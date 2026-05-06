# Usage guide index

This folder contains the operational runbooks for getting the project working.
Use this index instead of hunting through the root README.

## Recommended order

1. [Model artifacts](MODEL_ARTIFACTS.md)
   Download the ignored `Exports` zip from
   [Google Drive](https://drive.google.com/file/d/1mQq1cagJf5lNTkQqo85s9qRCW1a-hN5c/view?usp=sharing),
   restore it to `ai/models/Exports`, and verify required files.
1. [Getting started](GETTING_STARTED.md)
   Prepare the local environment and choose a workflow.
1. [Developer scripts](DEV_SCRIPTS.md)
   Use the shared PowerShell launchers for backend, desktop, mobile, Android checks, and loopback WAV routing.
1. [Python CLI](PYTHON_CLI.md)
   Run file-based suppression, semantic demos, and comparison backends.
1. [Desktop app](DESKTOP_APP.md)
   Run the Windows Tauri app, live monitor, Debug WAV, and target-speaker mode.
1. [Virtual mic](VIRTUAL_MIC.md)
   Route cleaned desktop audio into other Windows applications with VB-CABLE.
1. [Mobile app](MOBILE_APP.md)
   Run Android on-device suppression with the bundled Waveformer ORT model.
1. [Backend](BACKEND.md)
   Run the shared NestJS backend for desktop/mobile auth, profiles, device records, and metadata.
1. [Backend setup](BACKEND_SETUP.md)
   Walk through prerequisites, database setup, env files, migrations, health checks, and client URLs.
1. [Backend Windows PostgreSQL](BACKEND_WINDOWS_POSTGRES.md)
   Exact Windows/PostgreSQL 18 runbook for local cluster creation, migrations, and restart commands.
1. [Troubleshooting](TROUBLESHOOTING.md)
   Diagnose the common setup, model, audio, desktop, and Android failures.

## Reference docs

- [User manual](USER_MANUAL.md)
- [Developer scripts](DEV_SCRIPTS.md)
- [Backend setup](BACKEND_SETUP.md)
- [Backend Windows PostgreSQL](BACKEND_WINDOWS_POSTGRES.md)
- [Mobile deployment reference](MOBILE_DEPLOYMENT.md)
- [Waveformer wide evaluation](WAVEFORMER_WIDE_EVAL.md)
- [Project documentation home](../README.md)

## Current product defaults

| Concern | Current answer |
| --- | --- |
| Default model | `waveformer_edge_100ms` |
| Desktop semantic model artifact | `ai/models/Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx` |
| Android semantic model artifact | `ai/models/Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort` |
| Desktop target-speaker artifact | `ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/windows_bundle_manifest.json` |
| Mobile inference | On-device, bundled model, no backend suppression API |
| Backend role | Auth, profiles, settings, history metadata, devices |

Historical Native UNet, TFLite, old `WFExports`, and lowercase `exports`
references should not be treated as the current runtime.

## One-Machine Smoke Path

After restoring model artifacts and setting up PostgreSQL once, this is the
normal Windows development loop:

```powershell
cd C:\SoftwareProjects\TSEBP2025

.\shared\scripts\start-backend.ps1
.\shared\scripts\start-desktop.ps1
```

For the developer diagnostics UI:

```powershell
.\shared\scripts\start-desktop.ps1 -DevUi
```

For Android:

```powershell
.\shared\scripts\start-mobile-android.ps1 -StartEmulator
```

For VB-CABLE WAV streaming:

```powershell
.\shared\scripts\stream-loopback-wav.ps1 -ListDevices
.\shared\scripts\stream-loopback-wav.ps1 `
  -Input .\ai\data\audio\raw\speech_barking.wav `
  -DeviceName "CABLE Input"
```
