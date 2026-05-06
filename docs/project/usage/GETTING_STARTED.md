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
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r ai\training\requirements.txt
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
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort
```

Both commands should print `True` for the current desktop and Android product
paths.

## Choose a workflow

### Python CLI

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai.ai_runtime.batch.batch_processor `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --suppress dog `
  --aggressiveness 1.1
```

More commands: [Python CLI](PYTHON_CLI.md).

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
1. A Python batch command runs on `speech_barking.wav` with category `dog`.
1. The shared backend health check passes at `http://localhost:4000/api/v1/health`.
1. The desktop app opens and lists packaged categories.
1. Android Gradle prepares the bundled suppression model.
1. The Android app reports `waveformer_edge_100ms` and runs suppression on
   device.

If one of those fails, use [Troubleshooting](TROUBLESHOOTING.md).
