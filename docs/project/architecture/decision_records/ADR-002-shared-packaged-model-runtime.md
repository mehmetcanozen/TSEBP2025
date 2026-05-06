# ADR 002: Shared Packaged Model Runtime

## Status

Current.

## Context

The project has several model families and product surfaces:

- Python research/reference runtime.
- Windows desktop Tauri app.
- Android React Native app with native inference.
- FastAPI backend for auth, history, and device metadata.

Earlier documentation drifted because desktop, mobile, and backend paths each
described different "current" models. The repo now needs one source of truth
for model selection and platform runtime contracts.

## Decision

Use shared model package manifests under `ai/models` as the product runtime
contract.

The active model is resolved from:

```text
ai/models/model_selection.json
```

Each model package declares:

- `model_id`, family, display name, package version, and description.
- suppression strategy.
- category list and presets.
- per-platform runtime kind.
- artifact and metadata files.
- sample rate and chunk/segment timing.
- optional streaming state tensor shapes.

Desktop and Android runtime packaging code must read these manifests instead of
hard-coding historical model choices. The mobile backend is intentionally
outside the model runtime and distribution path.

## Current Default

The default is `waveformer_edge_100ms`.

```text
runtime_kind: onnx_streaming_target_extractor
desktop_artifact: ../Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx
android_artifact: ../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort
sample_rate: 44100
chunk_samples: 4416
```

Desktop bundles and loads the optimized ONNX artifact through Tauri/Rust
config. Android copies the ORT-format artifact plus sidecar metadata and
`required_operators.config` into its generated asset bundle. The backend does
not serve Android model bundles.

## Alternatives Retained

- `audiosep_hive15cat`: exact-15 ONNX category separator.
- `codecsep_dnrv2_15cat`: exact-15 CodecSep with desktop ONNX and Android
  ExecuTorch contracts.
- `target_speaker_windows`: desktop target-speaker package.
- Native UNet/TFLite: historical mobile experiment only.

## Consequences

- Documentation must state Waveformer ONNX as the default until
  `model_selection.json` changes.
- Android deployment docs must describe generated model bundles, not standalone
  `.tflite` assets.
- Backend `/model/latest`, `/model/download`, and `/separation/*` are not part
  of the active product route.
- New model work should first define or update a package manifest, then wire
  product runtimes to that manifest.
