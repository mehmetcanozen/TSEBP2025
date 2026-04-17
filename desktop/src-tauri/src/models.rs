use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelCategory {
    pub id: String,
    pub label: String,
    pub transient: bool,
    pub default_aggressiveness: f32,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Hive15Preset {
    pub id: String,
    pub name: String,
    pub description: String,
    pub categories: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AudioDevice {
    pub id: String,
    pub name: String,
    pub direction: AudioDeviceDirection,
    pub default: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum AudioDeviceDirection {
    Input,
    Output,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeMetrics {
    pub provider: String,
    pub available_providers: Vec<String>,
    pub warmed: bool,
    pub category_count: usize,
    pub active_live_sessions: usize,
    pub active_jobs: usize,
    pub model_path: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartOfflineJobRequest {
    pub input_path: String,
    pub output_path: String,
    pub categories: Vec<String>,
    pub aggressiveness: f32,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CancelOfflineJobRequest {
    pub job_id: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartLiveMonitorRequest {
    pub input_device_id: Option<String>,
    pub output_device_id: Option<String>,
    pub categories: Vec<String>,
    pub aggressiveness: f32,
    pub lookahead_ms: u32,
    pub record_output_path: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StopLiveMonitorRequest {
    pub session_id: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct JobHandle {
    pub job_id: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LiveSessionHandle {
    pub session_id: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OfflineProgressStage {
    Queued,
    Warming,
    Decoding,
    Processing,
    Writing,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OfflineProgressEvent {
    pub job_id: String,
    pub stage: OfflineProgressStage,
    pub progress: f32,
    pub eta_seconds: Option<f32>,
    pub message: Option<String>,
    pub output_path: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LiveSessionState {
    Starting,
    Running,
    Stopped,
    Error,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LiveStatusEvent {
    pub session_id: String,
    pub state: LiveSessionState,
    pub xruns: u32,
    pub provider: String,
    pub lookahead_ms: u32,
    pub inference_ms: Option<f32>,
    pub queue_depth_ms: Option<f32>,
    pub sample_rate: Option<u32>,
    pub input_device_id: Option<String>,
    pub output_device_id: Option<String>,
    pub message: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LiveMeterEvent {
    pub session_id: String,
    pub rms_in: f32,
    pub rms_out: f32,
    pub peak_in: f32,
    pub peak_out: f32,
    pub waveform_in: Vec<f32>,
    pub waveform_out: Vec<f32>,
    pub captured_frames: u64,
    pub rendered_frames: u64,
    pub timestamp_ms: u64,
}
