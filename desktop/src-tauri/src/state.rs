use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use parking_lot::Mutex;
use tauri::{ipc::Channel, AppHandle, Manager};
use uuid::Uuid;

use crate::{
    audio::{devices, io, live},
    config::{AssetCatalog, TargetSpeakerAssetCatalog},
    engine::{target_speaker::TargetSpeakerRuntime, SharedEngine},
    error::{AppError, AppResult},
    models::{
        AudioDevice, DeleteSpeakerProfileRequest, JobHandle, LiveMeterEvent, LiveProcessingMode,
        LiveSessionHandle, LiveStatusEvent, OfflineProgressEvent, OfflineProgressStage,
        RuntimeMetrics, SaveSpeakerProfileRequest, SpeakerProfile, StartLiveMonitorRequest,
        StartOfflineJobRequest, StartTargetSpeakerJobRequest, TargetSpeakerRuntimeInfo,
        VirtualMicStatus,
    },
};

struct OfflineJobControl {
    cancel_flag: Arc<AtomicBool>,
}

pub struct AppState {
    engine: Arc<SharedEngine>,
    target_speaker: Arc<TargetSpeakerRuntime>,
    speaker_profiles_dir: PathBuf,
    offline_jobs: Arc<Mutex<HashMap<String, OfflineJobControl>>>,
    live_sessions: Arc<Mutex<HashMap<String, Arc<live::LiveSessionControl>>>>,
}

impl AppState {
    pub fn new(app: &AppHandle) -> AppResult<Self> {
        let assets = AssetCatalog::resolve(app)?;
        let target_speaker_assets = TargetSpeakerAssetCatalog::resolve(app)?;
        let engine = Arc::new(SharedEngine::new(assets)?);
        let target_speaker = Arc::new(TargetSpeakerRuntime::new(target_speaker_assets));
        let speaker_profiles_dir = resolve_speaker_profiles_dir(app)?;
        fs::create_dir_all(&speaker_profiles_dir)?;
        Ok(Self {
            engine,
            target_speaker,
            speaker_profiles_dir,
            offline_jobs: Arc::new(Mutex::new(HashMap::new())),
            live_sessions: Arc::new(Mutex::new(HashMap::new())),
        })
    }

    pub fn engine(&self) -> &Arc<SharedEngine> {
        &self.engine
    }

    pub fn list_audio_devices(&self) -> AppResult<Vec<AudioDevice>> {
        devices::list_audio_devices()
    }

    pub fn get_virtual_mic_status(&self) -> AppResult<VirtualMicStatus> {
        devices::get_virtual_mic_status()
    }

    pub fn runtime_metrics(&self) -> AppResult<RuntimeMetrics> {
        let runtime = self.engine.runtime_info();
        Ok(RuntimeMetrics {
            provider: runtime.provider,
            available_providers: runtime.available_providers,
            warmed: runtime.warmed,
            model_id: runtime.model_id,
            model_family: runtime.model_family,
            display_name: runtime.display_name,
            suppression_strategy: runtime.suppression_strategy,
            runtime_kind: runtime.runtime_kind,
            category_count: self.engine.categories().len(),
            active_live_sessions: self.live_sessions.lock().len(),
            active_jobs: self.offline_jobs.lock().len(),
            model_path: runtime.model_path,
            runtime_metadata_paths: runtime.runtime_metadata_paths,
            model_sample_rate: runtime.model_sample_rate,
            chunk_samples: runtime.chunk_samples,
            preferred_live_hop_ms: runtime.preferred_live_hop_ms,
            validation_status: runtime.validation_status,
        })
    }

    pub fn target_speaker_runtime_info(&self) -> TargetSpeakerRuntimeInfo {
        self.target_speaker.info()
    }

    pub fn list_speaker_profiles(&self) -> AppResult<Vec<SpeakerProfile>> {
        fs::create_dir_all(&self.speaker_profiles_dir)?;
        let mut profiles = Vec::new();
        for entry in fs::read_dir(&self.speaker_profiles_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let profile: SpeakerProfile = serde_json::from_str(&fs::read_to_string(&path)?)?;
            profiles.push(profile);
        }
        profiles.sort_by(|left, right| {
            left.name
                .to_lowercase()
                .cmp(&right.name.to_lowercase())
                .then_with(|| left.created_at_ms.cmp(&right.created_at_ms))
        });
        Ok(profiles)
    }

    pub fn save_speaker_profile(
        &self,
        request: SaveSpeakerProfileRequest,
    ) -> AppResult<SpeakerProfile> {
        let name = request.name.trim();
        if name.is_empty() {
            return Err(AppError::message("enter a speaker profile name"));
        }
        let source_path = PathBuf::from(request.reference_path.trim());
        if source_path.as_os_str().is_empty() {
            return Err(AppError::message(
                "choose a reference speaker clip before saving a profile",
            ));
        }
        if !source_path.exists() {
            return Err(AppError::message(format!(
                "reference speaker clip was not found at '{}'",
                source_path.display()
            )));
        }

        fs::create_dir_all(&self.speaker_profiles_dir)?;
        let decoded = io::decode_audio_file(&source_path)?;
        let id = Uuid::new_v4().to_string();
        let extension = source_path
            .extension()
            .and_then(|value| value.to_str())
            .filter(|value| !value.trim().is_empty())
            .unwrap_or("wav");
        let reference_filename = format!(
            "{}_{}.{}",
            sanitize_profile_filename(name),
            &id[..8],
            extension
        );
        let stored_reference_path = self.speaker_profiles_dir.join(reference_filename);
        fs::copy(&source_path, &stored_reference_path)?;

        let now = now_ms();
        let profile = SpeakerProfile {
            id,
            name: name.to_string(),
            reference_path: stored_reference_path.to_string_lossy().to_string(),
            source_path: Some(source_path.to_string_lossy().to_string()),
            sample_rate: decoded.sample_rate,
            duration_ms: audio_duration_ms(decoded.frame_count(), decoded.sample_rate),
            created_at_ms: now,
            updated_at_ms: now,
        };
        let manifest_path = self.profile_manifest_path(&profile.id);
        fs::write(&manifest_path, serde_json::to_string_pretty(&profile)?)?;
        Ok(profile)
    }

    pub fn delete_speaker_profile(&self, request: DeleteSpeakerProfileRequest) -> AppResult<()> {
        let profile_id = request.profile_id.trim();
        if profile_id.is_empty() {
            return Err(AppError::message("choose a speaker profile to delete"));
        }
        let manifest_path = self.profile_manifest_path(profile_id);
        if !manifest_path.exists() {
            return Ok(());
        }
        let profile: SpeakerProfile = serde_json::from_str(&fs::read_to_string(&manifest_path)?)?;
        let reference_path = PathBuf::from(profile.reference_path);
        if reference_path.starts_with(&self.speaker_profiles_dir) && reference_path.exists() {
            fs::remove_file(reference_path)?;
        }
        fs::remove_file(manifest_path)?;
        Ok(())
    }

    pub async fn start_offline_job(
        &self,
        _app: AppHandle,
        request: StartOfflineJobRequest,
        progress_channel: Channel<OfflineProgressEvent>,
    ) -> AppResult<JobHandle> {
        self.engine
            .validate_selected_categories(&request.categories)?;

        let job_id = Uuid::new_v4().to_string();
        let cancel_flag = Arc::new(AtomicBool::new(false));
        self.offline_jobs.lock().insert(
            job_id.clone(),
            OfflineJobControl {
                cancel_flag: Arc::clone(&cancel_flag),
            },
        );

        let engine = Arc::clone(&self.engine);
        let engine_name = self.engine.display_name().to_string();
        let offline_jobs = Arc::clone(&self.offline_jobs);
        let request_clone = request.clone();
        let job_id_clone = job_id.clone();

        tauri::async_runtime::spawn_blocking(move || {
            let send_progress = |stage: OfflineProgressStage,
                                 progress: f32,
                                 eta_seconds: Option<f32>,
                                 message: Option<String>,
                                 output_path: Option<String>| {
                let _ = progress_channel.send(OfflineProgressEvent {
                    job_id: job_id_clone.clone(),
                    stage,
                    progress,
                    eta_seconds,
                    message,
                    output_path,
                });
            };

            send_progress(
                OfflineProgressStage::Queued,
                0.0,
                None,
                Some("Queued offline suppression job".to_string()),
                None,
            );

            let result = (|| -> AppResult<()> {
                send_progress(
                    OfflineProgressStage::Warming,
                    3.0,
                    None,
                    Some(format!("Warming {} runtime", engine_name)),
                    None,
                );
                let mut processor = engine.make_processor()?;

                if cancel_flag.load(Ordering::Relaxed) {
                    return Err(AppError::Cancelled);
                }

                send_progress(
                    OfflineProgressStage::Decoding,
                    6.0,
                    None,
                    Some("Decoding source audio".to_string()),
                    None,
                );
                let input_audio = io::decode_audio_file(Path::new(&request_clone.input_path))?;
                let started = Instant::now();

                send_progress(
                    OfflineProgressStage::Processing,
                    10.0,
                    None,
                    Some("Running model-guided suppression".to_string()),
                    None,
                );
                let mut progress_callback = |fraction: f32| {
                    let elapsed = started.elapsed().as_secs_f32();
                    let eta_seconds = if fraction > 0.001 {
                        Some(elapsed * (1.0 - fraction) / fraction)
                    } else {
                        None
                    };
                    send_progress(
                        OfflineProgressStage::Processing,
                        10.0 + fraction * 84.0,
                        eta_seconds,
                        Some("Suppressing selected categories".to_string()),
                        None,
                    );
                };
                let clean_audio = processor.process_offline(
                    &input_audio,
                    &request_clone.categories,
                    request_clone.aggressiveness,
                    &cancel_flag,
                    &mut progress_callback,
                )?;

                if cancel_flag.load(Ordering::Relaxed) {
                    return Err(AppError::Cancelled);
                }

                send_progress(
                    OfflineProgressStage::Writing,
                    96.0,
                    Some(0.0),
                    Some("Writing 32-bit float WAV".to_string()),
                    None,
                );
                io::write_wav_float(Path::new(&request_clone.output_path), &clean_audio)?;

                send_progress(
                    OfflineProgressStage::Completed,
                    100.0,
                    Some(0.0),
                    Some("Offline suppression complete".to_string()),
                    Some(request_clone.output_path.clone()),
                );

                Ok(())
            })();

            if let Err(error) = result {
                match error {
                    AppError::Cancelled => send_progress(
                        OfflineProgressStage::Cancelled,
                        100.0,
                        Some(0.0),
                        Some("Offline suppression cancelled".to_string()),
                        None,
                    ),
                    other => send_progress(
                        OfflineProgressStage::Failed,
                        100.0,
                        Some(0.0),
                        Some(other.to_string()),
                        None,
                    ),
                }
            }

            offline_jobs.lock().remove(&job_id_clone);
        });

        Ok(JobHandle { job_id })
    }

    pub async fn start_target_speaker_job(
        &self,
        request: StartTargetSpeakerJobRequest,
        progress_channel: Channel<OfflineProgressEvent>,
    ) -> AppResult<JobHandle> {
        let job_id = Uuid::new_v4().to_string();
        let cancel_flag = Arc::new(AtomicBool::new(false));
        self.offline_jobs.lock().insert(
            job_id.clone(),
            OfflineJobControl {
                cancel_flag: Arc::clone(&cancel_flag),
            },
        );

        let target_speaker = Arc::clone(&self.target_speaker);
        let offline_jobs = Arc::clone(&self.offline_jobs);
        let request_clone = request.clone();
        let job_id_clone = job_id.clone();

        tauri::async_runtime::spawn_blocking(move || {
            let send_progress = |stage: OfflineProgressStage,
                                 progress: f32,
                                 eta_seconds: Option<f32>,
                                 message: Option<String>,
                                 output_path: Option<String>| {
                let _ = progress_channel.send(OfflineProgressEvent {
                    job_id: job_id_clone.clone(),
                    stage,
                    progress,
                    eta_seconds,
                    message,
                    output_path,
                });
            };

            send_progress(
                OfflineProgressStage::Queued,
                0.0,
                None,
                Some("Queued target speaker suppression job".to_string()),
                None,
            );

            let result = (|| -> AppResult<()> {
                if request_clone.input_path.trim().is_empty() {
                    return Err(AppError::message("choose an input mixture audio file"));
                }
                if request_clone.reference_path.trim().is_empty() {
                    return Err(AppError::message("choose a reference speaker clip"));
                }
                if request_clone.output_path.trim().is_empty() {
                    return Err(AppError::message("choose an output WAV path"));
                }

                send_progress(
                    OfflineProgressStage::Warming,
                    4.0,
                    None,
                    Some(format!(
                        "Warming {:?} target speaker suppressor",
                        request_clone.engine
                    )),
                    None,
                );

                let started = Instant::now();
                send_progress(
                    OfflineProgressStage::Processing,
                    8.0,
                    None,
                    Some("Extracting reference-matched speaker and suppressing it".to_string()),
                    None,
                );
                let mut progress_callback = |fraction: f32| {
                    let fraction = fraction.clamp(0.0, 1.0);
                    let elapsed = started.elapsed().as_secs_f32();
                    let eta_seconds = if fraction > 0.001 {
                        Some(elapsed * (1.0 - fraction) / fraction)
                    } else {
                        None
                    };
                    send_progress(
                        OfflineProgressStage::Processing,
                        8.0 + fraction * 88.0,
                        eta_seconds,
                        Some("Suppressing the referenced speaker".to_string()),
                        None,
                    );
                };

                let output_audio = target_speaker.process(
                    Path::new(&request_clone.input_path),
                    Path::new(&request_clone.reference_path),
                    request_clone.engine,
                    request_clone.output_mode,
                    request_clone.removal_scale,
                    &cancel_flag,
                    &mut progress_callback,
                )?;

                if cancel_flag.load(Ordering::Relaxed) {
                    return Err(AppError::Cancelled);
                }

                send_progress(
                    OfflineProgressStage::Writing,
                    96.0,
                    Some(0.0),
                    Some("Writing speaker-suppressed float WAV".to_string()),
                    None,
                );
                io::write_wav_float(Path::new(&request_clone.output_path), &output_audio)?;

                send_progress(
                    OfflineProgressStage::Completed,
                    100.0,
                    Some(0.0),
                    Some("Target speaker suppression complete".to_string()),
                    Some(request_clone.output_path.clone()),
                );

                Ok(())
            })();

            if let Err(error) = result {
                match error {
                    AppError::Cancelled => send_progress(
                        OfflineProgressStage::Cancelled,
                        100.0,
                        Some(0.0),
                        Some("Target speaker suppression cancelled".to_string()),
                        None,
                    ),
                    other => send_progress(
                        OfflineProgressStage::Failed,
                        100.0,
                        Some(0.0),
                        Some(other.to_string()),
                        None,
                    ),
                }
            }

            offline_jobs.lock().remove(&job_id_clone);
        });

        Ok(JobHandle { job_id })
    }

    pub fn cancel_offline_job(&self, job_id: &str) -> AppResult<()> {
        let jobs = self.offline_jobs.lock();
        let Some(job) = jobs.get(job_id) else {
            return Err(AppError::message(format!(
                "offline job '{job_id}' was not found"
            )));
        };
        job.cancel_flag.store(true, Ordering::SeqCst);
        Ok(())
    }

    pub async fn start_live_monitor(
        &self,
        request: StartLiveMonitorRequest,
        status_channel: Channel<LiveStatusEvent>,
        meter_channel: Channel<LiveMeterEvent>,
    ) -> AppResult<LiveSessionHandle> {
        match &request.processing_mode {
            LiveProcessingMode::SemanticSuppression => {
                self.engine
                    .validate_selected_categories(&request.categories)?;
            }
            LiveProcessingMode::SpeakerSuppression => {
                let has_reference = request
                    .speaker_reference_path
                    .as_deref()
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .is_some();
                if !has_reference {
                    return Err(AppError::message(
                        "choose a reference speaker clip or saved speaker profile",
                    ));
                }
            }
        }

        let session_id = Uuid::new_v4().to_string();
        let live_sessions = Arc::clone(&self.live_sessions);
        let session_id_for_cleanup = session_id.clone();
        let controller = live::spawn_live_session(
            Arc::clone(&self.engine),
            Arc::clone(&self.target_speaker),
            session_id.clone(),
            request,
            status_channel,
            meter_channel,
            move || {
                live_sessions.lock().remove(&session_id_for_cleanup);
            },
        )?;

        self.live_sessions
            .lock()
            .insert(session_id.clone(), controller);
        Ok(LiveSessionHandle { session_id })
    }

    pub fn stop_live_monitor(&self, session_id: &str) -> AppResult<()> {
        let controller = self.live_sessions.lock().remove(session_id);
        match controller {
            Some(controller) => controller.stop(),
            None => Ok(()),
        }
    }

    fn profile_manifest_path(&self, profile_id: &str) -> PathBuf {
        self.speaker_profiles_dir.join(format!("{profile_id}.json"))
    }
}

fn resolve_speaker_profiles_dir(app: &AppHandle) -> AppResult<PathBuf> {
    let base = app.path().app_data_dir().map_err(|error| {
        AppError::message(format!("unable to resolve app data directory: {error}"))
    })?;
    Ok(base.join("speaker_profiles"))
}

fn sanitize_profile_filename(name: &str) -> String {
    let mut output = String::with_capacity(name.len().min(48));
    for character in name.chars() {
        if character.is_ascii_alphanumeric() {
            output.push(character.to_ascii_lowercase());
        } else if character == '-' || character == '_' {
            output.push(character);
        } else if !output.ends_with('_') {
            output.push('_');
        }
        if output.len() >= 48 {
            break;
        }
    }
    let trimmed = output.trim_matches('_').to_string();
    if trimmed.is_empty() {
        "speaker".to_string()
    } else {
        trimmed
    }
}

fn audio_duration_ms(frame_count: usize, sample_rate: u32) -> u64 {
    if sample_rate == 0 {
        return 0;
    }
    ((frame_count as f64 / sample_rate as f64) * 1000.0).round() as u64
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
