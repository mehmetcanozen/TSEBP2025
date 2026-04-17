use std::{
    fs::File,
    io::BufWriter,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
        mpsc,
        Arc,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use cpal::{
    traits::{DeviceTrait, StreamTrait},
    StreamConfig,
};
use hound::{SampleFormat, WavSpec, WavWriter};
use parking_lot::Mutex;
use rtrb::RingBuffer;
use tauri::ipc::Channel;

use crate::{
    audio::devices::{resolve_input_device, resolve_output_device},
    engine::{dsp::{peak, rms, waveform_summary, linear_resample}, SharedEngine},
    error::{AppError, AppResult},
    models::{LiveMeterEvent, LiveSessionState, LiveStatusEvent, StartLiveMonitorRequest},
};

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
    session_id: String,
    request: StartLiveMonitorRequest,
    status_channel: Channel<LiveStatusEvent>,
    meter_channel: Channel<LiveMeterEvent>,
    stop_flag: Arc<AtomicBool>,
    ready_tx: mpsc::Sender<Result<(), String>>,
) -> AppResult<()> {
    let input = resolve_input_device(request.input_device_id.as_deref())?;
    let output = resolve_output_device(request.output_device_id.as_deref())?;
    let input_device_id = input.descriptor.id.clone();
    let output_device_id = output.descriptor.id.clone();

    let input_config = input.config.clone();
    let output_config = output.config.clone();
    let input_rate = input_config.sample_rate().0;
    let output_rate = output_config.sample_rate().0;
    let input_channels = input_config.channels() as usize;
    let output_channels = output_config.channels() as usize;
    let lookahead_ms = request.lookahead_ms.clamp(250, 1000);
    let mut processor = engine.make_processor()?;
    let mut record_writer = create_record_writer(request.record_output_path.as_deref(), input_rate)?;

    let capture_capacity = (input_rate as usize * 15).max(8192);
    let render_capacity = (output_rate as usize * 8).max(8192);
    let (mut capture_producer, mut capture_consumer) = RingBuffer::<f32>::new(capture_capacity);
    let (mut render_producer, mut render_consumer) = RingBuffer::<f32>::new(render_capacity);

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
    let session_id_input_error = session_id.clone();
    let session_id_output_error = session_id.clone();
    let input_device_id_for_input_error = input_device_id.clone();
    let output_device_id_for_input_error = output_device_id.clone();
    let input_device_id_for_output_error = input_device_id.clone();
    let output_device_id_for_output_error = output_device_id.clone();

    let input_stream = input.device.build_input_stream(
        &StreamConfig::from(input_config.clone()),
        move |data: &[f32], _| {
            for frame in data.chunks(input_channels.max(1)) {
                let mono = frame.iter().copied().sum::<f32>() / frame.len().max(1) as f32;
                if capture_producer.push(mono).is_err() {
                    input_xruns.fetch_add(1, Ordering::Relaxed);
                } else {
                    capture_counter.fetch_add(1, Ordering::Relaxed);
                }
            }
        },
        move |error| {
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
                provider: "wasapi-shared/cpal".to_string(),
                lookahead_ms,
                inference_ms: None,
                queue_depth_ms: None,
                sample_rate: Some(input_rate),
                input_device_id: Some(input_device_id_for_input_error.clone()),
                output_device_id: Some(output_device_id_for_input_error.clone()),
                message: Some(message),
            });
        },
        None,
    )?;

    let output_stream = output.device.build_output_stream(
        &StreamConfig::from(output_config.clone()),
        move |data: &mut [f32], _| {
            if !render_ready_output.load(Ordering::Relaxed) {
                data.fill(0.0);
                return;
            }

            for frame in data.chunks_mut(output_channels.max(1)) {
                let sample = match render_consumer.pop() {
                    Ok(sample) => sample,
                    Err(_) => {
                        output_xruns.fetch_add(1, Ordering::Relaxed);
                        0.0
                    }
                };
                for value in frame {
                    *value = sample;
                }
                render_counter.fetch_add(1, Ordering::Relaxed);
            }
        },
        move |error| {
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
                provider: "wasapi-shared/cpal".to_string(),
                lookahead_ms,
                inference_ms: None,
                queue_depth_ms: None,
                sample_rate: Some(output_rate),
                input_device_id: Some(input_device_id_for_output_error.clone()),
                output_device_id: Some(output_device_id_for_output_error.clone()),
                message: Some(message),
            });
        },
        None,
    )?;

    input_stream.play()?;
    output_stream.play()?;

    if let Some(message) = fatal_error.lock().clone() {
        return Err(AppError::message(message));
    }

    let _ = status_channel.send(LiveStatusEvent {
        session_id: session_id.clone(),
        state: LiveSessionState::Starting,
        xruns: 0,
        provider: "wasapi-shared/cpal".to_string(),
        lookahead_ms,
        inference_ms: None,
        queue_depth_ms: None,
        sample_rate: Some(input_rate),
        input_device_id: Some(input_device_id.clone()),
        output_device_id: Some(output_device_id.clone()),
        message: Some("Opening live monitor streams".to_string()),
    });

    ready_tx
        .send(Ok(()))
        .map_err(|error| AppError::message(error.to_string()))?;

    let hop_samples = input_rate as usize;
    let context_samples = input_rate as usize * 5;
    let prebuffer_frames = output_rate as usize * lookahead_ms as usize / 1000;
    let mut rolling_input = Vec::<f32>::with_capacity(context_samples + hop_samples * 2);
    let mut scratch = vec![0.0f32; hop_samples.max(1024)];
    let mut buffered_since_inference = 0usize;
    let mut last_output_chunk = Vec::<f32>::new();
    let mut last_input_chunk = Vec::<f32>::new();
    let mut last_meter_emit = Instant::now();

    let _ = status_channel.send(LiveStatusEvent {
        session_id: session_id.clone(),
        state: LiveSessionState::Running,
        xruns: 0,
        provider: "wasapi-shared/cpal".to_string(),
        lookahead_ms,
        inference_ms: None,
        queue_depth_ms: Some(0.0),
        sample_rate: Some(input_rate),
        input_device_id: Some(input_device_id.clone()),
        output_device_id: Some(output_device_id.clone()),
        message: Some("Live suppression active".to_string()),
    });

    while !stop_flag.load(Ordering::Relaxed) {
        let available = capture_consumer.slots().min(scratch.len());
        if available > 0 {
            let (read, _) = capture_consumer.pop_partial_slice(&mut scratch[..available]);
            if !read.is_empty() {
                rolling_input.extend_from_slice(read);
                buffered_since_inference += read.len();
                last_input_chunk.clear();
                last_input_chunk.extend_from_slice(read);

                let keep = context_samples + hop_samples * 2;
                if rolling_input.len() > keep {
                    let overflow = rolling_input.len() - keep;
                    rolling_input.drain(0..overflow);
                }
            }
        }

        while buffered_since_inference >= hop_samples {
            let context = latest_context(&rolling_input, context_samples);
            let infer_started = Instant::now();
            let cleaned = processor.suppress_live_mono(
                &context,
                input_rate,
                &request.categories,
                request.aggressiveness,
                &stop_flag,
            )?;
            let inference_ms = infer_started.elapsed().as_secs_f32() * 1000.0;

            let mut clean_hop = cleaned[cleaned.len().saturating_sub(hop_samples)..].to_vec();
            if output_rate != input_rate {
                clean_hop = linear_resample(&clean_hop, input_rate, output_rate);
            }
            last_output_chunk = clean_hop.clone();

            let (written, _) = render_producer.push_partial_slice(&clean_hop);
            if written.len() < clean_hop.len() {
                xruns.fetch_add(1, Ordering::Relaxed);
            }
            if !render_ready.load(Ordering::Relaxed)
                && render_capacity.saturating_sub(render_producer.slots()) >= prebuffer_frames
            {
                render_ready.store(true, Ordering::Relaxed);
            }

            if let Some(writer) = record_writer.as_mut() {
                for sample in &cleaned[cleaned.len().saturating_sub(hop_samples)..] {
                    writer
                        .write_sample(*sample)
                        .map_err(|error| AppError::message(error.to_string()))?;
                }
            }

            let queue_depth_ms =
                (render_capacity.saturating_sub(render_producer.slots()) as f32 / output_rate as f32) * 1000.0;
            let _ = status_channel.send(LiveStatusEvent {
                session_id: session_id.clone(),
                state: LiveSessionState::Running,
                xruns: xruns.load(Ordering::Relaxed),
                provider: "wasapi-shared/cpal".to_string(),
                lookahead_ms,
                inference_ms: Some(inference_ms),
                queue_depth_ms: Some(queue_depth_ms),
                sample_rate: Some(input_rate),
                input_device_id: Some(input_device_id.clone()),
                output_device_id: Some(output_device_id.clone()),
                message: Some("Live suppression active".to_string()),
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

    let fatal_error_message = fatal_error.lock().clone();
    if fatal_error_message.is_none() {
        let _ = status_channel.send(LiveStatusEvent {
            session_id,
            state: LiveSessionState::Stopped,
            xruns: xruns.load(Ordering::Relaxed),
            provider: "wasapi-shared/cpal".to_string(),
            lookahead_ms,
            inference_ms: None,
            queue_depth_ms: Some(0.0),
            sample_rate: Some(input_rate),
            input_device_id: Some(input_device_id),
            output_device_id: Some(output_device_id),
            message: Some("Live suppression stopped".to_string()),
        });
    }

    if let Some(writer) = record_writer {
        writer.finalize().map_err(|error| AppError::message(error.to_string()))?;
    }

    Ok(())
}

fn create_record_writer(path: Option<&str>, sample_rate: u32) -> AppResult<Option<WavWriter<BufWriter<File>>>> {
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
        sample_format: SampleFormat::Float,
    };
    let writer = WavWriter::create(path, spec).map_err(|error| AppError::message(error.to_string()))?;
    Ok(Some(writer))
}

fn latest_context(rolling_input: &[f32], context_samples: usize) -> Vec<f32> {
    if rolling_input.len() >= context_samples {
        return rolling_input[rolling_input.len() - context_samples..].to_vec();
    }

    let mut context = vec![0.0f32; context_samples];
    let offset = context_samples - rolling_input.len();
    context[offset..].copy_from_slice(rolling_input);
    context
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
