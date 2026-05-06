# Audio Pipeline Deep Dive

This document explains how audio and model metadata move through the current
system. The key idea is that the product path is manifest-driven: choose a
packaged model, load the declared runtime, run category or speaker-conditioned
inference, then reconstruct output audio.

## Shared Model Selection

All product surfaces begin with `ai/models/model_selection.json`.

```text
default_model_id = waveformer_edge_100ms
```

The active package declares platform payloads. For the current default,
Waveformer declares:

- `runtime_kind`: `onnx_streaming_target_extractor`
- desktop artifact:
  `../Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx`
- Android artifact:
  `../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort`
- sample rate: `44100`
- chunk samples: `4416`
- state tensors: `enc_buf`, `dec_buf`, and `out_buf`
- categories: 20 product labels

Desktop resolves the same package at startup. Android copies the same files
into a generated asset bundle during Gradle prebuild. The backend does not
participate in model packaging, delivery, or inference.

The manifest is tracked, but `ai/models/Exports` is generated and ignored by
Git. When those artifacts are absent, the package still describes the correct
runtime truth, but desktop and Android Gradle cannot run the model until the
portable `Exports` folder is present locally.

## Offline Python Flow

```text
input WAV/FLAC
    -> BatchProcessor
    -> SemanticSuppressor
    -> selected backend
    -> unwanted estimate
    -> direct subtraction or post-mask reconstruction
    -> output WAV and optional removed-noise WAV
```

`BatchProcessor` handles file loading, mono/stereo handling, chunking,
overlap-add for long-running exact-category backends, and target-speaker
full-file inference. `SemanticSuppressor` selects a backend:

- `waveformer`: legacy/reference Waveformer path.
- `codecsep`: generic CodecSep path with query-first and compatibility modes.
- `audiosep_hive15cat`: packaged exact-15 AudioSep ONNX category separator.
- `codecsep_dnrv2_15cat`: packaged exact-15 CodecSep DNRv2 ONNX/ExecuTorch
  path.
- `target_speaker`: reference-speaker conditioned suppression.

The Python layer is the best place to inspect algorithmic behavior, but the
desktop and Android apps use their own native runtime code for product live
audio.

## Desktop Live Flow

```text
React Dashboard
    -> desktop-api.ts
    -> Tauri command start_live_monitor
    -> AppState and SharedEngine
    -> CPAL input or Debug WAV source
    -> live processing thread
    -> ONNX Runtime / DSP reconstruction
    -> monitor output or VB-CABLE playback endpoint
```

Important desktop details:

- `config.rs` resolves the active model package and the ONNX Runtime DLL.
- `audio/devices.rs` enumerates input/output devices and marks VB-CABLE roles.
- `audio/live.rs` manages capture/render queues, lookahead, realtime health,
  metrics, Debug WAV input, and output mode.
- `engine/mod.rs` runs either `onnx_streaming_target_extractor` or
  `onnx_category_separator`, depending on the active package.
- Virtual Mic mode writes to `CABLE Input`; the receiving app should select
  `CABLE Output` as its microphone.

The desktop live path is the most complete end-to-end product route for demos:
Debug WAV can feed repeatable audio into the same live machinery used by a real
microphone.

## Android Live Flow

```text
React Native screen/hook
    -> ModelBundleService prepares bundled on-device model
    -> SuppressionEngineService.prepare(...)
    -> native BundleRuntimeStore installs bundled Android asset bundle
    -> InferenceRuntime selects ONNX or ExecuTorch implementation
    -> LiveSuppressionSession starts Oboe/AAudio audio engine first
    -> processor thread runs model inference from native audio rings
    -> status, meter, and finished events return to JS
```

Current Android runtime choices are:

- `onnx_category_separator`
- `onnx_streaming_target_extractor`
- `executorch_category_separator`
- `executorch_streaming_target_extractor`

The generated asset bundle currently uses
`onnx_streaming_target_extractor` for `waveformer_edge_100ms`. The native code
expects a manifest with the category list, runtime kind, sample rate, model
artifact metadata, and either segment timing or streaming state tensors.

The active live audio engine is selected by `audioEngine`. The default is
`auto`, which attempts Oboe/AAudio first and falls back to the Kotlin
`AudioRecord`/`AudioTrack` path if native low-latency streams cannot open. The
audio callbacks do not run ONNX inference; they only move audio through
preallocated native rings. The processor thread uses 100 ms Waveformer chunks
and about 300 ms lookahead for quality-stable realtime behavior.

Status events report the active audio engine, native sample rate, frames per
burst, callback underruns, input overflows, render underruns, queue depth,
limiter hits, fail-open count, and inference p50/p95/p99. On a healthy device,
`audioEngine` should normally be `oboe`, inference p95 should stay below the
100 ms hop budget, and fail-open should remain zero during ordinary use.

## Mobile Backend Boundary

```text
mobile app model preparation
    -> native SuppressionEngine
    -> bundled Android assets
    -> no backend call

mobile-backend
    -> auth
    -> history
    -> devices
```

The backend no longer registers `/model/*` or `/separation/*` endpoints. Model
artifacts, category metadata, state tensor metadata, and runtime kind selection
are all handled by the Android app bundle and native runtime.

## Target-Speaker Flow

Target-speaker suppression is separate from semantic category suppression.

```text
mixture + reference clip
    -> TSExtract ONNX or ClearVoice offline fallback
    -> target speaker estimate
    -> remove_target or isolate_target output
```

The Windows package defaults to TSExtract ONNX. ClearVoice remains available as
an offline quality reference when its native runtime is present. The live
desktop UI blocks unsupported combinations such as ClearVoice realtime.

## Failure Modes To Check First

- Stale docs saying Native UNet/TFLite is current mobile runtime.
- Missing `onnxruntime.dll` in desktop packaging or local runtime lookup.
- Missing ignored model artifacts after a fresh clone.
- VB-CABLE not installed, not detected, or routed backwards.
- Android dev client not rebuilt after native module changes.
- Android bundle manifest not matching the active model package.
- Android runtime panel showing `legacy` because Oboe failed to open on the
  current device or build.
- Inference p95 exceeding the 100 ms hop budget or fail-open increasing during
  normal live use.
- Confusing exact-15 category labels with Waveformer 20-label product labels.
