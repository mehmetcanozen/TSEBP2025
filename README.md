# 🎧 Semantic Noise Mixer

Context-Aware Adaptive Noise Cancellation with Semantic Control. Uses Waveformer for target-aware separation and YAMNet for semantic cues.

**Train Once, Run Everywhere** — desktop first, with paths to mobile and export.

## 🧭 Overview
- Desktop mixer: PyAudio I/O, multiprocessing to bypass the GIL, ring buffers to decouple capture/playback from inference, gain smoothing to avoid zipper noise.
- Models: Waveformer checkpoints (targeted separation) and YAMNet (classification cues). Checkpoints are downloaded via helper script.
- Dev plans: see `CursorMD/DevPlans` for staged milestones (Audio Mixer, Semantic Detective, etc.).

## 🚀 Setup

### Prerequisites
- Python 3.11+
- Git LFS (for model files)
- Node.js 18+ (for mobile app)
- PowerShell (Windows) or Bash (macOS/Linux)

### Desktop Setup

1) Clone & LFS
```powershell
git lfs install
git clone <repo-url> .
cd TSEBP2025
```

2) Python env (training + desktop deps)
```powershell
cd training
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
pip install -r desktop/requirements.txt
```

3) Download checkpoints (Waveformer, YAMNet)
```powershell
python scripts\download_models.py
```

4) Smoke test inference (Waveformer + YAMNet)
```powershell
.\training\.venv\Scripts\Activate.ps1
python scripts\test_inference.py
```
Outputs: `scripts/sample_waveformer_out.wav` and YAMNet top-class log.

### Mobile Setup (React Native)

```powershell
cd TSEBP2025/mobile
npm install
# or
pnpm install

# Start development server
npm run dev
# or
pnpm dev

# Run on device
npm run android
npm run ios
```

## 🔊 Desktop Mixer Smoke Test
- Activate env: `.\training\.venv\Scripts\Activate.ps1`
- Run: `python desktop\src\test_mixer.py --duration 10 --frames 512 --sample-rate 44100`
- Optional: `--freeze-ui` simulates UI stall to verify multiprocessing/GIL isolation.
- Notes: uses default input/output devices; adjust frames/sample-rate for your hardware. Reports RMS and theoretical buffer latency (`frames / sample_rate`).

## 🧩 Architecture (desktop mixer)
- `desktop/src/audio/audio_io.py`: PyAudio backend, process priority helper.
- `desktop/src/audio/audio_process.py`: multiprocessing worker; ring buffers; inference loop.
- `desktop/src/audio/mixer_controller.py`: UI-facing controller and gain updates.
- `desktop/src/inference/waveformer_wrapper.py`: shim to reuse training WaveformerSeparator.
- `desktop/tests`: unit tests for ring buffer, gain smoothing, controller, WaveformerSeparator.

## 📁 Project Structure
- `training/` — PyTorch models, env
- `desktop/` — Python desktop app (ONNX runtime)
- `mobile/` — React Native app (TFLite path)
- `export/` — Model export pipeline
- `models/` — Checkpoints and exported artifacts
- `scripts/` — Utilities (downloads, smoke tests)
- `CursorMD/DevPlans` — Development plans

## CI
`.github/workflows/python-ci.yml` runs tests on push/PR to `main`/`develop`.

## ⚡ Keeping Empty Folders (fast)
Git ignores empty dirs. Create placeholders once after clone. Directories already populated (no .gitkeep needed): `desktop/src/audio`, `desktop/src/inference`, `desktop/tests`.

PowerShell:
```powershell
'models/checkpoints','models/exports/onnx','models/exports/tflite','models/exports/coreml','models/configs','training/datasets','training/scripts','training/configs','desktop/src/ui','desktop/src/profiles','mobile/src/components','mobile/src/screens','mobile/src/services','mobile/src/hooks','mobile/src/navigation','mobile/assets/models','export','shared/profiles','shared/constants','scripts' | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null; New-Item -ItemType File -Force -Path (Join-Path $_ ".gitkeep") | Out-Null }
```

Bash (macOS/Linux/WSL):
```bash
dirs=(
  models/checkpoints models/exports/onnx models/exports/tflite models/exports/coreml models/configs
  training/datasets training/scripts training/configs
  desktop/src/ui desktop/src/profiles
  mobile/src/components mobile/src/screens mobile/src/services mobile/src/hooks mobile/src/navigation mobile/assets/models
  export shared/profiles shared/constants scripts
)
mkdir -p "${dirs[@]}" && for d in "${dirs[@]}"; do touch "$d/.gitkeep"; done
```

## 📖 Documentation
See `docs/` and `CursorMD/DevPlans`.

## 📄 License
[Your License Here]

