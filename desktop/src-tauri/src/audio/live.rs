use std::{
    fs::File,
    io::BufWriter,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
        mpsc, Arc,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use cpal::{
    traits::{DeviceTrait, StreamTrait},
    FromSample, Sample, SampleFormat as CpalSampleFormat, SizedSample, Stream, StreamConfig,
    StreamError,
};
use hound::{SampleFormat as HoundSampleFormat, WavSpec, WavWriter};
use parking_lot::Mutex;
use rtrb::RingBuffer;
use tauri::ipc::Channel;

use crate::{
    audio::{
        devices::{
            is_standard_vb_cable_recording_endpoint, resolve_input_device, resolve_output_device,
            resolve_virtual_mic_output_device,
        },
        io::{decode_audio_file, DecodedAudio},
    },
    engine::{
        dsp::{peak, rms, sinc_resample, waveform_summary},
        target_speaker::TargetSpeakerRuntime,
        SharedEngine,
    },
    error::{AppError, AppResult},
    models::{
        LiveMeterEvent, LiveOutputMode, LiveOutputModeEvent, LiveProcessingMode,
        LiveRealtimeHealth, LiveSessionState, LiveStatusEvent, StartLiveMonitorRequest,
        TargetSpeakerEngine, TargetSpeakerOutputMode,
    },
};

const STREAMING_MIN_LOOKAHEAD_MS: u32 = 120;
const BUFFERED_MIN_LOOKAHEAD_MS: u32 = 250;
const MAX_LOOKAHEAD_MS: u32 = 1000;

pub struct LiveSessionControl {
    stop_flag: Arc<AtomicBool>,
    join_handle: Mutex<Option<thread::JoinHandle<()>>>,
}

impl LiveSessionControl {
    pub fn stop(&self) -> AppResult<()> {
        self.stop_flag.store(true, Ordering::SeqCst);
        if let Some(handle) = self.join_handle.lock().take() {
            handle
                .join()
                .map_err(|_| AppError::message("live audio worker thread panicked"))?;
        }
        Ok(())
    }
}

pub fn spawn_live_session(
    engine: Arc<SharedEngine>,
    target_speaker: Arc<TargetSpeakerRuntime>,
    session_id: String,
    request: StartLiveMonitorRequest,
    status_channel: Channel<LiveStatusEvent>,
    meter_channel: Channel<LiveMeterEvent>,
    on_exit: impl FnOnce() + Send + 'static,
) -> AppResult<Arc<LiveSessionControl>> {
    let stop_flag = Arc::new(AtomicBool::new(false));
    let stop_flag_thread = Arc::clone(&stop_flag);
    let (ready_tx, ready_rx) = mpsc::channel::<Result<(), String>>();
    let session_id_for_ready = session_id.clone();
    let ready_error_tx = ready_tx.clone();

    let join_handle = thread::spawn(move || {
        let _exit = ExitGuard {
            callback: Some(Box::new(on_exit)),
        };
        let result = run_live_worker(
            engine,
            target_speaker,
            session_id.clone(),
            request,
            status_channel,
            meter_channel,
            stop_flag_thread,
            ready_tx,
        );
        if let Err(error) = result {
            let _ = ready_error_tx.send(Err(error.to_string()));
            log::error!("Live session '{}' ended with error: {error}", session_id);
        }
    });

    match ready_rx.recv() {
        Ok(Ok(())) => Ok(Arc::new(LiveSessionControl {
            stop_flag,
            join_handle: Mutex::new(Some(join_handle)),
        })),
        Ok(Err(message)) => {
            let _ = join_handle.join();
            Err(AppError::message(format!(
                "unable to start live monitor '{}': {message}",
                session_id_for_ready
            )))
        }
        Err(_) => {
            let _ = join_handle.join();
            Err(AppError::message(format!(
                "live monitor '{}' exited before reporting readiness",
                session_id_for_ready
            )))
        }
    }
}

fn run_live_worker(
    engine: Arc<SharedEngine>,
    target_speaker: Arc<TargetSpeakerRuntime>,
    session_id: String,
    request: StartLiveMonitorRequest,
    status_channel: Channel<LiveStatusEvent>,
    meter_channel: Channel<LiveMeterEvent>,
    stop_flag: Arc<AtomicBool>,
    ready_tx: mpsc::Sender<Result<(), String>>,
) -> AppResult<()> {
    let debug_input_path = request
        .debug_input_path
        .as_deref()
        .map(str::trim)
        .filter(|path| !path.is_empty())
        .map(PathBuf::from);
    let debug_input = match debug_input_path {
        Some(path) => Some((path.clone(), decode_audio_file(&path)?)),
        None => None,
    };
    let input = if debug_input.is_some() {
        None
    } else {
        Some(resolve_input_device(request.input_device_id.as_deref())?)
    };
    let processing_mode = request.processing_mode.clone();
    let output_mode = match &processing_mode {
        LiveProcessingMode::SpeakerSuppression => LiveOutputMode::VirtualMic,
        LiveProcessingMode::SemanticSuppression => request.output_mode.clone(),
    };
    let output = match output_mode {
        LiveOutputMode::Monitor => resolve_output_device(request.output_device_id.as_deref())?,
        LiveOutputMode::VirtualMic => resolve_virtual_mic_output_device()?.0,
    };
    let input_uses_standard_vb_cable = input
        .as_ref()
        .map(|input| is_standard_vb_cable_recording_endpoint(&input.descriptor))
        .unwrap_or(false);
    if matches!(output_mode, LiveOutputMode::VirtualMic) && input_uses_standard_vb_cable {
        return Err(AppError::message(
            "Virtual Mic mode cannot use the same standard VB-CABLE pair as its input. \
            Choose a real microphone or a second virtual-cable recording endpoint, such as \
            'CABLE Output (VB-Audio Point)' or 'Input (VB-Audio Point)'.",
        ));
    }
    let input_device_id = match (&input, &debug_input) {
        (Some(input), _) => input.descriptor.id.clone(),
        (_, Some((path, _))) => format!("debug-wav::{}", path.display()),
        _ => "debug-wav".to_string(),
    };
    let output_device_id = output.descriptor.id.clone();
    let output_device_name = output.descriptor.name.clone();
    let provider_base = match (&output_mode, debug_input.is_some()) {
        (LiveOutputMode::Monitor, false) => "wasapi-shared/cpal",
        (LiveOutputMode::VirtualMic, false) => "wasapi-shared/cpal+vb-cable",
        (LiveOutputMode::Monitor, true) => "debug-wav/cpal",
        (LiveOutputMode::VirtualMic, true) => "debug-wav/cpal+vb-cable",
    };
    let provider = match &processing_mode {
        LiveProcessingMode::SemanticSuppression => provider_base.to_string(),
        LiveProcessingMode::SpeakerSuppression => format!("{provider_base}/target-speaker"),
    };
    let output_mode_event = LiveOutputModeEvent::from(&output_mode);

    let output_config = output.config.clone();
    let input_rate = match (&input, &debug_input) {
        (Some(input), _) => input.config.sample_rate().0,
        (_, Some((_, audio))) => audio.sample_rate,
        _ => 48_000,
    };
    let output_rate = output_config.sample_rate().0;
    let input_channels = input
        .as_ref()
        .map(|input| input.config.channels() as usize)
        .unwrap_or(1);
    let output_channels = output_config.channels() as usize;
    let preferred_hop_ms = match &processing_mode {
        LiveProcessingMode::SemanticSuppression => engine.preferred_live_hop_ms_f32().max(1.0),
        LiveProcessingMode::SpeakerSuppression => target_speaker.preferred_live_hop_ms(),
    };
    let lookahead_ms = clamp_live_lookahead_ms(
        request.lookahead_ms,
        matches!(&processing_mode, LiveProcessingMode::SemanticSuppression)
            && engine.is_streaming_live_runtime(),
    );
    let mut semantic_processor = match &processing_mode {
        LiveProcessingMode::SemanticSuppression => Some(engine.make_processor()?),
        LiveProcessingMode::SpeakerSuppression => None,
    };
    let mut speaker_processor = match &processing_mode {
        LiveProcessingMode::SemanticSuppression => None,
        LiveProcessingMode::SpeakerSuppression => {
            let reference_path = request
                .speaker_reference_path
                .as_deref()
                .map(str::trim)
                .filter(|path| !path.is_empty())
                .ok_or_else(|| {
                    AppError::message("choose a reference speaker clip or saved speaker profile")
                })?;
            let engine = request
                .speaker_engine
                .unwrap_or(TargetSpeakerEngine::TsextractOnnx);
            let output_mode = request
                .speaker_output_mode
                .unwrap_or(TargetSpeakerOutputMode::RemoveTarget);
            Some(target_speaker.make_live_processor(
                Path::new(reference_path),
                engine,
                output_mode,
                request.speaker_removal_scale.unwrap_or(1.0),
            )?)
        }
    };
    let mut record_writer =
        create_record_writer(request.record_output_path.as_deref(), input_rate)?;

    let capture_capacity = (input_rate as usize * 15).max(8192);
    let render_capacity = (output_rate as usize * 8).max(8192);
    let (capture_producer, mut capture_consumer) = RingBuffer::<f32>::new(capture_capacity);
    let (mut render_producer, render_consumer) = RingBuffer::<f32>::new(render_capacity);

    let xruns = Arc::new(AtomicU32::new(0));
    let captured_frames = Arc::new(AtomicU64::new(0));
    let rendered_frames = Arc::new(AtomicU64::new(0));
    let render_ready = Arc::new(AtomicBool::new(false));

    let input_status_channel = status_channel.clone();
    let output_status_channel = status_channel.clone();
    let input_xruns = Arc::clone(&xruns);
    let output_xruns = Arc::clone(&xruns);
    let capture_counter = Arc::clone(&captured_frames);
    let render_counter = Arc::clone(&rendered_frames);
    let render_ready_output = Arc::clone(&render_ready);
    let input_xruns_error = Arc::clone(&xruns);
    let output_xruns_error = Arc::clone(&xruns);
    let input_stop_flag = Arc::clone(&stop_flag);
    let output_stop_flag = Arc::clone(&stop_flag);
    let fatal_error = Arc::new(Mutex::new(None::<String>));
    let input_fatal_error = Arc::clone(&fatal_error);
    let output_fatal_error = Arc::clone(&fatal_error);
    let input_provider_error = provider.clone();
    let output_provider_error = provider.clone();
    let input_output_mode_error = output_mode_event.clone();
    let output_output_mode_error = output_mode_event.clone();
    let session_id_input_error = session_id.clone();
    let session_id_output_error = session_id.clone();
    let input_device_id_for_input_error = input_device_id.clone();
    let output_device_id_for_input_error = output_device_id.clone();
    let output_device_name_for_input_error = output_device_name.clone();
    let input_device_id_for_output_error = input_device_id.clone();
    let output_device_id_for_output_error = output_device_id.clone();
    let output_device_name_for_output_error = output_device_name.clone();

    let input_error_callback = move |error| {
        let message = format!("input stream error: {error}");
        {
            let mut guard = input_fatal_error.lock();
            if guard.is_none() {
                *guard = Some(message.clone());
            }
        }
        input_stop_flag.store(true, Ordering::SeqCst);
        let _ = input_status_channel.send(LiveStatusEvent {
            session_id: session_id_input_error.clone(),
            state: LiveSessionState::Error,
            xruns: input_xruns_error.load(Ordering::Relaxed),
            provider: input_provider_error.clone(),
            output_mode: input_output_mode_error.clone(),
            lookahead_ms,
            inference_ms: None,
            inference_ms_p50: None,
            inference_ms_p95: None,
            queue_depth_ms: None,
            estimated_latency_ms: None,
            realtime_health: LiveRealtimeHealth::Overloaded,
            sample_rate: Some(input_rate),
            input_device_id: Some(input_device_id_for_input_error.clone()),
            output_device_id: Some(output_device_id_for_input_error.clone()),
            output_device_name: Some(output_device_name_for_input_error.clone()),
            message: Some(message),
        });
    };
    let output_error_callback = move |error| {
        let message = format!("output stream error: {error}");
        {
            let mut guard = output_fatal_error.lock();
            if guard.is_none() {
                *guard = Some(message.clone());
            }
        }
        output_stop_flag.store(true, Ordering::SeqCst);
        let _ = output_status_channel.send(LiveStatusEvent {
            session_id: session_id_output_error.clone(),
            state: LiveSessionState::Error,
            xruns: output_xruns_error.load(Ordering::Relaxed),
            provider: output_provider_error.clone(),
            output_mode: output_output_mode_error.clone(),
            lookahead_ms,
            inference_ms: None,
            inference_ms_p50: None,
            inference_ms_p95: None,
            queue_depth_ms: None,
            estimated_latency_ms: None,
            realtime_health: LiveRealtimeHealth::Overloaded,
            sample_rate: Some(output_rate),
            input_device_id: Some(input_device_id_for_output_error.clone()),
            output_device_id: Some(output_device_id_for_output_error.clone()),
            output_device_name: Some(output_device_name_for_output_error.clone()),
            message: Some(message),
        });
    };

    let output_stream = match output_config.sample_format() {
        CpalSampleFormat::F32 => build_live_output_stream::<f32, _>(
            &output.device,
            &StreamConfig::from(output_config.clone()),
            output_channels,
            render_consumer,
            output_xruns,
            render_counter,
            render_ready_output,
            output_error_callback,
        )?,
        CpalSampleFormat::I16 => build_live_output_stream::<i16, _>(
            &output.device,
            &StreamConfig::from(output_config.clone()),
            output_channels,
            render_consumer,
            output_xruns,
            render_counter,
            render_ready_output,
            output_error_callback,
        )?,
        CpalSampleFormat::U16 => build_live_output_stream::<u16, _>(
            &output.device,
            &StreamConfig::from(output_config.clone()),
            output_channels,
            render_consumer,
            output_xruns,
            render_counter,
            render_ready_output,
            output_error_callback,
        )?,
        sample_format => {
            return Err(AppError::Unsupported(format!(
                "output device '{}' uses unsupported live sample format '{}'",
                output.descriptor.name, sample_format
            )))
        }
    };

    let (input_stream, debug_input_join) = if let Some((debug_path, debug_audio)) = debug_input {
        (
            None,
            Some(spawn_debug_wav_input(
                debug_path,
                debug_audio,
                capture_producer,
                input_xruns,
                capture_counter,
                Arc::clone(&stop_flag),
            )),
        )
    } else {
        let input = input.ok_or_else(|| AppError::message("no live input source was resolved"))?;
        let input_config = input.config.clone();
        let stream = match input_config.sample_format() {
            CpalSampleFormat::F32 => build_live_input_stream::<f32, _>(
                &input.device,
                &StreamConfig::from(input_config.clone()),
                input_channels,
                capture_producer,
                input_xruns,
                capture_counter,
                input_error_callback,
            )?,
            CpalSampleFormat::I16 => build_live_input_stream::<i16, _>(
                &input.device,
                &StreamConfig::from(input_config.clone()),
                input_channels,
                capture_producer,
                input_xruns,
                capture_counter,
                input_error_callback,
            )?,
            CpalSampleFormat::U16 => build_live_input_stream::<u16, _>(
                &input.device,
                &StreamConfig::from(input_config.clone()),
                input_channels,
                capture_producer,
                input_xruns,
                capture_counter,
                input_error_callback,
            )?,
            sample_format => {
                return Err(AppError::Unsupported(format!(
                    "input device '{}' uses unsupported live sample format '{}'",
                    input.descriptor.name, sample_format
                )))
            }
        };
        (Some(stream), None)
    };

    if let Some(input_stream) = input_stream.as_ref() {
        input_stream.play()?;
    }
    output_stream.play()?;

    if let Some(message) = fatal_error.lock().clone() {
        return Err(AppError::message(message));
    }

    let _ = status_channel.send(LiveStatusEvent {
        session_id: session_id.clone(),
        state: LiveSessionState::Starting,
        xruns: 0,
        provider: provider.clone(),
        output_mode: output_mode_event.clone(),
        lookahead_ms,
        inference_ms: None,
        inference_ms_p50: None,
        inference_ms_p95: None,
        queue_depth_ms: None,
        estimated_latency_ms: Some(lookahead_ms as f32 + preferred_hop_ms),
        realtime_health: LiveRealtimeHealth::Idle,
        sample_rate: Some(input_rate),
        input_device_id: Some(input_device_id.clone()),
        output_device_id: Some(output_device_id.clone()),
        output_device_name: Some(output_device_name.clone()),
        message: Some("Opening live monitor streams".to_string()),
    });

    ready_tx
        .send(Ok(()))
        .map_err(|error| AppError::message(error.to_string()))?;

    let hop_samples = match &processing_mode {
        LiveProcessingMode::SemanticSuppression => engine.preferred_live_hop_samples(input_rate),
        LiveProcessingMode::SpeakerSuppression => {
            target_speaker.preferred_live_hop_samples(input_rate)
        }
    };
    let prebuffer_frames = output_rate as usize * lookahead_ms as usize / 1000;
    let mut pending_input = Vec::<f32>::with_capacity(hop_samples * 4);
    let mut scratch = vec![0.0f32; hop_samples.max(1024)];
    let mut buffered_since_inference = 0usize;
    let mut last_output_chunk = Vec::<f32>::new();
    let mut last_input_chunk = Vec::<f32>::new();
    let mut inference_window = Vec::<f32>::with_capacity(128);
    let mut last_meter_emit = Instant::now();

    let _ = status_channel.send(LiveStatusEvent {
        session_id: session_id.clone(),
        state: LiveSessionState::Running,
        xruns: 0,
        provider: provider.clone(),
        output_mode: output_mode_event.clone(),
        lookahead_ms,
        inference_ms: None,
        inference_ms_p50: None,
        inference_ms_p95: None,
        queue_depth_ms: Some(0.0),
        estimated_latency_ms: Some(lookahead_ms as f32 + preferred_hop_ms),
        realtime_health: LiveRealtimeHealth::Ok,
        sample_rate: Some(input_rate),
        input_device_id: Some(input_device_id.clone()),
        output_device_id: Some(output_device_id.clone()),
        output_device_name: Some(output_device_name.clone()),
        message: Some(live_active_message(&processing_mode).to_string()),
    });

    while !stop_flag.load(Ordering::Relaxed) {
        let available = capture_consumer.slots().min(scratch.len());
        if available > 0 {
            let (read, _) = capture_consumer.pop_partial_slice(&mut scratch[..available]);
            if !read.is_empty() {
                pending_input.extend_from_slice(read);
                buffered_since_inference += read.len();
                last_input_chunk.clear();
                last_input_chunk.extend_from_slice(read);
            }
        }

        while buffered_since_inference >= hop_samples {
            let chunk = pending_input.drain(0..hop_samples).collect::<Vec<_>>();
            let infer_started = Instant::now();
            let mut cleaned = match (&mut semantic_processor, &mut speaker_processor) {
                (Some(processor), None) => processor.suppress_live_chunk(
                    &chunk,
                    input_rate,
                    &request.categories,
                    request.aggressiveness,
                    &stop_flag,
                )?,
                (None, Some(processor)) => {
                    target_speaker.suppress_live_chunk(processor, &chunk, input_rate, &stop_flag)?
                }
                _ => {
                    return Err(AppError::message(
                        "live session did not resolve exactly one processor",
                    ));
                }
            };
            let inference_ms = infer_started.elapsed().as_secs_f32() * 1000.0;
            let (inference_ms_p50, inference_ms_p95) =
                update_inference_window(&mut inference_window, inference_ms);
            let record_chunk = cleaned.clone();

            if output_rate != input_rate {
                cleaned = sinc_resample(&cleaned, input_rate, output_rate)?;
            }
            last_output_chunk = cleaned.clone();

            let (written, _) = render_producer.push_partial_slice(&cleaned);
            if written.len() < cleaned.len() {
                xruns.fetch_add(1, Ordering::Relaxed);
            }
            if !render_ready.load(Ordering::Relaxed)
                && render_capacity.saturating_sub(render_producer.slots()) >= prebuffer_frames
            {
                render_ready.store(true, Ordering::Relaxed);
            }

            if let Some(writer) = record_writer.as_mut() {
                for sample in &record_chunk {
                    writer
                        .write_sample(*sample)
                        .map_err(|error| AppError::message(error.to_string()))?;
                }
            }

            let queue_depth_ms = (render_capacity.saturating_sub(render_producer.slots()) as f32
                / output_rate as f32)
                * 1000.0;
            let xruns_now = xruns.load(Ordering::Relaxed);
            let _ = status_channel.send(LiveStatusEvent {
                session_id: session_id.clone(),
                state: LiveSessionState::Running,
                xruns: xruns_now,
                provider: provider.clone(),
                output_mode: output_mode_event.clone(),
                lookahead_ms,
                inference_ms: Some(inference_ms),
                inference_ms_p50: Some(inference_ms_p50),
                inference_ms_p95: Some(inference_ms_p95),
                queue_depth_ms: Some(queue_depth_ms),
                estimated_latency_ms: Some(estimated_added_latency_ms(
                    queue_depth_ms,
                    inference_ms,
                    preferred_hop_ms,
                )),
                realtime_health: realtime_health(
                    inference_ms,
                    xruns_now,
                    preferred_hop_ms,
                    live_target_count(&processing_mode, request.categories.len()),
                ),
                sample_rate: Some(input_rate),
                input_device_id: Some(input_device_id.clone()),
                output_device_id: Some(output_device_id.clone()),
                output_device_name: Some(output_device_name.clone()),
                message: Some(live_active_message(&processing_mode).to_string()),
            });

            buffered_since_inference = buffered_since_inference.saturating_sub(hop_samples);
        }

        if last_meter_emit.elapsed() >= Duration::from_millis(125) {
            let _ = meter_channel.send(LiveMeterEvent {
                session_id: session_id.clone(),
                rms_in: rms(&last_input_chunk),
                rms_out: rms(&last_output_chunk),
                peak_in: peak(&last_input_chunk),
                peak_out: peak(&last_output_chunk),
                waveform_in: waveform_summary(&last_input_chunk, 24),
                waveform_out: waveform_summary(&last_output_chunk, 24),
                captured_frames: captured_frames.load(Ordering::Relaxed),
                rendered_frames: rendered_frames.load(Ordering::Relaxed),
                timestamp_ms: SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_millis() as u64,
            });
            last_meter_emit = Instant::now();
        }

        thread::sleep(Duration::from_millis(5));
    }

    stop_flag.store(true, Ordering::SeqCst);
    if let Some(handle) = debug_input_join {
        handle
            .join()
            .map_err(|_| AppError::message("debug WAV input thread panicked"))?;
    }

    let fatal_error_message = fatal_error.lock().clone();
    if fatal_error_message.is_none() {
        let _ = status_channel.send(LiveStatusEvent {
            session_id,
            state: LiveSessionState::Stopped,
            xruns: xruns.load(Ordering::Relaxed),
            provider,
            output_mode: output_mode_event,
            lookahead_ms,
            inference_ms: None,
            inference_ms_p50: None,
            inference_ms_p95: None,
            queue_depth_ms: Some(0.0),
            estimated_latency_ms: Some(0.0),
            realtime_health: LiveRealtimeHealth::Idle,
            sample_rate: Some(input_rate),
            input_device_id: Some(input_device_id),
            output_device_id: Some(output_device_id),
            output_device_name: Some(output_device_name),
            message: Some("Live suppression stopped".to_string()),
        });
    }

    if let Some(writer) = record_writer {
        writer
            .finalize()
            .map_err(|error| AppError::message(error.to_string()))?;
    }

    Ok(())
}

fn spawn_debug_wav_input(
    path: PathBuf,
    audio: DecodedAudio,
    mut capture_producer: rtrb::Producer<f32>,
    input_xruns: Arc<AtomicU32>,
    capture_counter: Arc<AtomicU64>,
    stop_flag: Arc<AtomicBool>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let sample_rate = audio.sample_rate.max(1);
        let frame_count = audio.frame_count();
        if frame_count == 0 {
            log::warn!("Debug WAV input '{}' contains no frames", path.display());
            return;
        }

        log::info!(
            "Streaming debug WAV input '{}' at {} Hz into live capture",
            path.display(),
            sample_rate
        );
        let chunk_frames = (sample_rate as usize / 50).max(1);
        let mut cursor = 0usize;

        while !stop_flag.load(Ordering::SeqCst) {
            let end = (cursor + chunk_frames).min(frame_count);
            let mut chunk = audio.mono_range(cursor, end);
            if end == frame_count && chunk.len() < chunk_frames {
                let remaining = chunk_frames - chunk.len();
                chunk.extend(audio.mono_range(0, remaining.min(frame_count)));
            }

            for sample in &chunk {
                if capture_producer.push(*sample).is_err() {
                    input_xruns.fetch_add(1, Ordering::Relaxed);
                } else {
                    capture_counter.fetch_add(1, Ordering::Relaxed);
                }
            }

            cursor = (cursor + chunk_frames) % frame_count;
            let sleep_seconds = chunk.len() as f32 / sample_rate as f32;
            thread::sleep(Duration::from_secs_f32(sleep_seconds.max(0.001)));
        }
    })
}

fn build_live_input_stream<T, E>(
    device: &cpal::Device,
    config: &StreamConfig,
    input_channels: usize,
    mut capture_producer: rtrb::Producer<f32>,
    input_xruns: Arc<AtomicU32>,
    capture_counter: Arc<AtomicU64>,
    error_callback: E,
) -> Result<Stream, cpal::BuildStreamError>
where
    T: Sample + SizedSample + Copy + Send + 'static,
    f32: FromSample<T>,
    E: FnMut(StreamError) + Send + 'static,
{
    device.build_input_stream(
        config,
        move |data: &[T], _| {
            for frame in data.chunks(input_channels.max(1)) {
                let mono = frame.iter().copied().map(f32::from_sample).sum::<f32>()
                    / frame.len().max(1) as f32;
                if capture_producer.push(mono).is_err() {
                    input_xruns.fetch_add(1, Ordering::Relaxed);
                } else {
                    capture_counter.fetch_add(1, Ordering::Relaxed);
                }
            }
        },
        error_callback,
        None,
    )
}

fn build_live_output_stream<T, E>(
    device: &cpal::Device,
    config: &StreamConfig,
    output_channels: usize,
    mut render_consumer: rtrb::Consumer<f32>,
    output_xruns: Arc<AtomicU32>,
    render_counter: Arc<AtomicU64>,
    render_ready: Arc<AtomicBool>,
    error_callback: E,
) -> Result<Stream, cpal::BuildStreamError>
where
    T: Sample + SizedSample + FromSample<f32> + Copy + Send + 'static,
    E: FnMut(StreamError) + Send + 'static,
{
    device.build_output_stream(
        config,
        move |data: &mut [T], _| {
            if !render_ready.load(Ordering::Relaxed) {
                let silence = T::from_sample(0.0);
                data.fill(silence);
                return;
            }

            for frame in data.chunks_mut(output_channels.max(1)) {
                let sample = match render_consumer.pop() {
                    Ok(sample) => sample.clamp(-1.0, 1.0),
                    Err(_) => {
                        output_xruns.fetch_add(1, Ordering::Relaxed);
                        0.0
                    }
                };
                let value = T::from_sample(sample);
                for slot in frame {
                    *slot = value;
                }
                render_counter.fetch_add(1, Ordering::Relaxed);
            }
        },
        error_callback,
        None,
    )
}

pub(crate) fn clamp_live_lookahead_ms(requested_ms: u32, streaming_runtime: bool) -> u32 {
    let min = if streaming_runtime {
        STREAMING_MIN_LOOKAHEAD_MS
    } else {
        BUFFERED_MIN_LOOKAHEAD_MS
    };
    requested_ms.clamp(min, MAX_LOOKAHEAD_MS)
}

fn estimated_added_latency_ms(
    queue_depth_ms: f32,
    inference_ms: f32,
    preferred_hop_ms: f32,
) -> f32 {
    queue_depth_ms + inference_ms + preferred_hop_ms
}

fn realtime_health(
    inference_ms: f32,
    xruns: u32,
    preferred_hop_ms: f32,
    category_count: usize,
) -> LiveRealtimeHealth {
    let hop_ms = preferred_hop_ms.max(1.0);
    if inference_ms >= hop_ms * 2.0 {
        LiveRealtimeHealth::Overloaded
    } else if inference_ms > hop_ms || xruns > 0 || category_count > 2 {
        LiveRealtimeHealth::Warning
    } else {
        LiveRealtimeHealth::Ok
    }
}

fn live_active_message(processing_mode: &LiveProcessingMode) -> &'static str {
    match processing_mode {
        LiveProcessingMode::SemanticSuppression => "Live suppression active",
        LiveProcessingMode::SpeakerSuppression => "Speaker realtime suppression active",
    }
}

fn live_target_count(processing_mode: &LiveProcessingMode, category_count: usize) -> usize {
    match processing_mode {
        LiveProcessingMode::SemanticSuppression => category_count,
        LiveProcessingMode::SpeakerSuppression => 1,
    }
}

fn update_inference_window(window: &mut Vec<f32>, value: f32) -> (f32, f32) {
    const MAX_WINDOW: usize = 128;
    if window.len() == MAX_WINDOW {
        window.remove(0);
    }
    window.push(value);

    let mut sorted = window.clone();
    sorted.sort_by(|left, right| left.total_cmp(right));
    (percentile(&sorted, 0.50), percentile(&sorted, 0.95))
}

fn percentile(sorted: &[f32], fraction: f32) -> f32 {
    if sorted.is_empty() {
        return 0.0;
    }
    let index = ((sorted.len() - 1) as f32 * fraction).round() as usize;
    sorted[index.min(sorted.len() - 1)]
}

fn create_record_writer(
    path: Option<&str>,
    sample_rate: u32,
) -> AppResult<Option<WavWriter<BufWriter<File>>>> {
    let Some(path) = path else {
        return Ok(None);
    };
    let path = PathBuf::from(path);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let spec = WavSpec {
        channels: 1,
        sample_rate,
        bits_per_sample: 32,
        sample_format: HoundSampleFormat::Float,
    };
    let writer =
        WavWriter::create(path, spec).map_err(|error| AppError::message(error.to_string()))?;
    Ok(Some(writer))
}

struct ExitGuard {
    callback: Option<Box<dyn FnOnce() + Send + 'static>>,
}

impl Drop for ExitGuard {
    fn drop(&mut self) {
        if let Some(callback) = self.callback.take() {
            callback();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::clamp_live_lookahead_ms;

    #[test]
    fn waveformer_live_lookahead_allows_voice_chat_buffers() {
        assert_eq!(clamp_live_lookahead_ms(80, true), 120);
        assert_eq!(clamp_live_lookahead_ms(150, true), 150);
        assert_eq!(clamp_live_lookahead_ms(1400, true), 1000);
    }

    #[test]
    fn non_streaming_live_lookahead_keeps_safer_floor() {
        assert_eq!(clamp_live_lookahead_ms(120, false), 250);
        assert_eq!(clamp_live_lookahead_ms(300, false), 300);
    }
}
