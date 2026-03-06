## Semantic Noise Mixer

Context-aware adaptive noise suppression with semantic control.

This project provides a real-time audio pipeline that:
- **Separates** incoming audio into meaningful components using a pretrained Waveformer separator.
- **Understands** the scene using YAMNet-style semantic classification.
- **Suppresses** user-selected sound categories (typing, wind, traffic, and more) while preserving speech. See the Master User Manual for the currently supported categories.

The current focus is a **desktop-first** implementation with a validated **React Native / Expo test app** proving the on-device TFLite pipeline.

---

> [!IMPORTANT]
> **New to the project?** Start with the [Master User Manual](docs/project/usage/USER_MANUAL.md) for a comprehensive guide to all tools and features.

---

## Features

- **Real-time desktop suppression**
  - Sub-100 ms end-to-end latency with a rolling 1 second context buffer.
  - Tunable aggressiveness (for example 1.0 = normal, 1.5 = aggressive).
  - Mono/stereo handling and compatibility with “smart” headsets that pre-filter noise.
  - **🚀 Phase 1: Spectral Masking**: High-fidelity noise removal using frequency-domain ratio masking to prevent phase artifacts.
  - **🎙️ Phase 2: Suppress All**: Integrated **DeepFilterNet** for universal voice extraction (removes all non-speech audio).
- **🚀 Phase 3: Universal Extraction**: Integrated **AudioSep** foundation model for open-vocabulary sound extraction using natural language text prompts (e.g., "dog barking," "typing").
- **🎯 Per-Category Separation**: Each suppression category receives its own dedicated Waveformer query, preventing loud sources from masking quiet targets. Batched into a single GPU forward pass via `separate_multi_query()` for real-time performance.
- **🔊 Adaptive Stem Boosting**: Under-extracted quiet sounds are automatically amplified (up to 4×) to compensate for Waveformer's limitations in low target-to-interference ratio environments.
- **Semantic control**
  - YAMNet-based detection over 521 classes, mapped into actionable groups (typing, pets, phone, wind, traffic, speech, music, etc.).
  - Profiles describing which categories to suppress or pass through.
- **Tooling and diagnostics**
  - Batch and real-time record/clean tools that save:
    - Original mic input.
    - Cleaned signal.
    - Extracted noise stem (`*_noise.wav`).
  - **🧪 Phase 6: Virtual Mic Sim**: Stream WAV files directly into the system via VB-Cable to simulate live microphone input for repeatable testing.
  - Performance profiler with per-operation timing (mean, p95, p99, min, max) and JSON export.
- **Mobile testbed**
  - `mobile-test/` Expo project with:
    - On-device TFLite UNet-style model (`waveformer.tflite`).
    - Record → process → play pipeline at 44.1 kHz using `react-native-fast-tflite`, `react-native-audio-record`, `expo-av`, and `expo-file-system`.
- **🚀 Phase 8: Final Verification**: 100% production-ready validation complete across batch and real-time paths (Virtual Mic verified).

---

## Quick start (desktop)

### 1. Create and activate the virtual environment

From the repo root:

```powershell
# Option A: Use the shared setup script (AI + desktop stack)
.\shared\scripts\setup_env.ps1
.\.venv\Scripts\Activate.ps1

# Option B: Manual venv + requirements
python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
pip install -r desktop\requirements.txt
pip install -r ai\training\requirements.txt
pip install -r ai\export\requirements.txt
```

### 2. Download models & Foundational Weights

```powershell
# Basic models (YAMNet, Waveformer, DeepFilterNet)
python ai\scripts\setup\download_models.py

# Foundational models (AudioSep weights & CLAP)
# Note: This requires ~2GB of space and additional ML dependencies
python ai\scripts\setup\install_audiosep.py
```

### 3. Record and clean audio (recommended path)

Record from your microphone, apply semantic suppression, and save stems:

```powershell
# 10 seconds, suppress typing only
python -m ai.ai_runtime.audio.recorder_cleaner `
  --duration 10 `
  --suppress typing `
  --output ai\data\audio\processed\session_clean.wav

# Suppress multiple categories
python -m ai.ai_runtime.audio.recorder_cleaner `
  --duration 10 `
  --suppress typing,wind `
  --output ai\data\audio\processed\session_clean.wav
```

Outputs (filenames may vary based on `--output`):
- `*_clean.wav` – cleaned audio after suppression.
- `*_original.wav` – raw microphone input.
- `*_noise.wav` – extracted noise stem.

### 4. Live real-time demo (monitoring your mic)

```powershell
# Default focus-style behavior (suppress typing)
python ai\scripts\demos\demo_custom_realtime.py --suppress typing

# If your mic or headset heavily pre-filters noise, lower the threshold:
python ai\scripts\demos\demo_custom_realtime.py --suppress typing --threshold 0.03

# List available categories and options
python ai\scripts\demos\demo_custom_realtime.py --help
```

### 5. Process existing WAV files

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input ai\data\audio\raw\keyboard.wav `
  --output ai\data\audio\processed\keyboard_clean.wav `
  --suppress typing `
  --threshold 0.3
```

---

## Semantic categories

Internally, YAMNet’s 521 classes are grouped into higher-level categories to simplify control and profiles:

| Category       | Priority  | Example sounds                          |
|----------------|-----------|------------------------------------------|
| **siren**      | Medium    | Ambulance, fire truck, police siren     |
| **alarm**      | Medium    | Smoke alarm, fire alarm                  |
| **speech**     | Medium    | Conversation, narration                  |
| **traffic**    | Medium    | Cars, engines, road noise               |
| **music**      | Medium    | Singing, instruments                     |
| **wind**       | Low       | Wind, microphone wind noise              |
| **typing**     | Low       | Keyboard clicks                          |
| **nature**     | Low       | Rain, birds, dogs                        |
| **pets**       | Low       | Dog barking, cat meowing                 |
| **appliances** | Low       | Microwave, blender, fan                  |
| **misc**       | Low       | Cough, snaps, key jangling              |

All categories are fully suppressible via profiles and command-line options (for example `--suppress typing,wind,siren`).

---

## Project layout

```text
TSEBP2025/
├── desktop/
│   ├── src/
│   │   └── profiles/     # Profile manager, control engine, safety logic
│   └── requirements.txt  # Desktop runtime stack
├── ai/
│   ├── ai_runtime/       # Canonical AI runtime (detection/separation/suppression, config/)
│   ├── training/         # Training configs and training dependency set
│   ├── export/           # PyTorch → ONNX/TFLite export factory
│   ├── scripts/          # AI scripts (setup/, demos/, diagnostics/)
│   └── tests/            # AI tests (runtime/, integration/, manual/)
├── ai/models/            # Downloaded checkpoints and exports
├── ai/data/audio/        # Raw and processed audio datasets
├── mobile/               # Main React Native app (future integration target)
├── mobile-test/          # Self-contained Expo testbed for TFLite pipeline
├── docs/                 # Additional documentation and test notes
└── shared/
    └── scripts/         # Shared setup (e.g. setup_env.ps1 for .venv)
```

---

## Folder-level guide

### `desktop`

- **Purpose**: Desktop runtime, demos, and tests for the real-time suppression engine.
- **Key modules**:
  - `ai/ai_runtime/suppression/semantic_suppressor.py` – core semantic suppression engine. Glues together semantic detection and Waveformer separation, implements per-category separation with adaptive stem boosting and two-stage spectral masking, and loads the YAMNet → Waveformer mapping.
  - `ai/ai_runtime/audio/recorder_cleaner.py` – record-from-mic + suppress + write stems (original/clean/noise) with CLI options for duration, categories, and aggressiveness.
  - `ai/ai_runtime/audio/latency_profiler.py`, `ai/ai_runtime/profiles/profiler.py`, `ai/scripts/diagnostics/profile_performance.py` – operation-level timing and JSON export for throughput/latency analysis.
  - `ai/ai_runtime/audio/ring_buffer.py`, `ai/ai_runtime/detection/detection_thread.py`, `ai/ai_runtime/audio/audio_io.py` – low-level pieces that keep streaming audio stable and decoupled from heavier model inference.
  - `ai/ai_runtime/profiles/profile_manager.py` – loads/stores profiles from JSON, including custom user profiles.
  - `src/profiles/control_engine.py` – central logic for auto/manual modes, applying profiles, and enforcing safety rules.
  - `ai/ai_runtime/batch/batch_processor.py` – offline processor for existing WAV files; uses the same suppression logic as the live path.
  - `ai/scripts/demos/demo_custom_realtime.py` – primary realtime demo with `--suppress`, `--threshold`, and helper flags.
  - `ai/scripts/demos/demo_realtime.py`, `ai/scripts/demos/demo_debug_realtime.py`, `ai/scripts/diagnostics/show_yamnet_detections.py` – debugging/visualization helpers.
  - `tests/` + `test_*` scripts – pytest tests and script-level smoke tests for end-to-end behavior.

### `ai/training`

- **Purpose**: Training, fine-tuning, and evaluation for the models used by the mixer.
- **Key modules**:
  - `ai/ai_runtime/separation/waveformer_separator.py` – defines `WaveformerSeparator`, the inference wrapper that:
    - Loads Waveformer configs and checkpoints.
    - Resamples audio to the model’s sample rate.
    - Produces separated stems in a shape that the desktop code expects.
  - `ai/ai_runtime/detection/semantic_detective.py` – YAMNet-based detector that:
    - Runs classification on windows of audio.
    - Aggregates/confidence-smooths predictions.
    - Produces semantic labels used by the control engine.
  - `ai/models/Waveformer/` – upstream Waveformer project (configs, data loaders, training scripts, experiments).
  - `ai/ai_runtime/config/yamnet_class_map.yaml` – canonical mapping from raw YAMNet indices to semantic categories.
  - `requirements.txt` – full training + metrics + visualization stack.

### `ai/export`

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
  - `requirements.txt` – dependencies for export only. **Use a separate venv** for full ONNX/TFLite export (TF 2.15, numpy<2 conflict with desktop/training). See `ai/export/requirements.txt` header.

### `ai/ai_runtime/config`

- **Purpose**: Canonical config (YAMNet mappings, profile defaults, schemas).
- **Key files**:
  - `yamnet_class_map.yaml`, `yamnet_to_waveformer.yaml` – YAMNet category mappings.
  - `default_profiles.json` – pre-defined profiles (focus/office/commute) specifying suppressions and gains.
  - `profile_schema.json` – JSON schema for profile validation.

### `shared/scripts`

- **Purpose**: Shared tooling used by AI and desktop.
- **Key scripts**:
  - `setup_env.ps1` – creates and populates `.venv` at project root with the full stack (AI + desktop) on Windows (CUDA-enabled PyTorch, audio libs, TensorFlow, ONNX/TFLite tooling, etc.).

### `ai/scripts`

- **Purpose**: AI utility scripts for downloads and smoke checks.
- **Key scripts**:
  - `setup/download_models.py` – pulls pretrained checkpoints and unpacks them into `ai/models/` (including `ai/models/Waveformer/experiments/`).

### `ai/tests`

- **Purpose**: AI-owned automated tests and smoke-style validation modules.
- **Key modules**:
  - `test_audio.py`, `test_detection_thread.py`, `test_waveformer_separator.py`, `test_suppression_quality.py` – core AI runtime behavior tests.
  - `test_inference.py`, `test_df.py`, `test_system.py` – validation-focused smoke helpers kept under test ownership.

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
    - SemanticSuppressor with per-category separation and adaptive stem boosting.
    - Rolling 1 second context buffer.
    - Two-stage masking pipeline with adaptive floor and Wiener post-filter.
    - Batched multi-query Waveformer inference via `separate_multi_query()`.
    - Performance optimization: torch.compile, ONNX Runtime, STFT window caching.
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
