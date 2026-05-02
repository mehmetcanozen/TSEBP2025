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
    pub model_sample_rate: u32,
    pub chunk_samples: Option<usize>,
    pub preferred_live_hop_ms: f32,
    pub validation_status: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TargetSpeakerRuntimeInfo {
    pub model_id: String,
    pub display_name: String,
    pub runtime_kind: String,
    pub default_engine: TargetSpeakerEngine,
    pub available_engines: Vec<TargetSpeakerEngine>,
    pub model_sample_rate: u32,
    pub mixture_samples: usize,
    pub reference_samples: usize,
    pub validation_status: String,
    pub runtime_metadata_paths: Vec<String>,
    pub bundle_manifest_path: Option<String>,
    pub tsextract_onnx_path: Option<String>,
    pub clearvoice_bundle_path: Option<String>,
    pub onnx_sidecar_present: bool,
    pub clearvoice_ready: bool,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveSpeakerProfileRequest {
    pub name: String,
    pub reference_path: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeleteSpeakerProfileRequest {
    pub profile_id: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SpeakerProfile {
    pub id: String,
    pub name: String,
    pub reference_path: String,
    pub source_path: Option<String>,
    pub sample_rate: u32,
    pub duration_ms: u64,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartOfflineJobRequest {
    pub input_path: String,
    pub output_path: String,
    pub categories: Vec<String>,
    pub aggressiveness: f32,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TargetSpeakerEngine {
    TsextractOnnx,
    ClearvoiceBundle,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TargetSpeakerOutputMode {
    RemoveTarget,
    ExtractTarget,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartTargetSpeakerJobRequest {
    pub input_path: String,
    pub reference_path: String,
    pub output_path: String,
    pub engine: TargetSpeakerEngine,
    pub output_mode: TargetSpeakerOutputMode,
    pub removal_scale: f32,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CancelOfflineJobRequest {
    pub job_id: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartLiveMonitorRequest {
    #[serde(default)]
    pub processing_mode: LiveProcessingMode,
    pub input_device_id: Option<String>,
    pub output_device_id: Option<String>,
    #[serde(default)]
    pub output_mode: LiveOutputMode,
    pub debug_input_path: Option<String>,
    #[serde(default)]
    pub categories: Vec<String>,
    pub aggressiveness: f32,
    pub lookahead_ms: u32,
    pub record_output_path: Option<String>,
    pub speaker_reference_path: Option<String>,
    pub speaker_engine: Option<TargetSpeakerEngine>,
    pub speaker_output_mode: Option<TargetSpeakerOutputMode>,
    pub speaker_removal_scale: Option<f32>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub enum LiveProcessingMode {
    SemanticSuppression,
    SpeakerSuppression,
}

impl Default for LiveProcessingMode {
    fn default() -> Self {
        Self::SemanticSuppression
    }
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
    pub inference_ms_p50: Option<f32>,
    pub inference_ms_p95: Option<f32>,
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
    use super::{LiveProcessingMode, ModelCategory, StartLiveMonitorRequest};

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

    #[test]
    fn live_request_defaults_to_semantic_processing() {
        let request: StartLiveMonitorRequest = serde_json::from_str(
            r#"{
                "inputDeviceId": null,
                "outputDeviceId": null,
                "outputMode": "monitor",
                "debugInputPath": null,
                "categories": ["speech"],
                "aggressiveness": 1.0,
                "lookaheadMs": 150,
                "recordOutputPath": null
            }"#,
        )
        .expect("legacy live monitor payloads should keep working");

        assert_eq!(
            request.processing_mode,
            LiveProcessingMode::SemanticSuppression
        );
    }
}
