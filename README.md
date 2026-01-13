# 🎧 Semantic Noise Mixer

Context-Aware Adaptive Noise Cancellation with Semantic Control.

**Train Once, Run Everywhere** — A portable AI system that separates audio into stems (Waveformer) and identifies sounds semantically (YAMNet), enabling granular noise control with safety overrides.

## ✅ Current Status

| Module | DevPlan | Status | Description |
|--------|---------|--------|-------------|
| Project Setup | DevPlan0 | ✅ Complete | Repo structure, CI/CD, dependencies |
| Audio Mixer | DevPlan1 | ✅ Complete | Real-time Waveformer separation (<30ms) |
| Semantic Detective | DevPlan2 | ✅ Complete | YAMNet classification with temporal smoothing |
| Profiles & Logic | DevPlan3 | ⬜ Next | Auto-mode, safety override integration |
| Model Export | DevPlan4 | ⬜ Pending | ONNX/TFLite quantization |
| Desktop App | DevPlan5 | ⬜ Pending | CustomTkinter GUI |
| Mobile App | DevPlan6 | ⬜ Pending | React Native + TFLite |

## 🧭 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DUAL-TRACK PROCESSING                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  FAST LANE (30ms)              SLOW LANE (3s)               │
│  ┌──────────────┐              ┌──────────────┐             │
│  │  Waveformer  │              │    YAMNet    │             │
│  │  (Separator) │              │  (Detector)  │             │
│  └──────┬───────┘              └──────┬───────┘             │
│         │                             │                      │
│         ▼                             ▼                      │
│  [Speech] [Noise]              "wind", "siren"              │
│         │                             │                      │
│         ▼                             ▼                      │
│  ┌──────────────┐              ┌──────────────┐             │
│  │ Gain Mixer   │◄─────────────│ Auto-Mode    │             │
│  │ (user gains) │   profiles   │ Safety Override            │
│  └──────────────┘              └──────────────┘             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Git LFS (for model checkpoints)
- Windows PowerShell (or bash on macOS/Linux)

### 1. Clone & Setup
```powershell
git lfs install
git clone <repo-url>
cd TSEBP2025

# Install dependencies
pip install -r training/requirements.txt
pip install -r desktop/requirements.txt
```

### 2. Download Models
```powershell
python scripts/download_models.py

# Extract YAMNet (if not already)
tar -xzf models/checkpoints/yamnet_1.tar.gz -C models/checkpoints/yamnet_1
```

### 3. Test Audio Mixer (Waveformer)
```powershell
python desktop/src/test_mixer.py --duration 10 --frames 512 --sample-rate 44100
```
- Uses default mic/speaker
- Reports RMS levels and buffer latency

### 4. Test Semantic Detective (YAMNet)
```powershell
# With a WAV file
python desktop/src/test_detective.py --wav samples/audio/siren.wav --model-handle models/checkpoints/yamnet_1

# With live microphone (requires sounddevice)
pip install sounddevice
python desktop/src/test_detective.py --seconds 3
```

**Sample output:**
```
Top detections:
- siren: 0.44
- traffic: 0.16
- alarm: 0.12

Safety override: clear
```

## 📁 Project Structure

```
TSEBP2025/
├── training/                    # Model training & YAMNet wrapper
│   ├── models/
│   │   ├── audio_mixer.py       # Waveformer separator
│   │   ├── semantic_detective.py # YAMNet + temporal smoothing
│   │   └── Waveformer/          # Waveformer submodule
│   ├── configs/
│   │   └── yamnet_class_map.yaml # 8 semantic categories
│   └── tests/
├── desktop/                     # Desktop application
│   ├── src/
│   │   ├── audio/
│   │   │   ├── audio_process.py # Multiprocessing audio worker
│   │   │   ├── mixer_controller.py # UI-facing controller
│   │   │   ├── detection_thread.py # Background YAMNet detection
│   │   │   └── ring_buffer.py   # Thread-safe audio buffer
│   │   └── inference/
│   │       └── waveformer_wrapper.py
│   └── tests/
├── models/
│   ├── checkpoints/
│   │   ├── waveformer_experiments/ # Waveformer .pt files
│   │   ├── yamnet_1/            # Extracted YAMNet SavedModel
│   │   └── yamnet_class_map.csv # 521 AudioSet classes
│   └── exports/                 # ONNX/TFLite exports (DevPlan4)
├── samples/audio/               # Test audio clips
├── CursorMD/DevPlans/           # Development roadmap
└── scripts/                     # Utilities
```

## 🎯 Semantic Categories

The Semantic Detective maps YAMNet's 521 classes to 8 actionable categories:

| Category | Priority | Safety Override | Example Sounds |
|----------|----------|-----------------|----------------|
| **siren** | Critical | ✅ Yes | Ambulance, fire truck, police |
| **alarm** | Critical | ✅ Yes | Smoke detector, fire alarm |
| **speech** | Medium | No | Conversation, narration |
| **traffic** | Medium | No | Cars, engines, road noise |
| **music** | Medium | No | Singing, instruments |
| **wind** | Low | No | Wind, microphone noise |
| **typing** | Low | No | Keyboard clicks |
| **nature** | Low | No | Rain, birds, dogs |

## 🔧 Key Features

### Temporal Smoothing (Anti-Flicker)
- **Confidence Buffer**: 2-of-3 rule prevents false positives
- **Schmitt Trigger**: 70% ON / 40% OFF hysteresis
- **Median Filter**: Optional extra stability

### Adaptive Duty Cycling (Battery Saver)
- Battery >50%: Detect every 3 seconds
- Battery 20-50%: Detect every 8 seconds
- Battery <20%: Detect every 15 seconds

### Safety Override
When siren/alarm detected above threshold → bypass all user settings, pass audio through.

## 🧪 Running Tests

```powershell
# Unit tests for Semantic Detective
python -m pytest training/tests/test_detective.py -v

# Unit tests for Audio components
python -m pytest desktop/tests/ -v
```

## 📖 Documentation

- **Development Plans**: `CursorMD/DevPlans/`
- **Master Plan**: `CursorMD/DevPlans/MasterPlan.md`
- **Progress Log**: `CursorMD/progress.md`

## 🔜 Next Steps (DevPlan3)

1. Profile system (Focus, Commute, Passthrough presets)
2. Auto-mode controller (detection → profile switching)
3. Safety override integration (siren → force passthrough)
4. Desktop UI wiring

## CI/CD

`.github/workflows/python-ci.yml` runs tests on push/PR to `main`/`develop`.

## 📄 License

[Your License Here]
