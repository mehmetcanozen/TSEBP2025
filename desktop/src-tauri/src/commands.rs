use std::sync::Arc;

use tauri::{ipc::Channel, AppHandle, State};

use crate::{
    models::{
        CancelOfflineJobRequest, Hive15Preset, JobHandle, LiveMeterEvent, LiveSessionHandle,
        LiveStatusEvent, ModelCategory, OfflineProgressEvent, RuntimeMetrics, StartLiveMonitorRequest,
        StartOfflineJobRequest, StopLiveMonitorRequest,
    },
    state::AppState,
};

type SharedState<'a> = State<'a, Arc<AppState>>;

#[tauri::command]
pub fn get_model_categories(state: SharedState<'_>) -> Result<Vec<ModelCategory>, String> {
    Ok(state.engine().categories().to_vec())
}

#[tauri::command]
pub fn get_hive15_presets(state: SharedState<'_>) -> Result<Vec<Hive15Preset>, String> {
    Ok(state.engine().presets().to_vec())
}

#[tauri::command]
pub fn list_audio_devices(state: SharedState<'_>) -> Result<Vec<crate::models::AudioDevice>, String> {
    state.list_audio_devices().map_err(|error| error.to_string())
}

#[tauri::command]
pub fn get_virtual_mic_status(state: SharedState<'_>) -> Result<crate::models::VirtualMicStatus, String> {
    state.get_virtual_mic_status().map_err(|error| error.to_string())
}

#[tauri::command]
pub fn get_runtime_metrics(state: SharedState<'_>) -> Result<RuntimeMetrics, String> {
    state.runtime_metrics().map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn start_offline_job(
    app: AppHandle,
    state: SharedState<'_>,
    request: StartOfflineJobRequest,
    progress_channel: Channel<OfflineProgressEvent>,
) -> Result<JobHandle, String> {
    state
        .start_offline_job(app, request, progress_channel)
        .await
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn cancel_offline_job(state: SharedState<'_>, request: CancelOfflineJobRequest) -> Result<(), String> {
    state.cancel_offline_job(&request.job_id).map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn start_live_monitor(
    state: SharedState<'_>,
    request: StartLiveMonitorRequest,
    status_channel: Channel<LiveStatusEvent>,
    meter_channel: Channel<LiveMeterEvent>,
) -> Result<LiveSessionHandle, String> {
    state
        .start_live_monitor(request, status_channel, meter_channel)
        .await
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn stop_live_monitor(state: SharedState<'_>, request: StopLiveMonitorRequest) -> Result<(), String> {
    state
        .stop_live_monitor(&request.session_id)
        .map_err(|error| error.to_string())
}
