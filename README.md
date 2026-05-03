# Semantic Noise Mixer

Semantic Noise Mixer is a desktop-first audio suppression project built around
semantic detection, source separation, spectral masking, and profile-driven
control. The repository contains the active AI runtime, a Tauri desktop app,
setup scripts, tests, and local model layouts for multiple separator backends.

For detailed operator guidance, see the
[Master User Manual](docs/project/usage/USER_MANUAL.md).

## Current Scope

- Real-time and offline audio suppression tooling
- Multiple separator backends behind one runtime interface
- Profile-based control and backend-specific suppression settings
- Local model asset management under `ai/models/`
- Desktop app, command-line tools, tests, and research documentation

## Main Components

### YAMNet

YAMNet is the semantic detector used by the legacy detector-driven runtime. It
maps AudioSet classes into the higher-level categories defined under
`ai/ai_runtime/config/`.

### Waveformer

Waveformer is the default target-separation backend. In the current runtime it
works together with YAMNet and the legacy semantic category surface such as
`typing`, `traffic`, `wind`, `pets`, `alarm`, and `siren`.

### CodecSep

CodecSep is an optional separator backend for broader nuisance-removal and
research workflows. The current runtime supports fixed-category execution as the
main path, while retaining compatibility and legacy prompt-based modes for
debugging and comparison.

### AudioSepHive15Cat

AudioSepHive15Cat is an ONNX-based exact-15 backend with a smaller, explicit
category surface. It is intended for deterministic fixed-category suppression
such as `keyboard typing`, `alarm`, `wind`, `rain`, `music`, and
`background noise`.

### AudioSep

AudioSep is the optional open-vocabulary backend used by the `--universal`
workflow. It is intended for prompt-based extraction when a fixed category is
not sufficient.

### DeepFilterNet

DeepFilterNet provides the `--suppress-all` path for speech-focused cleanup
without category selection.

## Backend Summary

| Backend | Control surface | Typical use | Asset notes |
| --- | --- | --- | --- |
| `waveformer` | Legacy semantic categories plus YAMNet gating | Default desktop suppression | Uses local `Waveformer` and `YAMNet` assets |
| `codecsep` | Fixed product categories, Hive class IDs, or legacy prompt modes | Broader nuisance removal and research runtime | Expects local `ai/models/CodecSep/` assets |
| `audiosep_hive15cat` | Exact-15 fixed categories | Deterministic ONNX inference | Expects local `ai/models/AudioSepHive15Cat/` assets |
| `--universal` | Free-text prompts | Open-vocabulary extraction | Uses local `ai/models/AudioSep/` assets |
| `--suppress-all` | No category selection | Speech-focused cleanup | Uses the enhancement path rather than a separator backend |

## Repository Layout

```text
TSEBP2025/
|-- ai/
|   |-- ai_runtime/     # Active runtime: detection, suppression, separation, config
|   |-- data/           # Raw and processed audio
|   |-- export/         # ONNX and TFLite export helpers
|   |-- models/         # Local model trees and downloaded assets
|   |-- scripts/        # Setup, demos, diagnostics
|   |-- tests/          # Runtime and integration tests
|   `-- training/       # Training-side dependencies and related code
|-- desktop/
|   |-- src/            # React desktop UI
|   |-- src-tauri/      # Tauri host and native Rust audio runtime
|   `-- tests/          # Desktop-side tests
|-- docs/               # Project documentation and research notes
|-- shared/
|   `-- scripts/        # Shared environment setup
|-- pyproject.toml
`-- README.md
```

## Configuration Surfaces

The runtime now has multiple category surfaces. The most important config files
are:

- `ai/ai_runtime/config/yamnet_to_waveformer.yaml`
  Legacy semantic categories for detector-driven Waveformer suppression
- `ai/ai_runtime/config/audiosep_hive15cat_categories.yaml`
  Exact-15 categories for the AudioSepHive15Cat backend
- `ai/ai_runtime/config/product_to_hive_fixedset.json`
  Fixed-category product catalog for the current CodecSep runtime
- `ai/ai_runtime/config/category_to_codecsep.yaml`
  Legacy CodecSep prompt and slot compatibility mapping
- `ai/ai_runtime/config/default_profiles.json`
  Built-in profiles for default desktop usage
- `ai/ai_runtime/config/profile_schema.json`
  Schema for profile validation and backend-specific overrides

## Setup

### Recommended environment setup

From the repository root:

```powershell
.\shared\scripts\setup_env.ps1
.\.venv\Scripts\Activate.ps1
```

### Manual environment setup

```powershell
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
pip install -r desktop\requirements.txt
pip install -r ai\training\requirements.txt
```

If you need export tooling as well:

```powershell
pip install -r ai\export\requirements.txt
```

## Model Assets

Model directories under `ai/models/` are local assets and large checkpoints are
generally not intended to be committed to Git.

### Standard asset download

```powershell
python ai\scripts\setup\download_models.py
```

This downloader stores the standard Waveformer archive and YAMNet packages
under `ai/models/`.

### Optional AudioSep installation

```powershell
python ai\scripts\setup\install_audiosep.py
```

This clones the AudioSep repository into `ai/models/AudioSep/` and downloads the
required checkpoints.

### Current local model layout

- `ai/models/Waveformer/`
  Vendored Waveformer code plus `assets/config/`, `assets/checkpoints/`, and
  `assets/archives/`
- `ai/models/YAMNet/`
  Local SavedModel, metadata CSV, archives, and TFLite copy
- `ai/models/AudioSep/`
  Optional open-vocabulary AudioSep checkout and weights
- `ai/models/AudioSepHive15Cat/`
  Local exact-15 ONNX assets
- `ai/models/ClapSepHive15Cat/`
  Local companion assets for fixed-category experiments
- `ai/models/CodecSep/`
  Optional local CodecSep runtime tree when that backend is used

## Packaged Model Selection

Desktop, mobile backend, and the mobile app now resolve their suppression model
from shared manifests under `ai/models/`. There is no user-facing model picker:
we switch the active separator centrally so one model can be swapped for another
without rewriting each client.

- `ai/models/model_selection.json`
  Source of truth for packaged suppression models. `default_model_id` selects
  the repo-wide default and `models` maps model IDs to their package manifests.
- `ai/models/Waveformer/model_package.json`
  Declares the `waveformer_edge_100ms` package, including categories, presets,
  suppression strategy, and per-platform artifacts for desktop ONNX and Android
  ExecuTorch.
- `ai/models/AudioSepHive15Cat/model_package.json`
  Declares the `audiosep_hive15cat` package, including the exact-15 category
  surface and ONNX artifacts for desktop and Android.

Current packaged model IDs:

- `waveformer_edge_100ms`
  Default packaged model for the current edge-deployed suppression path
- `audiosep_hive15cat`
  Alternative packaged ONNX separator with the exact-15 category surface

The package manifests preserve model-specific capabilities instead of forcing
every backend into one inference shape. Each manifest declares its own runtime
kind, suppression strategy, timing, categories, presets, and platform-specific
artifacts, so Waveformer can stay a streaming target extractor while
AudioSepHive15Cat stays a category-based separator.

This shared selection layer is used in three places:

- Desktop
  Tauri bundles the shared selection manifest and the active model package from
  `ai/models/`
- Mobile app
  Android pre-packages the active model inside the app bundle so the edge model
  is available immediately on device
- Mobile backend
  The backend serves the same packaged model metadata and artifacts so mobile
  updates stay aligned with the app/runtime contract

### Switching the active packaged model

1. Add or update a model package manifest under `ai/models/<Model>/model_package.json`
1. Register that manifest in `ai/models/model_selection.json`
1. Change `default_model_id` to the model you want active across the project
1. For local development or CI overrides, set `TSEBP_ACTIVE_SUPPRESSION_MODEL`
   to one of the registered model IDs

Changing the active model here updates desktop, mobile packaging, and backend
bundle resolution together. There is still no end-user model chooser in the
product UI.

## Common Commands

### Batch processing with the default backend

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input ai\data\audio\raw\keyboard.wav `
  --output ai\data\audio\processed\keyboard_clean.wav `
  --suppress typing `
  --threshold 0.3
```

### Record from microphone and clean in real time

```powershell
python -m ai.ai_runtime.audio.recorder_cleaner `
  --duration 10 `
  --suppress typing,wind `
  --output ai\data\audio\processed\session_clean.wav
```

### Live real-time demo

```powershell
python ai\scripts\demos\demo_custom_realtime.py --suppress typing
python ai\scripts\demos\demo_custom_realtime.py --list-categories
python ai\scripts\demos\demo_custom_realtime.py --list-devices
```

### Virtual Mic developer setup

The desktop app's realtime path depends on a Windows recording endpoint that
other apps can select as a microphone. The project does not ship or create an
audio driver. For local development, install VB-CABLE from the official
VB-Audio site, then reboot if the installer asks for it:

```text
https://vb-audio.com/Cable/
```

After installation, Windows and the desktop app should show this pair:

```text
CABLE Input  - playback endpoint the desktop app writes cleaned audio into
CABLE Output - recording endpoint the target app selects as its microphone
```

On some Windows machines the playback side may appear under a name such as
`Speakers (2- VB-Audio Virtual Cable)` rather than literally `CABLE Input`.
That is still the VB-CABLE playback endpoint the desktop app should write into.

### Desktop live routing

Both desktop live modes now use the same routing model:

- `Live mic`: the desktop app captures the user's real microphone.
- `Debug WAV`: the desktop app uses a WAV file as if it were the live
  microphone, which is the most reliable one-machine validation path.

In both cases the processed stream is written into the VB-CABLE playback side,
and the target app should record from the VB-CABLE recording side:

```text
Semantic suppression:
Live mic or Debug WAV
-> semantic suppressor
-> CABLE Input / Speakers (VB-CABLE playback endpoint)
-> CABLE Output
-> target app microphone selection

Speaker suppression:
Live mic or Debug WAV
-> speaker suppressor using the active reference/profile
-> CABLE Input / Speakers (VB-CABLE playback endpoint)
-> CABLE Output
-> target app microphone selection
```

Important routing rule:

- In `Live mic` mode, choose a real microphone as the app input device.
- Do not choose `CABLE Output` as the app's own live input, because that feeds
  the virtual mic back into itself.

If VB-CABLE is not installed or Windows does not expose both sides as usable
audio endpoints, the desktop app still supports offline rendering. The realtime
VB-CABLE route stays unavailable until the playback side and recording side are
both detected.

### Desktop transmission test harness

The desktop app now includes a shared `Transmission Test` panel for both
semantic and speaker realtime modes. It exists to answer a different question
than local WAV recording:

- local recording tells us whether suppression itself is working
- transmission testing tells us how the already-processed VB-CABLE mic behaves
  when a browser-style network path captures it, transports it, and plays it
  back

This desktop v1 path is a same-machine WebRTC loopback benchmark. It is not a
real WAN benchmark and it does not replace testing in Zoom, Discord, Meet, or
other production apps.

Test route:

```text
desktop live suppression
-> CABLE Input / Speakers (VB-CABLE playback endpoint)
-> CABLE Output (VB-CABLE recording endpoint)
-> desktop Transmission Test browser capture
-> local WebRTC loopback
-> local speaker playback
```

How to use it:

1. Start a desktop live session first in either semantic or speaker mode.
2. Confirm the app shows a healthy VB-CABLE route.
3. Open the shared `Transmission Test` panel.
4. Click `Start loopback test`.
5. Leave `Play received audio` enabled if you want to hear the returned stream.
6. Click `Run ping calibration` when you want an explicit loopback-delay check.

Important behavior:

- the transmission tester captures `CABLE Output`, not your real microphone
- this means it validates the exact virtual microphone stream that another app
  would receive
- `Live mic` and `Debug WAV` both work, because both ultimately feed the same
  VB-CABLE route
- browser-side echo cancellation, noise suppression, and auto gain control are
  requested off so the test path does not "improve" the stream behind our backs

Metrics surfaced by the panel:

- app-side live metrics already produced by the Rust suppression runtime:
  - estimated live latency
  - queue depth
  - inference p95
  - realtime health
- WebRTC transport metrics from the loopback:
  - current / average / max round-trip time
  - inbound jitter
  - average jitter-buffer delay
  - packet loss rate
  - concealed samples and concealment events
  - send / receive bitrate
  - codec when exposed by stats
- derived estimates:
  - network loopback estimate
  - combined app + network estimate
  - calibrated loopback delay from the explicit ping pass

What `Run ping calibration` does:

- it injects a short calibration tone into the browser sender graph
- it listens for that tone on the received loopback stream
- it reports the measured return delay in milliseconds
- it only runs when requested and is not mixed into normal monitoring

### Test Virtual Mic with a WAV source

Use the desktop app's `Debug WAV` realtime source for the reliable one-machine
VB-CABLE test. The desktop app reads the WAV as live input, runs the normal
live suppression path, and sends the cleaned stream to VB-CABLE. This does not
require a second virtual cable pair.

Start the desktop app:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
$env:Path += ";$env:USERPROFILE\.cargo\bin"
npm run tauri:dev
```

This is the tested route:

```text
desktop Debug WAV realtime source
-> desktop live suppression
-> CABLE Input
-> CABLE Output
-> target app microphone selection
```

For the barking sample, set the desktop debug WAV path to:

```text
C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav
```

Desktop live settings:

```text
Realtime source: Debug WAV
VB-CABLE sink: CABLE Input (VB-Audio Virtual Cable) or Speakers (VB-Audio Virtual Cable)
Debug WAV path: C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav
Category: dog barking
```

Start the session, then record from this microphone in the target app:

```text
CABLE Output (VB-Audio Virtual Cable)
```

This test does not use speakers, a headset microphone, or a second cable pair.

If the app says VB-CABLE is missing, install VB-CABLE, reboot if prompted, then
click **Refresh devices** in the desktop app. If the target app does not see
`CABLE Output`, open Windows Sound settings and confirm the VB-CABLE recording
device is enabled.

The Python feeder remains available for cable-routing checks. It plays a WAV
into a virtual cable playback endpoint and does not run suppression. Do not
use it for the full one-cable Virtual Mic validation path above.

```powershell
python -m ai.scripts.demos.virtual_mic_streamer --list-devices
python -m ai.scripts.demos.virtual_mic_streamer --input C:\path\to\test.wav --device-name "CABLE Input"
```

### Fixed-category CodecSep example

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input ai\data\audio\raw\speech_siren.wav `
  --output ai\data\audio\processed\speech_siren_codecsep.wav `
  --separator-backend codecsep `
  --codecsep-product-category keyboard_typing `
  --codecsep-product-category siren `
  --output-noise
```

### Exact-15 AudioSepHive15Cat example

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input ai\data\audio\raw\speech_alarm.wav `
  --output ai\data\audio\processed\speech_alarm_hive15.wav `
  --separator-backend audiosep_hive15cat `
  --suppress "keyboard typing,alarm"
```

### Open-vocabulary AudioSep example

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input ai\data\audio\raw\speech_boat.wav `
  --output ai\data\audio\processed\speech_boat_universal.wav `
  --universal "boat engine, water noise"
```

### Mobile app on Android emulator

The mobile app lives in `mobile-part/` and the mobile API lives in
`mobile-backend/`. The app is an Expo development-client/native Android build
because it uses native audio and model-runtime modules. It cannot run in the
standard Expo Go app.

Use two terminals: one for the FastAPI backend and one for the mobile app.

#### 1. Prepare the mobile backend once

Create `mobile-backend/.env` if it does not already exist:

```env
DATABASE_URL=sqlite:///./audioapp.db
SECRET_KEY=dev-local-secret-change-me
DEBUG=True
MODELS_DIR=./models_store
```

Install backend dependencies from `mobile-backend/`:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

`onnxruntime` is required by the `/separation` route and is listed in
`mobile-backend/requirements.txt`.

#### 2. Start the mobile backend

From `mobile-backend/`:

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Leave this terminal open. Confirm the API is reachable from Windows:

```text
http://localhost:8000/docs
http://localhost:8000/
```

#### 3. Start an Android emulator

Use Android Studio Device Manager and start an emulator, for example:

```text
Medium_Phone_API_36.1
```

If running from PowerShell, make sure Android SDK tools are on PATH for that
terminal:

```powershell
$env:Path = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:Path"
```

The Android emulator reaches the Windows host through `10.0.2.2`, not
`localhost`.

#### 4. Configure the mobile app for the emulator

Create `mobile-part/.env` if it does not already exist:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
```

If Gradle cannot find the Android SDK, create
`mobile-part/android/local.properties`:

```properties
sdk.dir=C:\\Users\\omehm\\AppData\\Local\\Android\\Sdk
```

These files are local machine settings and are intentionally ignored by Git.

#### 5. Build and run the mobile app

Open a second terminal and run:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
npm run android
```

The first run builds the native Android app, so it can take a while. A successful
build should end with `BUILD SUCCESSFUL`, then install/open the app named `SNC`
on the emulator.

If the build succeeds but the app does not open, start the Expo dev-client
server from `mobile-part/`:

```powershell
npx expo start --dev-client
```

Then press `a` to open the installed Android app.

#### 6. Basic checks

- Keep the backend terminal running while using the mobile app.
- In the app, allow microphone permission.
- If login/register or model checks work, the backend terminal should show
  requests such as `/auth/register`, `/auth/login`, `/model/latest`, or
  `/separation/separate`.
- If the app cannot reach the backend, confirm `EXPO_PUBLIC_API_URL` is
  `http://10.0.2.2:8000` and that `http://localhost:8000/docs` still works on
  Windows.
- If emulator recording is silent, check the emulator microphone setting in
  Android Emulator extended controls.

#### 7. Test mobile live suppression with `speech_barking.wav`

Use this workflow when you want the mobile app to receive a local WAV file as
live microphone input through VB-CABLE. It is intended for the Android emulator
on the Windows host. The app workflow is the same on a physical phone, but
changing the Windows default recording device only affects the emulator, not a
real phone microphone.

The signal path is:

```text
speech_barking.wav
-> CABLE Input
-> CABLE Output
-> Android emulator host microphone
-> mobile app live suppression
-> saved recording
```

VB-CABLE exposes two endpoints:

```text
CABLE Input  - playback endpoint that receives the WAV stream
CABLE Output - recording endpoint that Windows and the emulator use as a mic
```

Use three terminals/windows while testing.

Terminal 1: stream the WAV into VB-CABLE from the repository root:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\mobile-backend\venv\Scripts\python.exe -m ai.scripts.demos.virtual_mic_streamer --input C:\SoftwareProjects\TSEBP2025\ai\data\audio\raw\speech_barking.wav --device-name "CABLE Input"
```

The streamer loops the file. Stop it with `Ctrl+C` when you are done.

Terminal 2: start the mobile backend:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Windows sound settings: open the Recording tab:

```powershell
Start-Process control.exe -ArgumentList 'mmsys.cpl,,1'
```

In the Recording tab, set `CABLE Output (VB-Audio Virtual Cable)` as the default
recording device. Write down the previous default device first. After the test,
switch the default recording device back to the original microphone.

In the Android Emulator, open **Extended Controls -> Microphone** and enable
host microphone input. The emulator should now receive the audio coming through
`CABLE Output`.

In the mobile app:

1. Make sure the recording toggle is enabled.
1. Choose the target category `dog`.
1. Tap **Tap to start listening**.
1. Let the sample play for a few seconds.
1. Tap stop to finish the session and save the processed WAV.
1. Open the app's recordings/library view to play or locate the saved output.

The active mobile Waveformer package exposes barking as `dog`, not
`dog barking`. If the app hears silence, check that the streamer is still
running, Windows input is set to `CABLE Output`, and the emulator microphone is
using host audio input.

### Desktop UI

```powershell
cd desktop
npm run tauri:dev
```

## Tests

Run the automated test suites with:

```powershell
python -m pytest ai\tests\runtime desktop\tests
```

Additional diagnostics and manual smoke tools live under `ai/scripts/diagnostics/`
and `ai/tests/manual/`.

## Notes

- Waveformer is detector-driven and uses the YAMNet-based semantic mapping.
- AudioSepHive15Cat is manual-first and uses its own exact-15 category surface.
- CodecSep fixed-category mode uses `product_to_hive_fixedset.json` rather than
  the older prompt-routing file.
- Some backends require local model trees that are not provisioned by the base
  downloader.

## Documentation

- [Master User Manual](docs/project/usage/USER_MANUAL.md)
- [Model Details](docs/project/knowledge/model_details.md)
- [Semantic Mappings](docs/project/knowledge/semantic_mappings.md)
- [Architecture Overview](docs/project/architecture/overview.md)
