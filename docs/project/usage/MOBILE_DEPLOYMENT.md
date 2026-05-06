# Android Mobile Deployment Guide

This guide describes the current Android suppression path in `mobile-part`.
Older project notes may mention `mobile-test`, Native UNet, or TFLite. Those are
historical. The current Android runtime uses packaged suppression model bundles
with ONNX Runtime Android and ExecuTorch-capable native code.

For the shorter operator runbook, see [Mobile app](MOBILE_APP.md).

## Current Architecture

```text
ai/models/model_selection.json
    -> selected model_package.json
    -> Gradle prepareBundledSuppressionModel
    -> generated Android asset bundle
    -> native SuppressionEngine.prepare()
    -> BundleRuntimeStore
    -> InferenceRuntime
    -> LiveSuppressionSession
    -> Oboe/AAudio audio engine by default
    -> Kotlin AudioRecord/AudioTrack fallback
```

The default generated bundle is:

```text
model_id: waveformer_edge_100ms
runtime_kind: onnx_streaming_target_extractor
sample_rate: 44100
chunk_samples: 4416
artifact: model_fixed.ort
```

The generated manifest is expected at:

```text
mobile-part/android/app/build/generated/suppression-assets/suppression-model-bundle/manifest.json
```

## Source Files To Know

| File | Role |
| --- | --- |
| `mobile-part/android/app/build.gradle` | Generates the bundled suppression model assets from shared package manifests. |
| `mobile-part/services/ModelBundleService.ts` | Calls native prepare for the bundled on-device model. |
| `mobile-part/services/SuppressionEngineService.ts` | TypeScript wrapper around the native `SuppressionEngine` module. |
| `mobile-part/hooks/useSuppressionDemo.ts` | UI-facing hook for prepare/start/stop, meters, recording, and finished events. |
| `SuppressionEngineModule.kt` | Native React module entrypoint. |
| `BundleRuntimeStore.kt` | Installs bundled Android asset model bundles and parses manifests. |
| `InferenceRuntime.kt` | Selects ONNX or ExecuTorch implementation from `runtime_kind`. |
| `LiveSuppressionSession.kt` | Owns live-session lifecycle, starts Oboe first, runs processor-thread inference, handles fallback audio, and emits status/meter/finished events. |
| `NativeOboeAudioEngine.kt` | Kotlin JNI wrapper for the native Oboe/AAudio audio engine. |
| `mobile-part/android/app/src/main/cpp/native_oboe_audio_engine.cpp` | C++ Oboe callback engine and native audio rings. |

## Build-Time Bundle Generation

Gradle task:

```text
prepareBundledSuppressionModel
```

This task reads the active model package and writes a complete asset bundle.
The generated manifest includes model id, package version, runtime kind, sample
rate, categories, artifact hashes, and streaming/segment shape.

To inspect the current generated bundle:

```powershell
cd C:\SoftwareProjects\TSEBP2025
Get-Content .\mobile-part\android\app\build\generated\suppression-assets\suppression-model-bundle\manifest.json
```

If this file is missing or stale, run an Android Gradle build or `expo
run:android` from `mobile-part` so the Gradle task runs.

## Native Runtime Kinds

`InferenceRuntime.kt` supports:

- `onnx_category_separator`: ONNX Runtime category separator, used by
  AudioSepHive15Cat-style packages.
- `onnx_streaming_target_extractor`: ONNX Runtime streaming target extractor,
  used by the current Waveformer default.
- `executorch_category_separator`: ExecuTorch category separator, used by
  CodecSepDNRv2 exact-15 Android packaging.
- `executorch_streaming_target_extractor`: reserved for streaming target
  extractor packages exported to ExecuTorch.

The current default uses ONNX Runtime Android CPU.

## Live Audio Engine

`SuppressionEngine.startLive()` accepts `audioEngine`, with this default:

```text
audioEngine: auto
```

`auto` attempts the native Oboe/AAudio path first. If Oboe cannot open on the
device, the app falls back to the older Kotlin `AudioRecord`/`AudioTrack` path.
The Oboe callbacks are intentionally small: they move audio through preallocated
native rings and do not run ONNX inference. Waveformer inference runs on a
processor thread with the current quality-stable defaults:

```text
hop: 100 ms
lookahead: about 300 ms
provider: ONNX Runtime Android CPU
post-filter: off
quantization: none by default
```

The runtime panel/status events expose the active audio engine, native sample
rate, frames per burst, queue depth, callback underruns, input overflows, render
underruns, fail-open count, and inference p50/p95/p99. On a healthy device,
`audioEngine` should be `oboe`, inference p95 should stay under the 100 ms hop
budget, and fail-open should remain zero.

## Backend Boundary

The Android model path is local-only. `ModelBundleService.ts` does not call
`/model/latest`, and `BundleRuntimeStore.kt` does not download model bundles.
The shared NestJS backend is for auth, profiles, settings, history metadata,
and device metadata; it is not needed to prepare the suppression model or run
live inference.

## Local Development Steps

From the repo root:

```powershell
cd C:\SoftwareProjects\TSEBP2025
Test-Path .\ai\models\model_selection.json
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\required_operators.config
```

From the mobile app:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
npm install
npm run android
```

`npm run android` invokes Expo's Android build path and should trigger Gradle's
model-bundle task. If native code changes, rebuild the dev client; Metro reload
alone is not enough.

## Runtime Smoke Checks

In the app or logs, verify that `SuppressionEngine.prepare()` reports:

```text
modelId = waveformer_edge_100ms
runtimeKind = onnx_streaming_target_extractor
sampleRate = 44100
categoryCount = 20
provider includes onnxruntime-cpu or cpu
audioEngine = oboe, or legacy only if Oboe is unavailable on the device
inferenceP95Ms < 100 during normal live use
```

Then check:

- categories load from native runtime
- start live returns a session id
- status and meter events arrive
- stop live emits/handles the finished event
- recording save, if enabled, waits for native drain/cleanup
- backend logs do not show `/model/*` or `/separation/*` requests

## Troubleshooting

### Native Module Unavailable

Error text may say the `SuppressionEngine` native module is unavailable. Rebuild
the Android dev client after native changes:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
npm run android
```

### Stale Or Missing Bundle

Check the generated manifest path. If it does not exist, the Gradle task did
not run or failed. Check that the active package artifact exists under
`ai/models`.

### Backend Requests During Model Preparation

Model preparation should not call the backend. If backend logs show `/model/*`
or `/separation/*` requests from the app, check for stale JavaScript/native code
or an old installed dev client.

### Audio Engine Shows `legacy`

`legacy` means the Oboe path was unavailable or failed to open and the app used
the Kotlin `AudioRecord`/`AudioTrack` fallback. Rebuild the app after native
changes, confirm the native library is packaged, and test on a real Android
device when emulator audio behavior is suspect.

Useful build checks:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part\android
.\gradlew.bat :app:compileDebugKotlin
.\gradlew.bat :app:externalNativeBuildDebug
.\gradlew.bat :app:mergeDebugNativeLibs
```

### TFLite References

Some dependencies or old docs may still mention TFLite. Treat those as
historical unless the current native module is changed to use them again. The
current product runtime is ONNX/ExecuTorch bundle based.

## Historical Note

Native UNet/TFLite was explored because complex Waveformer exports were hard to
lower to TFLite. That decision has been superseded by the shared packaged-model
runtime described in
`../architecture/decision_records/ADR-002-shared-packaged-model-runtime.md`.
