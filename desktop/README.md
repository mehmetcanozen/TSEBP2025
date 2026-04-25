# Semantic Noise Suppression Desktop

Windows desktop client for the Semantic Noise Suppression project.

This folder now contains a full desktop application built with:

- React + Vite + TypeScript for the UI
- Tauri v2 for the desktop host
- Rust for the native audio runtime
- ONNX Runtime for the bundled `AudioSepHive15Cat` inference path

The desktop app is self-contained at runtime. It does not ship Python as part of the app. The Python code under `../ai/` remains the reference implementation and source of model/config assets.

## Purpose

The desktop app provides two main flows:

1. Offline suppression
   Give the app an audio file, choose one or more exact-15 categories, and export a cleaned WAV.
2. Live monitor suppression
   Capture the user's microphone, suppress the selected categories in a buffered native pipeline, and play the cleaned result back to a selected output device or a VB-CABLE virtual microphone route.

The current desktop runtime is Windows-only. It does not ship or develop a virtual audio driver; virtual microphone routing uses an optional existing VB-CABLE installation.

## What Was Added

This project started as a React desktop UI shell. The main addition in this pass was the full native desktop runtime and the bridge between the UI and the model.

Major additions:

- Added `src-tauri/` and converted `desktop/` into a Tauri v2 application
- Added a native Rust backend for:
  - exact-15 category loading
  - ONNX model session management
  - offline audio decoding and WAV export
  - live microphone capture and monitor playback
  - optional VB-CABLE virtual microphone routing
  - Wiener decision-directed masking
  - desktop command/state orchestration
- Added model-backed frontend integration:
  - exact-15 category picker
  - Hive15 preset strip
  - live device controls
  - offline job progress
  - live RMS/peak/waveform telemetry
  - runtime health metrics
- Bundled desktop resources:
  - `AudioSepHive15Cat` model files
  - exact-15 category config
  - default profile config
  - ONNX Runtime DLLs

## Desktop Architecture

The desktop app is split into two layers.

### 1. Frontend

The frontend lives in `src/` and is responsible for:

- routing and auth shell
- dashboard and flyout UI
- category and preset selection
- file pickers and device selectors
- invoking native commands
- rendering live/offline telemetry

Important frontend pieces:

- `src/App.tsx`
  Root app, auth shell, display mode shell, desktop runtime provider
- `src/contexts/DesktopRuntimeContext.tsx`
  Frontend state manager for categories, presets, devices, live/offline job state, and telemetry
- `src/lib/desktop-api.ts`
  Type-safe bridge between React and Tauri commands/channels
- `src/pages/Dashboard.tsx`
  Main desktop processing dashboard
- `src/components/RealTimeMode.tsx`
  Compact live-mode / flyout experience
- `src/components/desktop/*`
  Exact-15 category, preset, and signal meter UI components

### 2. Native backend

The native backend lives in `src-tauri/` and is responsible for:

- loading the ONNX model and config assets
- running exact-15 separation
- applying fast Rust-side masking
- enumerating audio devices
- running offline jobs
- running live buffered microphone suppression
- sending telemetry back to the frontend

Important backend pieces:

- `src-tauri/src/lib.rs`
  Tauri app bootstrap, plugin registration, command registration, warmup
- `src-tauri/src/commands.rs`
  Public Tauri commands exposed to the UI
- `src-tauri/src/state.rs`
  App state, job/session lifecycle, command handlers
- `src-tauri/src/config.rs`
  Resource resolution and config loading
- `src-tauri/src/models.rs`
  Shared request/response/event models for Tauri IPC
- `src-tauri/src/audio/io.rs`
  Symphonia decode and float32 WAV export
- `src-tauri/src/audio/devices.rs`
  Device enumeration, VB-CABLE detection, and stream config resolution
- `src-tauri/src/audio/live.rs`
  Buffered live monitor pipeline
- `src-tauri/src/engine/mod.rs`
  Shared inference engine and offline/live suppression processor
- `src-tauri/src/engine/dsp.rs`
  Resampling helpers, overlap-add, Wiener DD masking, meters

## Model And Config Sources

The desktop runtime uses the project assets under `../ai/`.

Primary assets:

- `../ai/models/AudioSepHive15Cat/frozensep_hive_15cat.onnx`
- `../ai/models/AudioSepHive15Cat/categories_15.txt`
- `../ai/ai_runtime/config/audiosep_hive15cat_categories.yaml`
- `../ai/ai_runtime/config/default_profiles.json`

These are bundled into the desktop app through `src-tauri/tauri.conf.json`.

The exact-15 categories are loaded from the shared config and are the authoritative UI surface:

- speech
- music
- dog barking
- car engine
- footsteps
- rain
- wind
- keyboard typing
- phone ringing
- crowd noise
- bird singing
- water flowing
- door knocking
- alarm
- background noise

Hive15 presets are also loaded from the shared config so the desktop app stays aligned with the runtime defaults.

## Processing Design

### Offline flow

Offline processing currently works like this:

1. Decode the source file with `symphonia`
2. Preserve original sample rate and channel count in memory
3. Convert to mono for model inference
4. Resample to `32 kHz`
5. Run exact-15 ONNX separation in `5.0 s` windows with `1.0 s` overlap
6. Sum the selected unwanted categories
7. Resample the unwanted estimate back to the original sample rate
8. Apply Wiener DD masking in Rust
9. For stereo or multi-channel audio, project removed mono energy back to the original channel layout
10. Write a `32-bit float WAV`

For longer files, the desktop runtime also uses outer overlap-add chunking with:

- `10.0 s` outer chunks
- `1.0 s` outer overlap

This keeps memory bounded and avoids audible chunk seams.

### Live flow

The live path is intentionally buffered instead of trying to run model inference inside an audio callback.

Current live design:

- capture mic input in a native Rust stream
- convert callback frames to mono and push into a lock-free ring buffer
- maintain a rolling `5.0 s` context
- run Waveformer suppression every `100 ms` when the streaming model is active
- push the latest cleaned hop into the render buffer
- play cleaned output to the selected monitor device or `CABLE Input (VB-Audio Virtual Cable)`
- optionally record the cleaned live signal to a WAV file

This is designed to avoid adding avoidable latency in the desktop glue. The model itself is still the main bottleneck.

### Virtual microphone flow

Virtual Mic mode depends on VB-CABLE because Windows applications need a capture endpoint to see audio as a microphone. The app detects the VB-CABLE playback endpoint, renders cleaned audio into `CABLE Input`, and tells the user to select `CABLE Output` as the microphone in the target app.

This is intentionally not a driver, APO, or global microphone interceptor. If VB-CABLE is missing, Virtual Mic mode stays disabled and local monitor mode remains available.

Developer setup:

1. Install VB-CABLE from the official VB-Audio site:

```text
https://vb-audio.com/Cable/
```

2. Reboot if the installer asks for it.
3. Start the desktop app and click **Refresh devices**.
4. Confirm the app reports VB-CABLE ready.

Expected Windows device pair:

```text
CABLE Input  - playback endpoint the desktop app writes cleaned audio into
CABLE Output - recording endpoint the target app selects as its microphone
```

Without VB-CABLE, developers can still test offline rendering and live **Listen locally** mode. They cannot validate the target-app microphone handoff until `CABLE Input` and `CABLE Output` are available.

### Testing Virtual Mic with a WAV source

For the reliable one-machine Virtual Mic test, use the desktop app's **Debug WAV mic source** control in live mode. This makes the desktop live pipeline read a WAV as if it were microphone input while still rendering the cleaned result to VB-CABLE Virtual Mic output. This test needs one VB-CABLE pair and does not need a second virtual cable.

Start the app from PowerShell:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
$env:Path += ";$env:USERPROFILE\.cargo\bin"
npm run tauri:dev
```

Tested route:

```text
desktop Debug WAV mic source
-> desktop live suppression
-> CABLE Input
-> CABLE Output
-> target app microphone selection
```

Set the debug WAV path to a source file such as:

```text
C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav
```

Use these live settings:

```text
Mode: Virtual mic
Clean audio sink: CABLE Input (VB-Audio Virtual Cable)
Debug WAV mic source: ON
Debug WAV path: C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav
Category: dog barking
```

Start the session, then record from `CABLE Output (VB-Audio Virtual Cable)` in the target app. This validates the full desktop Virtual Mic route with one VB-CABLE pair and without speakers, headset microphone bleed, or a second virtual cable.

If the target app does not list `CABLE Output`, open Windows Sound settings and confirm the VB-CABLE recording endpoint is enabled. If the desktop app does not report VB-CABLE ready, reinstall or repair VB-CABLE, reboot if prompted, then click **Refresh devices**.

The Python reference side also includes a pure feeder for lower-level cable playback checks. It plays a WAV into a virtual cable playback endpoint and does not run suppression, inference, or cleanup itself:

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai.scripts.demos.virtual_mic_streamer --list-devices
python -m ai.scripts.demos.virtual_mic_streamer --input C:\path\to\test.wav --device-name "CABLE Input"
```

Do not use the Python feeder for the full one-cable Virtual Mic validation path above; use the in-app Debug WAV mic source.

## Public Native API

The frontend talks to the native backend through Tauri commands and channels.

Commands:

- `get_model_categories`
- `get_hive15_presets`
- `list_audio_devices`
- `get_virtual_mic_status`
- `get_runtime_metrics`
- `start_offline_job`
- `cancel_offline_job`
- `start_live_monitor`
- `stop_live_monitor`

Streaming channel events:

- offline progress
- live status
- live meters

Raw audio is not sent through JSON IPC. The UI only receives compact telemetry and job/session state.

## Running The Desktop App

From a PowerShell terminal:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
$env:Path += ";$env:USERPROFILE\.cargo\bin"
npm run tauri:dev
```

Notes:

- `cargo` may not be on the terminal `PATH` yet, so the extra line above is often needed
- `src-tauri/runtime/` already contains:
  - `onnxruntime.dll`
  - `onnxruntime_providers_shared.dll`
- the app expects Windows with WebView2 available

## Building The Desktop App

To create a packaged Windows build:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
$env:Path += ";$env:USERPROFILE\.cargo\bin"
npm run tauri:build
```

The Tauri build is configured to generate an NSIS installer.

## Frontend Commands

Useful frontend scripts:

- `npm run dev`
  Start only the Vite frontend
- `npm run tauri:dev`
  Start the full desktop app in development mode
- `npm run build`
  Build the frontend bundle
- `npm run tauri:build`
  Build the packaged desktop application
- `npm test`
  Run Vitest

## Validation Status

Current checks that pass:

- `npm run build`
- `npm test`
- `cargo check`
- `cargo test --lib`

The Rust unit tests currently cover:

- overlap window behavior
- linear resampling sanity
- stereo removed-audio projection shape
- real-FFT-safe masking output
- outer chunk overlap sizing

## Current Limitations

This is an important section because the desktop app is functional, but not everything is final yet.

Current boundaries:

- Windows-only runtime
- virtual microphone routing requires a user-installed VB-CABLE device
- no bundled or custom virtual microphone driver
- CPU-first ONNX inference
- live processing is buffered; Waveformer uses a lower-latency voice-chat profile, but device and model timing still matter
- multi-category live suppression can become slow on CPU
- live path currently uses CPAL-based native streams rather than a fully hand-written `IAudioClient3` path

Performance reality on the current development machine:

- `1` category on a `5 s` window is comfortably below a `1 s` hop
- `3+` categories are much heavier and move toward or beyond the comfort zone for live CPU-only operation
- offline rendering is the most reliable mode right now

## Suggested Usage

### Best current use case

Use the desktop app first for:

- offline cleanup of recorded files
- focused live suppression with a very small category set
- demoing the exact-15 Hive15 desktop workflow

### When to keep category count small

For live mode, prefer:

- `1` category
- maybe `2` categories, depending on the machine

Examples:

- `keyboard typing`
- `background noise`
- `alarm`

Avoid selecting many categories at once in live mode unless you are specifically testing quality rather than latency.

## Relationship To The Python Runtime

The Python runtime under `../ai/` is still important.

It remains the:

- reference implementation
- source of shared model/config assets
- benchmarking baseline
- parity target for future desktop tuning

The desktop runtime does not replace the Python runtime as the research/reference layer. It packages the exact-15 flow into a native Windows desktop app.

## Folder Map

High-level map:

```text
desktop/
|- public/                    Static web assets
|- src/                       React frontend
|  |- components/desktop/     Desktop-specific UI controls
|  |- contexts/               Auth, display mode, desktop runtime state
|  |- lib/desktop-api.ts      Tauri bridge
|  |- pages/                  App screens
|  `- test/                   Frontend tests
|- src-tauri/                 Native desktop host and audio runtime
|  |- capabilities/           Tauri capability config
|  |- icons/                  Desktop app icons
|  |- runtime/                ONNX Runtime DLLs
|  |- src/audio/              Audio device, I/O, live processing
|  |- src/engine/             ONNX + DSP engine
|  `- tauri.conf.json         Tauri app configuration and bundled resources
|- package.json               Frontend and Tauri scripts
`- README.md                  This file
```

## Next Recommended Improvements

If the team continues the desktop runtime, the highest-value next steps are:

1. Add a GPU path such as DirectML for Windows inference
2. Benchmark and tune live mode with category-count-aware scheduling
3. Improve live device recovery and hot-plug handling
4. Add stronger parity tests against the Python reference runtime
5. Consider a lower-latency Windows-specific stream path if live mode becomes a top priority

## Summary

The desktop folder is now more than a UI prototype. It is a real Windows desktop application with:

- a Tauri host
- a native Rust audio runtime
- exact-15 AudioSep ONNX integration
- fast masking and overlap-add reconstruction
- offline export
- buffered live mic monitoring
- shared config-driven categories and presets

The project is in a strong state for offline use today and in a workable state for buffered live experimentation on Windows.
