# Export, Packaging, Mobile, And Backend

The current edge-deployment story is not "export a `.tflite` and place it in
the app." It is a shared packaged-model workflow: define a package manifest,
let desktop and Android read it, and ship the platform artifacts declared by
that package. The backend stays generic and does not participate in model
delivery or inference.

## Package Contract

The shared selection file is:

```text
ai/models/model_selection.json
```

Each package listed there points to a `model_package.json`. The package must
declare at least:

- `model_id`
- `package_version`
- `family`
- `display_name`
- `suppression_strategy`
- `categories`
- `presets`
- `platforms.desktop` and/or `platforms.android`

Platform payloads define the runtime contract:

```text
runtime_kind
artifact
metadata_artifacts
sample_rate
segment_seconds / overlap_seconds, or chunk_samples
preferred_live_hop_ms
mix_channels
state_tensors, if streaming
```

## Current Waveformer Package

The active package is `waveformer_edge_100ms`. Desktop uses the ONNX Runtime
CPU optimized ONNX artifact:

```text
runtime_kind: onnx_streaming_target_extractor
artifact: ../Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx
metadata: ../Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx.json
```

Android uses the same streaming tensor contract, but the packaged model file is
the ORT-format artifact and reduced-build operator config:

```text
runtime_kind: onnx_streaming_target_extractor
artifact: ../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort
metadata: ../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort.json
required_ops: ../Exports/Waveformer/waveformer_edge_100ms/android/required_operators.config
sample_rate: 44100
chunk_samples: 4416
preferred_live_hop_ms: 100
mix_channels: 2
```

The generated Android bundle manifest should therefore report
`model_id=waveformer_edge_100ms` and
`runtime_kind=onnx_streaming_target_extractor`.

## Waveformer Export Layout

`ai/export` is code-only. Generated deployable artifacts live under:

```text
ai/models/Exports/Waveformer/waveformer_edge_100ms/
```

Expected subfolders:

- `source/`: canonical copy of the trusted source ONNX plus source metadata.
- `desktop/`: ONNX Runtime CPU optimized desktop ONNX plus sidecar metadata.
- `android/`: ORT-format `model_fixed.ort`, `model_fixed.ort.json`, and
  `required_operators.config`.

The packager is:

```powershell
python -m ai.export.export_waveformer_edge `
  --out-root .\ai\models\Exports\Waveformer\waveformer_edge_100ms `
  --package-version waveformer_edge_100ms_exports_20260505 `
  --write-package
```

The default source resolution is intentionally centered on `Exports`: use the
canonical source copy under `source/` when it exists, then recover from a known
generated Android build cache when available. If neither exists, restore the
trusted 100 ms Waveformer ONNX from artifact storage before running the
packager. Do not describe older pre-cleanup Waveformer folders as active export
destinations.

## Exact-15 Export Layout

AudioSepHive15Cat and CodecSepDNRv2_15Cat are packaged alternatives, not the
current default, but their generated payloads follow the same centralized
artifact rule. `ai/export` is code-only, and `ai/models/<ModelName>` keeps the
package manifest/source identity.

AudioSepHive15Cat:

```text
ai/models/Exports/AudioSepHive15Cat/audiosep_hive15cat_exact15/
  shared/frozensep_hive_15cat.onnx
  shared/categories_15.yaml
  shared/categories_15.txt
  source/category_embeddings.pt
```

Both desktop and Android package entries point at the same shared ONNX artifact
because this package currently uses `onnx_category_separator` on both
platforms.

CodecSepDNRv2_15Cat:

```text
ai/models/Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/
  source/codecsep_dnrv2_15cat_frozen.pt
  source/embedding_init.pt
  source/freeze_manifest.json
  source/freeze_spec_15.yaml
  shared/categories_15.yaml
  shared/categories_15.txt
  desktop/codecsep_dnrv2_15cat.onnx
  desktop/codecsep_dnrv2_15cat.onnx.json
  android/codecsep_dnrv2_15cat.pte
  android/codecsep_dnrv2_15cat.pte.json
```

The desktop package entry uses the ONNX artifact. The Android entry uses the
ExecuTorch `.pte` artifact. Runtime helpers in `ai/ai_runtime/utils/paths.py`
resolve to these canonical paths.

ClapSepHive15Cat is prototype/history only. Its generated files are centralized
under:

```text
ai/models/Exports/ClapSepHive15Cat/clapsep_hive15cat_prototype/
```

It is not listed in `model_selection.json`, so desktop or mobile product
packaging should not treat it as an active package.

## Android Asset Generation

`mobile-part/android/app/build.gradle` registers
`prepareBundledSuppressionModel`. That task:

1. Reads `ai/models/model_selection.json`.
2. Resolves the active package, unless overridden by Gradle property or
   environment.
3. Copies the Android artifact and metadata into
   `mobile-part/android/app/build/generated/suppression-assets/`.
4. Writes `suppression-model-bundle/manifest.json`.
5. Adds generated assets to the Android source set before build.

The Android app receives package metadata from the bundled asset manifest. It
does not request model metadata or artifacts from the backend at runtime.

## Android Native Runtime

The React Native service layer is in:

- `mobile-part/services/ModelBundleService.ts`
- `mobile-part/services/SuppressionEngineService.ts`
- `mobile-part/hooks/useSuppressionDemo.ts`

The native Android runtime is in:

- `SuppressionEngineModule.kt`
- `suppression/BundleRuntimeStore.kt`
- `suppression/InferenceRuntime.kt`
- `suppression/LiveSuppressionSession.kt`
- `suppression/NativeOboeAudioEngine.kt`
- `mobile-part/android/app/src/main/cpp/native_oboe_audio_engine.cpp`

`InferenceRuntime.kt` supports:

- `onnx_category_separator`
- `onnx_streaming_target_extractor`
- `executorch_category_separator`
- `executorch_streaming_target_extractor`

The current generated bundle uses the ONNX streaming target-extractor path.
ExecuTorch support exists for packaged models that declare it, such as
CodecSepDNRv2 exact-15 on Android.

Live audio is selected separately from model runtime. `audioEngine: "auto"` is
the default JS/native contract. It attempts the native Oboe/AAudio engine first,
using low-latency input/output streams and preallocated native rings, then
falls back to the Kotlin `AudioRecord`/`AudioTrack` path if native stream
creation fails. ONNX/ExecuTorch inference remains on a processor thread; audio
callbacks do not run model inference or file IO.

The mobile status event includes the active audio engine, native sample rate,
frames per burst, callback underruns, input overflows, render underruns, queue
depth, and inference p50/p95/p99. These diagnostics are the first place to
check whether a device is actually meeting the 100 ms Waveformer hop budget.

## Shared Backend Boundary

The shared backend is not a model-distribution service. The active NestJS app
registers auth, profile, settings, history metadata, and device routes only. It
does not register `/model/*` or `/separation/*`, and Android model preparation
must succeed from the on-device bundle without a backend call.

`ModelBundleService.ts` is therefore intentionally small: it calls native
`SuppressionEngine.prepare()` and lets `BundleRuntimeStore.kt` install the
already-packaged Android asset bundle.

## Export Tooling

Export scripts are still useful, but their output must be connected to a package
manifest before it becomes product runtime:

- The preferred command surface is `python -m ai export ...`; it keeps export
  entrypoints discoverable without requiring developers to remember individual
  file paths.
- Waveformer ONNX audit/export utilities live in `ai/scripts` and `ai/export`.
- AudioSepHive15Cat is a packaged exact-15 ONNX separator.
- CodecSepDNRv2 exact-15 export creates ONNX and ExecuTorch artifacts plus
  metadata.
- Target-speaker export creates a Windows bundle with TSExtract ONNX and
  optional ClearVoice runtime.
- TFLite export scripts are historical and should not be used to describe the
  current Android product path.

Useful front-door commands:

```powershell
python -m ai artifacts check --required-only
python -m ai models list
python -m ai export waveformer-edge --help
python -m ai export target-speaker-windows --help
```

The old module paths remain available for compatibility and should print a
short legacy-path notice when invoked directly.

## Target-Speaker Desktop Export Layout

`ai/export/export_target_speaker_windows.py package-desktop` is the canonical
Windows target-speaker packager. It writes generated artifacts under:

```text
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/
```

Expected subfolders:

- `source/`: canonical TSExtract FP32 ONNX source copy and `.onnx.data`.
- `desktop/tsextract_onnx/`: ONNX Runtime CPU optimized desktop copy,
  manifest, external-data sidecar, and validation report.
- `desktop/clearvoice_native/`: slim native ClearVoice runtime assets without
  a generated `.venv`; run the generated installer after packaging when the
  offline quality engine is needed.

`ai/models/TargetSpeakerWindows/model_package.json` should point at the
`desktop/windows_bundle_manifest.json` file in that tree. `ai/models/SpeakerSeperator`
is only the source/toy workspace and should not be used as a deployable output
root.

## Mobile Deployment Checklist

1. Confirm `model_selection.json` selects the intended model.
2. Confirm the selected package has an Android platform payload.
3. Confirm the package artifact and metadata files exist.
4. Run or trigger Gradle so `prepareBundledSuppressionModel` writes the
   generated bundle.
5. Rebuild the Android dev client after native code changes.
6. Check `SuppressionEngine.prepare()` runtime info in the app.
7. Start live suppression and confirm status reports `audioEngine=oboe` on
   supported devices, inference p95 under the 100 ms hop budget, and fail-open
   remaining zero.
8. Confirm the backend logs show no model update/download or separation
   requests during model preparation and live suppression.

## Historical Boundary

Older docs that mention `mobile-test`, Native UNet, or `react-native-fast-tflite`
describe a superseded mobile experiment. The current Android code uses a native
bundle runtime with ONNX Runtime Android and ExecuTorch dependencies.
