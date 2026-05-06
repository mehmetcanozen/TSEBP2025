# Architecture Overview

This project is a semantic noise suppression system. Instead of applying a
generic noise gate, it lets the user choose a sound category or speaker target,
estimates the unwanted source, and reconstructs cleaner audio by subtracting or
masking that estimate from the original mixture.

The current product architecture is shared across Python, desktop, and Android
through model manifests in `ai/models`. The default model is
`waveformer_edge_100ms`, a 20-category Waveformer ONNX streaming target
extractor.

## System Layers

```text
ai/models/model_selection.json
        |
        +-- Waveformer/model_package.json
        |       |
        |       +-- desktop: onnx_streaming_target_extractor
        |       +-- android: onnx_streaming_target_extractor
        |
        +-- AudioSepHive15Cat/model_package.json
        +-- CodecSepDNRv2_15Cat/model_package.json
        +-- TargetSpeakerWindows/model_package.json
        |
        +-- Exports/
                +-- Waveformer/waveformer_edge_100ms/
                +-- AudioSepHive15Cat/audiosep_hive15cat_exact15/
                +-- CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/
                +-- TargetSpeakerWindows/target_speaker_windows_desktop/

Python ai_runtime          Desktop Tauri app          Android app
offline/reference          live/offline product       mobile live product
        |                         |                         |
        +-------------------------+-------------------------+

backend
auth/profile/settings/history metadata/devices only; no model delivery or inference
```

### Python Runtime

The Python layer under `ai/ai_runtime` is the reference implementation and test
surface. It contains:

- `SemanticSuppressor`, the common suppression API.
- `BatchProcessor`, the offline file processor.
- Waveformer, AudioSepHive15Cat, CodecSepDNRv2, generic CodecSep, and
  target-speaker separator adapters.
- YAMNet-based detection and semantic mapping used by legacy Waveformer Python
  flows.
- Profiles, masking, audio IO, diagnostics, export helpers, and runtime tests.

This layer is where most model experiments and validation utilities live, even
when the desktop/mobile product uses packaged ONNX or ExecuTorch artifacts.

### Desktop App

The desktop app is a Tauri v2 application:

- React/Vite frontend in `desktop/src`.
- Rust native runtime in `desktop/src-tauri/src`.
- Shared model selection resolved by `desktop/src-tauri/src/config.rs`.
- Live audio, Debug WAV input, monitor output, and VB-CABLE virtual mic routing
  in `desktop/src-tauri/src/audio`.
- ONNX category and streaming target-extractor inference in
  `desktop/src-tauri/src/engine`.
- Target-speaker offline and limited realtime support through the Windows
  target-speaker package.

The virtual mic feature does not install a driver. It writes processed audio to
the VB-CABLE playback endpoint, while other applications select the matching
VB-CABLE recording endpoint as their microphone.

### Android App

The Android app lives in `mobile-part`. The JavaScript/TypeScript side prepares
the model, exposes categories, starts/stops live suppression, and handles UI
state. The native Android module named `SuppressionEngine` loads model bundles,
chooses the runtime from `manifest.json`, and runs live audio through an
Oboe/AAudio-first native engine. The Oboe callbacks only move samples through
preallocated rings; model inference stays on a processor thread. If Oboe cannot
open on a device, the app falls back to the Kotlin `AudioRecord`/`AudioTrack`
path.

Current Android support is not the old TFLite/Native UNet path. The generated
bundle under `mobile-part/android/app/build/generated/suppression-assets/`
contains the active Waveformer Android artifact (`model_fixed.ort`), metadata,
and required-operator config. The default live settings are quality-stable:
100 ms Waveformer hops, about 300 ms lookahead, CPU ONNX Runtime, no default
post-filter, and no default quantization or accelerator path.

### Shared Backend

The shared NestJS backend in `backend` provides auth, profile, settings,
history metadata, and device APIs for both desktop and mobile. It is
deliberately outside the model runtime boundary: Android and desktop do not ask
it for model metadata, model files, or server-side separation. The backend app
does not register `/model/*` or `/separation/*` routes.

## Architectural Principles

### Suppress The Unwanted Source

The dominant strategy is residual suppression:

```text
unwanted = model(mixture, category or speaker reference)
clean = mixture - scale * unwanted
```

For exact-15 category separators, the unwanted estimate may be post-processed
through Wiener-style masking before reconstructing clean audio.

### One Package Contract Across Products

The current design avoids separate "desktop model" and "mobile model" stories.
Each packaged model declares its platform-specific runtime kind, artifact,
sample rate, categories, chunk or segment shape, metadata files, and state
tensors. Desktop and Android read those contracts rather than hard-coding old
assumptions. The backend deliberately does not read model packages because it
is outside model delivery and inference.

### Current Default Is Waveformer Edge

`waveformer_edge_100ms` is the current default because it has a validated
stateful ONNX contract, a small edge artifact, and a 100 ms live chunk surface.
The model supports 20 product labels and runs on CPU ONNX Runtime in the current
packaging.

### Historical Paths Stay Labeled

Native UNet/TFLite, AudioSepHive15Cat-as-default, and several older Waveformer
Python/YAMNet flows are part of the project evolution. They are useful for
explaining decisions and alternatives, but they are not the current product
default unless a manifest is explicitly changed.

## Environment Boundaries

- Windows desktop is the most complete product environment.
- Desktop virtual mic requires VB-CABLE or a compatible virtual audio cable.
- Android live suppression requires a dev client with the native
  `SuppressionEngine` module, ONNX Runtime Android, Oboe, and ExecuTorch
  dependencies.
- Heavy model training/export commands are separate from normal app operation.
- Generated audio datasets, downloaded corpora, and model exports are often
  ignored by Git and must be checked locally before demoing.
