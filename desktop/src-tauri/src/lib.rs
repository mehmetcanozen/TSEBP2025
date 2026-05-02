mod audio;
mod commands;
mod config;
mod engine;
mod error;
mod models;
mod state;

use std::sync::Arc;

use tauri::Manager;

use crate::state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let _ = env_logger::try_init();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let state = Arc::new(AppState::new(app.handle())?);
            let warm_state = Arc::clone(&state);
            app.manage(state);

            tauri::async_runtime::spawn_blocking(move || {
                if let Err(error) = warm_state.engine().warm() {
                    log::warn!("Desktop model warmup did not complete: {error}");
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_model_categories,
            commands::get_hive15_presets,
            commands::list_audio_devices,
            commands::get_virtual_mic_status,
            commands::get_runtime_metrics,
            commands::get_target_speaker_runtime_info,
            commands::list_speaker_profiles,
            commands::save_speaker_profile,
            commands::delete_speaker_profile,
            commands::start_offline_job,
            commands::start_target_speaker_job,
            commands::cancel_offline_job,
            commands::start_live_monitor,
            commands::stop_live_monitor
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
