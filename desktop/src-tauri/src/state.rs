use std::{
    collections::HashMap,
    path::Path,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Instant,
};

use parking_lot::Mutex;
use tauri::{ipc::Channel, AppHandle};
use uuid::Uuid;

use crate::{
    audio::{devices, io, live},
    config::AssetCatalog,
    engine::SharedEngine,
    error::{AppError, AppResult},
    models::{
        AudioDevice, JobHandle, LiveMeterEvent, LiveSessionHandle, LiveStatusEvent,
        OfflineProgressEvent, OfflineProgressStage, RuntimeMetrics, StartLiveMonitorRequest,
        StartOfflineJobRequest,
    },
};

struct OfflineJobControl {
    cancel_flag: Arc<AtomicBool>,
}

pub struct AppState {
    engine: Arc<SharedEngine>,
    offline_jobs: Arc<Mutex<HashMap<String, OfflineJobControl>>>,
    live_sessions: Arc<Mutex<HashMap<String, Arc<live::LiveSessionControl>>>>,
}

impl AppState {
    pub fn new(app: &AppHandle) -> AppResult<Self> {
        let assets = AssetCatalog::resolve(app)?;
        let engine = Arc::new(SharedEngine::new(assets)?);
        Ok(Self {
            engine,
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

    pub fn runtime_metrics(&self) -> AppResult<RuntimeMetrics> {
        let runtime = self.engine.runtime_info();
        Ok(RuntimeMetrics {
            provider: runtime.provider,
            available_providers: runtime.available_providers,
            warmed: runtime.warmed,
            category_count: self.engine.categories().len(),
            active_live_sessions: self.live_sessions.lock().len(),
            active_jobs: self.offline_jobs.lock().len(),
            model_path: runtime.model_path,
        })
    }

    pub async fn start_offline_job(
        &self,
        _app: AppHandle,
        request: StartOfflineJobRequest,
        progress_channel: Channel<OfflineProgressEvent>,
    ) -> AppResult<JobHandle> {
        self.engine.validate_selected_categories(&request.categories)?;

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

    pub fn cancel_offline_job(&self, job_id: &str) -> AppResult<()> {
        let jobs = self.offline_jobs.lock();
        let Some(job) = jobs.get(job_id) else {
            return Err(AppError::message(format!("offline job '{job_id}' was not found")));
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
        self.engine.validate_selected_categories(&request.categories)?;

        let session_id = Uuid::new_v4().to_string();
        let live_sessions = Arc::clone(&self.live_sessions);
        let session_id_for_cleanup = session_id.clone();
        let controller = live::spawn_live_session(
            Arc::clone(&self.engine),
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
}
