use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelCategory {
    pub id: String,
    pub label: String,
    pub transient: bool,
    #[serde(alias = "default_aggressiveness")]
    pub default_aggressiveness: f32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
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
    pub virtual_cable: Option<VirtualCableEndpoint>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum AudioDeviceDirection {
    Input,
    Output,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct VirtualCableEndpoint {
    pub provider: String,
    pub role: VirtualCableEndpointRole,
    pub paired_device_name: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum VirtualCableEndpointRole {
    Playback,
    Recording,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct VirtualMicStatus {
    pub provider: String,
    pub installed: bool,
    pub playback_device_id: Option<String>,
    pub playback_device_name: Option<String>,
    pub recording_device_name: Option<String>,
    pub setup_url: String,
    pub message: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeMetrics {
    pub provider: String,
    pub available_providers: Vec<String>,
    pub warmed: bool,
    pub model_id: String,
    pub model_family: String,
    pub display_name: String,
    pub suppression_strategy: String,
    pub runtime_kind: String,
    pub category_count: usize,
    pub active_live_sessions: usize,
    pub active_jobs: usize,
    pub model_path: Option<String>,
    pub runtime_metadata_paths: Vec<String>,
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
    #[serde(default)]
    pub output_mode: LiveOutputMode,
    pub debug_input_path: Option<String>,
    pub categories: Vec<String>,
    pub aggressiveness: f32,
    pub lookahead_ms: u32,
    pub record_output_path: Option<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub enum LiveOutputMode {
    Monitor,
    VirtualMic,
}

impl Default for LiveOutputMode {
    fn default() -> Self {
        Self::Monitor
    }
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
    pub output_mode: LiveOutputModeEvent,
    pub lookahead_ms: u32,
    pub inference_ms: Option<f32>,
    pub queue_depth_ms: Option<f32>,
    pub estimated_latency_ms: Option<f32>,
    pub realtime_health: LiveRealtimeHealth,
    pub sample_rate: Option<u32>,
    pub input_device_id: Option<String>,
    pub output_device_id: Option<String>,
    pub output_device_name: Option<String>,
    pub message: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum LiveOutputModeEvent {
    Monitor,
    VirtualMic,
}

impl From<&LiveOutputMode> for LiveOutputModeEvent {
    fn from(value: &LiveOutputMode) -> Self {
        match value {
            LiveOutputMode::Monitor => Self::Monitor,
            LiveOutputMode::VirtualMic => Self::VirtualMic,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum LiveRealtimeHealth {
    Idle,
    Ok,
    Warning,
    Overloaded,
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

#[cfg(test)]
mod tests {
    use super::ModelCategory;

    #[test]
    fn model_category_deserializes_packaged_snake_case_fields() {
        let category: ModelCategory = serde_json::from_str(
            r#"{
                "id": "speech",
                "label": "speech",
                "transient": false,
                "default_aggressiveness": 1.4
            }"#,
        )
        .expect("packaged model categories should deserialize");

        assert_eq!(category.id, "speech");
        assert_eq!(category.default_aggressiveness, 1.4);
    }
}
