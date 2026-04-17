# Semantic Noise Mixer

Semantic Noise Mixer is a desktop-first audio suppression project built around
semantic detection, source separation, spectral masking, and profile-driven
control. The repository contains the active AI runtime, a Python desktop UI,
setup scripts, tests, and local model layouts for multiple separator backends.

For detailed operator guidance, see the
[Master User Manual](docs/project/usage/USER_MANUAL.md).

## Current Scope

- Real-time and offline audio suppression tooling
- Multiple separator backends behind one runtime interface
- Profile-based control and backend-specific suppression settings
- Local model asset management under `ai/models/`
- Desktop UI, command-line tools, tests, and research documentation

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
|   |-- src/            # Desktop UI and settings layer
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

### Desktop UI

```powershell
python desktop\src\ui\app.py
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
