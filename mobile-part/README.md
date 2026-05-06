# Semantic Noise Suppression Mobile App

This React Native Android app validates the on-device suppression pipeline for
the shared packaged model runtime. The current default model is
`waveformer_edge_100ms`, packaged from `ai/models/Waveformer/model_package.json`
and copied into Android assets by the Gradle `prepareBundledSuppressionModel`
task.

Older notes may mention `mobile-test`, Native UNet, or TFLite. Those are
historical experiments. The active Android path uses ONNX Runtime Android and
accepts ONNX/ORT packaged artifacts.

## Build Inputs

- Shared model selection: `ai/models/model_selection.json`
- Waveformer package manifest: `ai/models/Waveformer/model_package.json`
- Canonical Android artifact:
  `ai/models/Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort`
- Android bundle output:
  `mobile-part/android/app/build/generated/suppression-assets/suppression-model-bundle/`

## Prepare Bundled Model

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part\android
.\gradlew.bat :app:prepareBundledSuppressionModel
```

The generated bundle manifest should report:

- `model_id`: `waveformer_edge_100ms`
- `runtime_kind`: `onnx_streaming_target_extractor`
- model artifact format: `ort`
- sample rate: `44100`
- chunk samples: `4416`

## Run Android

Install Java/Android tooling, connect a device or emulator, then run:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-mobile-android.ps1 -StartEmulator
```

The app uses native modules, so it cannot run inside standard Expo Go.

## App Data Backend

The mobile app uses the shared backend in `backend/` for account, profile,
settings, history metadata, and device registration only. For the Android
emulator, set:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Use script arguments instead of editing source when the backend host differs:

```powershell
# Android emulator default.
.\shared\scripts\start-mobile-android.ps1

# Physical USB device through adb reverse.
.\shared\scripts\start-mobile-android.ps1 -UseAdbReverseBackend

# Physical device over Wi-Fi.
.\shared\scripts\start-mobile-android.ps1 -BackendHost "192.168.1.50"
```

The app calls only the shared backend for app data. It does not call backend
model or separation routes. Suppression remains on device.

## Live Audio Runtime

Live suppression is on-device end to end:

- `SuppressionEngine.prepare()` installs the bundled Android asset copy.
- `SuppressionEngine.startLive()` defaults to `audioEngine: "auto"`.
- `"auto"` starts the native Oboe/AAudio-backed audio engine first and falls
  back to the Kotlin `AudioRecord`/`AudioTrack` path if the native stream cannot
  open on a device.
- Model inference remains on a processor thread; the native audio callbacks only
  move samples through preallocated rings.
- The default live target is quality-stable realtime: 100 ms Waveformer hops,
  300 ms lookahead, ONNX Runtime CPU, no default post-filter, and no default
  quantization or accelerator path.

The runtime status panel reports the active audio engine, native sample rate,
frames per burst, inference p95, queue depth, callback underruns, input
overflows, render underruns, limiter hits, fail-open count, and boundary repair
count. For device validation, Oboe should stay selected as the audio engine,
inference p95 should remain under the 100 ms hop budget, and fail-open should
stay at zero during ordinary live use.

## Model Boundary

Model preparation is local-only. `ModelBundleService` calls the native
`SuppressionEngine.prepare()` method, and `BundleRuntimeStore` installs the
bundle that is already packaged in Android assets. The mobile app does not call
backend model update/download endpoints and does not upload audio for backend
suppression.
