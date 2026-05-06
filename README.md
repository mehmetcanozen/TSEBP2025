# Semantic Noise Mixer

Semantic Noise Mixer is a local-first semantic audio suppression project for
Windows desktop, Android, and Python research workflows. The active product
path uses packaged model artifacts under `ai/models/Exports`, with
`waveformer_edge_100ms` as the default semantic suppressor.

The root README is intentionally short. It explains what the repository is,
where the major pieces live, and which document to open next.

## Current status

| Area | Current path |
| --- | --- |
| Default semantic model | `waveformer_edge_100ms` |
| Desktop runtime | Tauri, Rust audio, ONNX Runtime CPU, optional VB-CABLE virtual mic |
| Android runtime | On-device Waveformer ORT, ONNX Runtime Android CPU, Oboe/AAudio first with Kotlin fallback |
| Mobile backend | Generic FastAPI backend for auth, history, and devices only |
| Model artifacts | Restored from the portable `ai/models/Exports` bundle, not committed to Git |
| Historical paths | Native UNet, TFLite, old `WFExports`, and lowercase `exports` are not the active product path |

## Start here

1. Restore the model artifact bundle:
   [Model artifacts](docs/project/usage/MODEL_ARTIFACTS.md)
1. Set up the repository:
   [Getting started](docs/project/usage/GETTING_STARTED.md)
1. Choose the workflow you need:
   [Usage guide index](docs/project/usage/README.md)

## Common workflows

| Goal | Guide |
| --- | --- |
| Run the Python CLI and batch processors | [Python CLI](docs/project/usage/PYTHON_CLI.md) |
| Run the Windows desktop app | [Desktop app](docs/project/usage/DESKTOP_APP.md) |
| Use desktop virtual microphone routing | [Virtual mic](docs/project/usage/VIRTUAL_MIC.md) |
| Run the Android app with on-device suppression | [Mobile app](docs/project/usage/MOBILE_APP.md) |
| Run the generic backend for app accounts/history | [Backend](docs/project/usage/BACKEND.md) |
| Diagnose setup/runtime problems | [Troubleshooting](docs/project/usage/TROUBLESHOOTING.md) |

## Repository map

```text
TSEBP2025/
|-- ai/
|   |-- ai_runtime/     # Python runtime, separators, profiles, mappings
|   |-- data/           # Local raw and processed audio
|   |-- export/         # Model packaging and historical conversion tools
|   |-- models/         # Model manifests plus local model/artifact trees
|   |-- scripts/        # Demos, diagnostics, utilities
|   `-- tests/          # Runtime tests
|-- desktop/            # Tauri desktop app and Rust audio runtime
|-- mobile-part/        # React Native Android app and native suppression module
|-- mobile-backend/     # Generic FastAPI backend: auth, history, devices
|-- docs/project/       # Architecture, codebase, model, knowledge, and usage docs
|-- shared/scripts/     # Shared environment setup helpers
`-- README.md
```

## Model layout

Small source-of-truth manifests stay in Git:

- `ai/models/model_selection.json`
- `ai/models/Waveformer/model_package.json`
- `ai/models/TargetSpeakerWindows/model_package.json`
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

Large model artifacts live under `ai/models/Exports` and are restored from a
separate artifact bundle. Do not rename `Exports` to lowercase `exports`.

## Documentation

- [Project documentation home](docs/project/README.md)
- [Architecture overview](docs/project/architecture/overview.md)
- [Audio pipeline](docs/project/architecture/pipeline.md)
- [Model catalogue](docs/project/model/README.md)
- [Models and training](docs/project/codebase/models_and_training.md)
- [Mobile deployment reference](docs/project/usage/MOBILE_DEPLOYMENT.md)

## Documentation approach

The operational details live in `docs/project/usage` so the repository front
page stays readable. This follows common README guidance: keep the top-level
README focused on what the project does, why it matters, how to get started,
and where to find the deeper documentation.
