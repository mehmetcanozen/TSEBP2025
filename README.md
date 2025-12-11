# 🎧 Semantic Noise Mixer

Context-Aware Adaptive Noise Cancellation with Semantic Control.

**Train Once, Run Everywhere** — a portable AI model that runs on desktop, mobile, and embedded devices.

## 🚀 Quick Start (Desktop + Models)
Prereqs: Python 3.11, Git LFS, Node 18+ (for mobile later), PowerShell.

1) Clone & LFS
```powershell
git lfs install
git clone <repo-url> .
```

2) Python env
```powershell
cd training
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3) Download checkpoints (Waveformer, YAMNet)
```powershell
cd ..
python scripts\download_models.py
```

4) Smoke test inference
```powershell
.\training\.venv\Scripts\Activate.ps1
python scripts\test_inference.py
```

Outputs: `scripts/sample_waveformer_out.wav` and YAMNet top-class log.

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
Git ignores empty dirs. Create placeholders once after clone:

PowerShell:
```powershell
'models/checkpoints','models/exports/onnx','models/exports/tflite','models/exports/coreml','models/configs','training/datasets','training/scripts','training/configs','desktop/src/audio','desktop/src/inference','desktop/src/ui','desktop/src/profiles','desktop/tests','mobile/src/components','mobile/src/screens','mobile/src/services','mobile/src/hooks','mobile/src/navigation','mobile/assets/models','export','shared/profiles','shared/constants','scripts' | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null; New-Item -ItemType File -Force -Path (Join-Path $_ ".gitkeep") | Out-Null }
```

Bash (macOS/Linux/WLS):
```bash
dirs=(
  models/checkpoints models/exports/onnx models/exports/tflite models/exports/coreml models/configs
  training/datasets training/scripts training/configs
  desktop/src/audio desktop/src/inference desktop/src/ui desktop/src/profiles desktop/tests
  mobile/src/components mobile/src/screens mobile/src/services mobile/src/hooks mobile/src/navigation mobile/assets/models
  export shared/profiles shared/constants scripts
)
mkdir -p "${dirs[@]}" && for d in "${dirs[@]}"; do touch "$d/.gitkeep"; done
```

## 📖 Documentation
See `docs/` and `CursorMD/DevPlans`.

## 📄 License
[Your License Here]

