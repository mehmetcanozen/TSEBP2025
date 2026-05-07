# Getting started

Use this guide when you have a fresh checkout and want to get one working path
running without reading the entire documentation set.

## Prerequisites

Install the pieces required by the workflow you plan to use:

| Workflow | Required tools |
| --- | --- |
| Python CLI | Python 3.10 or newer, PowerShell |
| Desktop app | Node.js, npm, Rust/Cargo, WebView2 runtime |
| Android app | Node.js, npm, Android Studio, Android SDK, JDK, Gradle through the Android project |
| Backend | Node.js, npm, PostgreSQL 18 or another PostgreSQL-compatible server |
| Virtual mic | VB-CABLE on Windows |

## Python environment

From the repository root:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime -UpgradePip
.\.venv\Scripts\Activate.ps1
python -m ai --help
```

Use additional AI setup profiles only when needed:

```powershell
# Required for VB-CABLE/WAV streaming.
.\shared\scripts\setup-ai-runtime.ps1 -Profile audio-device

# Required for ONNX runtime checks or export work.
.\shared\scripts\setup-ai-runtime.ps1 -Profile onnx

# Heavy research/export environments.
.\shared\scripts\setup-ai-runtime.ps1 -Profile export
.\shared\scripts\setup-ai-runtime.ps1 -Profile training

# Evaluation reports and figures.
.\shared\scripts\setup-ai-runtime.ps1 -Profile evaluation
```

The desktop and mobile apps install their JavaScript dependencies inside their
own folders with `npm install`.

## Restore model artifacts

The checkout is not complete until `ai/models/Exports` is present. Download
the portable artifact zip from:

```text
https://drive.google.com/file/d/1mQq1cagJf5lNTkQqo85s9qRCW1a-hN5c/view?usp=sharing
```

Then follow [Model artifacts](MODEL_ARTIFACTS.md), and return here.

Minimum check:

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai artifacts check --required-only
```

The required entries should report `OK`.

## Choose a workflow

### Python CLI

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --target dog `
  --backend waveformer `
  --aggressiveness 1.1
```

More commands: [Python CLI](PYTHON_CLI.md).

For the final model evaluation/report workflow:

```powershell
python -m ai evaluate plan --models all --suite full
python -m ai evaluate run --models waveformer_onnx_export --max-cases 1 --report md-html
```

### Desktop app

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-backend.ps1
.\shared\scripts\start-desktop.ps1
```

The default command opens the clean user UI. For the diagnostics UI:

```powershell
.\shared\scripts\start-desktop.ps1 -DevUi
```

More detail: [Desktop app](DESKTOP_APP.md) and [Developer scripts](DEV_SCRIPTS.md).

### Android app

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-backend.ps1
.\shared\scripts\start-mobile-android.ps1 -StartEmulator
```

More detail: [Mobile app](MOBILE_APP.md).

### Shared backend

Preferred scripted setup:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-backend-postgres.ps1 -PostgresPassword "<YOUR_POSTGRES_PASSWORD>"
.\shared\scripts\start-backend.ps1
```

More detail: [Backend](BACKEND.md),
[Backend setup](BACKEND_SETUP.md), and
[Backend Windows PostgreSQL](BACKEND_WINDOWS_POSTGRES.md).

## What should work first

For a normal developer setup, prove these in order:

1. `ai/models/Exports` is restored and verified.
1. `python -m ai models list` reports `waveformer_edge_100ms` as the default.
1. A Python CLI command runs on `speech_barking.wav` with category `dog`.
1. The shared backend health check passes at `http://localhost:4000/api/v1/health`.
1. The desktop app opens and lists packaged categories.
1. Android Gradle prepares the bundled suppression model.
1. The Android app reports `waveformer_edge_100ms` and runs suppression on
   device.

If one of those fails, use [Troubleshooting](TROUBLESHOOTING.md).
