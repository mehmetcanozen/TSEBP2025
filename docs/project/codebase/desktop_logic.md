# Desktop Logic And UI Contract

The desktop UI is responsible for presenting model categories, output routing,
live-session controls, offline jobs, target-speaker workflows, and runtime
health. It should mirror the Rust command contract rather than inventing a
separate model story.

## Frontend Layers

| Layer | Responsibility |
| --- | --- |
| `desktop/src/lib/desktop-api.ts` | Typed wrapper around Tauri commands and fallback browser-only values. |
| `desktop/src/contexts/DesktopRuntimeContext.tsx` | Central state for categories, devices, virtual mic status, profiles, live status, jobs, and speaker settings. |
| `desktop/src/contexts/DesktopUiSurfaceContext.tsx` | Chooses the clean user UI or the dev/debug UI from `?ui=` or `VITE_DESKTOP_UI_SURFACE`. |
| `desktop/src/pages/Dashboard.tsx` | Surface router that renders the user dashboard by default or the dev dashboard when requested. |
| `desktop/src/pages/UserDashboard.tsx` | Clean task-based user UI for live, file render, speaker profiles, and status. |
| `desktop/src/pages/DevDashboard.tsx` | Task-based diagnostics console for Semantic Debug, Speaker Debug, Transmission, and Runtime/Devices. |
| `desktop/src/components/CategorySelector.tsx` | Category selection based on packaged model labels. |
| `desktop/src/components/RealTimeMode.tsx` | Compact live monitor controls in the app shell. |

## UI Surfaces

The desktop has two launchable surfaces:

- `user`: default product UI, selected by `VITE_DESKTOP_UI_SURFACE=user` or `?ui=user`.
- `dev`: diagnostics UI, selected by `VITE_DESKTOP_UI_SURFACE=dev` or `?ui=dev`.

`shared/scripts/start-desktop.ps1` writes the surface value before launching.
Normal launches use `user`; `-DevUi` uses `dev`.

The user surface keeps semantic live, speaker live, offline file processing,
speaker profiles, basic device readiness, and signal/status summaries. It hides
Debug WAV controls, Transmission Test, Loopback Monitor, raw provider/runtime
details, and calibration metrics.

The dev surface preserves those diagnostics for development and regression
checks, but it is still compartmentalized around the same task-navigation
pattern as the user UI. Debug WAV, recording output, routing, transmission, and
runtime/device inspection live in separate panels instead of one long vertical
debug page. It still uses the same `DesktopRuntimeContext`, so UI surface
selection does not create a second runtime or change suppression behavior.

## Tauri Command Surface

The UI uses commands declared in `desktop/src-tauri/src/commands.rs`:

- `get_model_categories`
- `get_hive15_presets`
- `list_audio_devices`
- `get_virtual_mic_status`
- `get_runtime_metrics`
- `get_target_speaker_runtime_info`
- speaker profile CRUD
- `start_offline_job` and `cancel_offline_job`
- `start_target_speaker_job`
- `start_live_monitor` and `stop_live_monitor`

The frontend should treat command return values as the source of display truth:
category names, runtime status, VB-CABLE readiness, target-speaker readiness,
and live-session metrics all come from Rust.

## State Model

`DesktopRuntimeContext` owns:

- selected categories and per-category aggressiveness
- current audio devices
- monitor vs Virtual Mic output mode
- live lookahead and Debug WAV settings
- runtime metrics and live status/meter events
- target-speaker engine, output mode, reference/profile state
- offline and target-speaker jobs

Two state boundaries matter:

- The monitor output device is a persisted user preference.
- The Virtual Mic sink is selected dynamically when Virtual Mic mode starts.

Mixing those two concepts causes confusing routing bugs where Virtual Mic
silently changes a user's normal monitor device.

## Category And Preset Display

The current category list comes from the active packaged model. With the default
Waveformer package, the desktop UI should show the 20 Waveformer product labels,
not exact-15 AudioSep labels and not old YAMNet aliases.

Presets are also package-provided. They are convenience groupings, not a
separate hard-coded taxonomy.

## Live Lifecycle

The live lifecycle is:

```text
load categories/devices/status
    -> user chooses mode, categories, device, output mode, lookahead
    -> startLive builds StartLiveMonitorRequest
    -> Tauri returns a session id
    -> status/meter channels update UI
    -> stopLive requests shutdown
    -> UI releases session state
```

The UI should disable controls that would invalidate a running session, such as
changing engine mode or output routing mid-stream.

## Target-Speaker UI

Target-speaker features are intentionally separate from semantic categories:

- speaker profiles store reference material and metadata
- TSExtract ONNX is the fast/default engine
- ClearVoice is a quality bundle for offline use
- live speaker suppression should require supported engine/device combinations

The target-speaker runtime info should surface whether the ONNX sidecar exists,
because missing external data makes the ONNX artifact unusable.

## Error And Health Messaging

Good desktop error messages should point to the failing boundary:

- missing model artifact
- missing `onnxruntime.dll`
- missing VB-CABLE
- wrong cable direction
- unsupported speaker engine for realtime
- Debug WAV path missing
- live session already running

Avoid presenting old model names as current troubleshooting steps. If the
runtime reports `waveformer_edge_100ms`, the UI/docs should use Waveformer
labels.
