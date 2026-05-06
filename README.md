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
- `ai/models/CodecSepDNRv2_15Cat/model_package.json`

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
