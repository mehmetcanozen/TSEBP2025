## Semantic Noise Mixer

Context-aware adaptive noise suppression with semantic control.

This project provides a real-time audio pipeline that:
- **Separates** incoming audio into meaningful components using a pretrained Waveformer separator.
- **Understands** the scene using YAMNet-style semantic classification.
- **Suppresses** user-selected sound categories (for example typing, wind, traffic) while preserving important ones (for example speech, sirens, alarms).

The current focus is a **desktop-first** implementation with a validated **React Native / Expo test app** proving the on-device TFLite pipeline.

---

## Features

- **Real-time desktop suppression**
  - Sub-100 ms end-to-end latency with a rolling 1 second context buffer.
  - Tunable aggressiveness (for example 1.0 = normal, 1.5 = aggressive).
  - Mono/stereo handling and compatibility with “smart” headsets that pre-filter noise.
- **Semantic control**
  - YAMNet-based detection over 500+ classes, mapped into actionable groups (typing, wind, traffic, speech, alarms, etc.).
  - Profiles describing which categories to suppress or pass through.
  - Hard safety override so critical sounds (sirens/alarms) are never removed.
- **Tooling and diagnostics**
  - Batch and real-time record/clean tools that save:
    - Original mic input.
    - Cleaned signal.
    - Extracted noise stem.
  - Performance profiler with per-operation timing (mean, p95, p99, min, max) and JSON export.
- **Mobile testbed**
  - `mobile-test/` Expo project with:
    - On-device TFLite UNet-style model (`waveformer.tflite`).
    - Record → process → play pipeline at 44.1 kHz using `react-native-fast-tflite`, `react-native-audio-record`, `expo-av`, and `expo-file-system`.

---

## Quick start (desktop)

### 1. Create and activate the virtual environment

From the repo root:

```powershell
# Option A: Use the setup script (installs full desktop stack)
.\scripts\setup_env.ps1
.\desktop\.venv\Scripts\Activate.ps1

# Option B: Manual venv + requirements
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
pip install -r desktop\requirements.txt
pip install -r training\requirements.txt
pip install -r export\requirements.txt
```

### 2. Download models

```powershell
python scripts\download_models.py
```

This populates pretrained Waveformer/YAMNet checkpoints and prepares default configs.

### 3. Record and clean audio (recommended path)

Record from your microphone, apply semantic suppression, and save stems:

```powershell
# 10 seconds, suppress typing only
python -m desktop.src.audio.recorder_cleaner `
  --duration 10 `
  --suppress typing `
  --output samples\processed\session_clean.wav

# Suppress multiple categories
python -m desktop.src.audio.recorder_cleaner `
  --duration 10 `
  --suppress typing,wind
  --output samples\processed\session_clean.wav
```

Outputs (filenames may vary based on `--output`):
- `*_clean.wav` – cleaned audio after suppression.
- `*_original.wav` – raw microphone input.
- `*_noise.wav` – extracted noise stem.

### 4. Live real-time demo (monitoring your mic)

```powershell
# Default focus-style behavior (suppress typing)
python desktop\scripts\demo_custom_realtime.py --suppress typing

# If your mic or headset heavily pre-filters noise, lower the threshold:
python desktop\scripts\demo_custom_realtime.py --suppress typing --threshold 0.03

# List available categories and options
python desktop\scripts\demo_custom_realtime.py --help
```

### 5. Process existing WAV files

```powershell
python -m desktop.src.batch.batch_processor `
  --input samples\audio\keyboard.wav `
  --output samples\processed\keyboard_clean.wav `
  --suppress typing `
  --threshold 0.3
```

---

## Semantic categories

Internally, YAMNet’s 521 classes are grouped into higher-level categories to simplify control and profiles:

| Category       | Priority  | Safety override | Example sounds                          |
|----------------|-----------|-----------------|------------------------------------------|
| **siren**      | Critical  | Always pass     | Ambulance, fire truck, police siren     |
| **alarm**      | Critical  | Always pass     | Smoke alarm, fire alarm                  |
| **speech**     | Medium    | Normal          | Conversation, narration                  |
| **traffic**    | Medium    | Normal          | Cars, engines, road noise               |
| **music**      | Medium    | Normal          | Singing, instruments                     |
| **wind**       | Low       | Suppressable    | Wind, microphone wind noise              |
| **typing**     | Low       | Suppressable    | Keyboard clicks                          |
| **nature**     | Low       | Suppressable    | Rain, birds, dogs                        |
| **appliances** | Low       | Suppressable    | Microwave, blender, fan                  |
| **misc**       | Low       | Suppressable    | Cough, snaps, key jangling              |

Profiles and command-line options (for example `--suppress typing,wind`) operate on these groups.

---

## Project layout

```text
TSEBP2025/
├── desktop/
│   ├── src/
│   │   ├── audio/        # Real-time suppression, recorder/cleaner, buffers
│   │   ├── profiles/     # Profile manager, control engine, safety logic
│   │   └── batch/        # Offline batch processor
│   ├── scripts/          # Demo and diagnostic scripts
│   └── requirements.txt  # Desktop runtime stack
├── training/
│   ├── models/           # Waveformer wrapper and related code
│   ├── configs/          # Training/eval configuration
│   └── requirements.txt  # Training and metrics stack
├── export/
│   ├── export_onnx.py    # PyTorch → ONNX export
│   ├── export_tflite.py  # ONNX → TFLite export (UNet-based model)
│   └── requirements.txt  # ONNX/TFLite toolchain
├── models/               # Downloaded checkpoints and exports
├── mobile/               # Main React Native app (future integration target)
├── mobile-test/          # Self-contained Expo testbed for TFLite pipeline
├── samples/              # Input and processed WAV files
├── docs/                 # Additional documentation and test notes
└── scripts/              # Environment setup, model download, utilities
```

---

## Folder-level guide

### `desktop`

- **Purpose**: Desktop runtime, demos, and tests for the real-time suppression engine.
- **Key modules**:
  - `src/audio/semantic_suppressor.py` – core semantic suppression engine. Glues together semantic detection and Waveformer separation, implements inverse separation (`clean = mix - unwanted × aggressiveness`), and loads the YAMNet → Waveformer mapping.
  - `src/audio/recorder_cleaner.py` – record-from-mic + suppress + write stems (original/clean/noise) with CLI options for duration, categories, and aggressiveness.
  - `src/audio/latency_profiler.py`, `src/audio/profiler.py`, `src/audio/profile_performance.py` – operation-level timing and JSON export for throughput/latency analysis.
  - `src/audio/ring_buffer.py`, `src/audio/detection_thread.py`, `src/audio/audio_io.py` – low-level pieces that keep streaming audio stable and decoupled from heavier model inference.
  - `src/profiles/profile_manager.py` – loads/stores profiles from JSON, including custom user profiles.
  - `src/profiles/control_engine.py` – central logic for auto/manual modes, applying profiles, and enforcing safety rules.
  - `src/batch/batch_processor.py` – offline processor for existing WAV files; uses the same suppression logic as the live path.
  - `scripts/demo_custom_realtime.py` – primary realtime demo with `--suppress`, `--threshold`, and helper flags.
  - `scripts/demo_realtime.py`, `scripts/demo_debug_realtime.py`, `scripts/show_yamnet_detections.py` – debugging/visualization helpers.
  - `tests/` + `test_*` scripts – pytest tests and script-level smoke tests for end-to-end behavior.

### `training`

- **Purpose**: Training, fine-tuning, and evaluation for the models used by the mixer.
- **Key modules**:
  - `models/audio_mixer.py` – defines `WaveformerSeparator`, the inference wrapper that:
    - Loads Waveformer configs and checkpoints.
    - Resamples audio to the model’s sample rate.
    - Produces separated stems in a shape that the desktop code expects.
  - `models/semantic_detective.py` – YAMNet-based detector that:
    - Runs classification on windows of audio.
    - Aggregates/confidence-smooths predictions.
    - Produces semantic labels used by the control engine.
  - `models/Waveformer/` – upstream Waveformer project (configs, data loaders, training scripts, experiments).
  - `configs/yamnet_class_map.yaml` – mapping from raw YAMNet indices to the intermediate semantic categories used in `shared/mappings`.
  - `requirements.txt` – full training + metrics + visualization stack.

### `export`

- **Purpose**: Model export “factory” for desktop and mobile formats.
- **Key modules**:
  - `export_onnx.py` – `ONNXExporter`:
    - Wraps an instantiated `WaveformerSeparator`.
    - Exports a static-shape ONNX graph (3 seconds at 44.1 kHz) suitable for downstream conversion.
    - Can apply FP16 quantization for desktop GPU acceleration.
  - `export_tflite.py` – `TFLiteExporter`:
    - Runs the ONNX exporter.
    - Calls `onnx2tf` via `subprocess.run(...)`.
    - Moves the generated `model_float32.tflite` into the configured output location (for example the mobile assets directory).
  - `requirements.txt` – dependencies for export only (does not need to be installed in the main desktop venv unless you are actively exporting).

### `shared`

- **Purpose**: Cross-cutting configuration and profiles used by multiple components.
- **Key files**:
  - `mappings/yamnet_to_waveformer.yaml` – the primary mapping from YAMNet indices into semantic groups such as `typing`, `wind`, `traffic`, `siren`, `alarm`, etc. This is where class IDs were corrected based on empirical detection (for example for typing).
  - `profiles/default_profiles.json` – pre-defined profiles such as focus/office/commute that:
    - Specify which semantic categories to suppress.
    - Set default aggressiveness and thresholds.

### `scripts`

- **Purpose**: Utility scripts that sit at the repo root.
- **Key scripts**:
  - `setup_env.ps1` – creates and populates `desktop\.venv` with a known-good stack on Windows (CUDA-enabled PyTorch, audio libs, TensorFlow, ONNX/TFLite tooling, etc.).
  - `download_models.py` – pulls pretrained checkpoints and unpacks them into `models/` and `training/models/Waveformer/experiments/`.
  - `test_inference.py` – simple end-to-end check that the core models can be imported and executed.
  - `sample_noise.wav`, `sample_waveformer_out.wav` – audio samples for quick validation.

### `mobile` and `mobile-test`

- **`mobile/`**:
  - Primary React Native app (long-term target). The idea is to migrate the working logic from `mobile-test/` into this app once the desktop stack is fully finalized.
- **`mobile-test/`**:
  - Self-contained Expo testbed that:
    - Records audio via `react-native-audio-record`.
    - Converts WAV data to `Float32Array` buffers with helpers in `utils/wavUtils.ts`.
    - Runs chunks through a TFLite UNet-style model using `react-native-fast-tflite`.
    - Reassembles and plays original vs. cleaned audio via `expo-av`.
  - Important files:
    - `hooks/useSuppressionDemo.ts` – coordinates recording, processing, and playback in React-land.
    - `services/WaveformerInferenceService.ts` – low-level TFLite integration and buffer management.
    - `utils/wavUtils.ts` – WAV parsing and writing utilities.

## Development notes and next steps

- **What is done**
  - Desktop real-time suppression pipeline, including:
    - SemanticSuppressor with inverse separation \(Clean = Mix − Unwanted × aggressiveness\).
    - Rolling 1 second context buffer.
    - Input normalization to handle quiet microphones and pre-filtered headsets.
    - Safety overrides for critical sounds.
  - Batch and recorder tooling.
  - A working on-device TFLite pipeline in the `mobile-test` app.

- **What is partially done**
  - ONNX/TFLite export scripts for the UNet-style TFLite model.
  - Early mobile integration patterns (service/hook design, chunked 3 second inference).

- **Potential future work**
  - Desktop GUI (CustomTkinter or Electron) over the existing engine.
  - Migration of `mobile-test` logic into the main `mobile` app.
  - More automated and generalized export pipeline (Core ML, TFLite Micro, CI jobs).
  - Performance tuning and quantization for lower-end hardware. 
