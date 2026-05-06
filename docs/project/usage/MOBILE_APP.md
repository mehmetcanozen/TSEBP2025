# Mobile app

The Android app runs suppression on device. It does not call the backend for
model selection, model files, or audio inference.

## Current mobile runtime

```text
React Native UI
-> SuppressionEngine native module
-> bundled Waveformer ORT model
-> ONNX Runtime Android CPU inference
-> native Oboe/AAudio audio engine by default
-> Kotlin AudioRecord/AudioTrack fallback if Oboe cannot open
```

Default model:

```text
model_id: waveformer_edge_100ms
runtime_kind: onnx_streaming_target_extractor
sample_rate: 44100
chunk_samples: 4416
category_count: 20
artifact: model_fixed.ort
```

## Prerequisites

- Restored `ai/models/Exports` bundle
- Node.js and npm
- Android Studio with SDK installed
- Android emulator or physical Android device

The app is an Expo development-client/native Android build because it uses
native audio and model runtime code. It cannot run in the standard Expo Go app.

## Prepare Android assets and run

Preferred scripted launch:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-backend.ps1
.\shared\scripts\start-mobile-android.ps1 -StartEmulator
```

Manual Gradle path:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part\android
.\gradlew.bat :app:prepareBundledSuppressionModel
.\gradlew.bat :app:mergeDebugAssets

cd ..
npm install
npm run android
```

Generated Android assets are build output:

```text
mobile-part\android\app\build\generated\suppression-assets\suppression-model-bundle
```

The durable artifact source remains:

```text
ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort
```

## Backend configuration

The backend is optional for suppression. Use it only for login, profile,
settings, history metadata, and device metadata.

For Android emulator testing, create `mobile-part/.env`:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

The emulator reaches the Windows host through `10.0.2.2`, not `localhost`.

## Runtime checks

In the app runtime panel or logs, verify:

```text
modelId = waveformer_edge_100ms
runtimeKind = onnx_streaming_target_extractor
sampleRate = 44100
categoryCount = 20
audioEngine = oboe on supported devices
inferenceP95Ms < 100 during normal live use
failOpenCount = 0 during normal live use
```

If `audioEngine` is `legacy`, the app is using the compatibility
`AudioRecord`/`AudioTrack` path. That can be acceptable as fallback, but Oboe is
the preferred low-jitter path for real-device quality testing.

## Native build checks

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
npx tsc --noEmit

cd .\android
.\gradlew.bat :app:compileDebugKotlin
.\gradlew.bat :app:externalNativeBuildDebug
.\gradlew.bat :app:mergeDebugNativeLibs
```

## Mobile audio notes

- Keep microphone permission enabled.
- Use a physical device for meaningful latency and audio-quality judgment.
- Emulator microphone behavior depends on host microphone settings.
- Oboe callbacks move samples through native rings; model inference runs off
  the audio callback thread.
- The current quality-stable target uses 100 ms Waveformer hops and about
  300 ms lookahead.

## Related docs

- [Mobile deployment reference](MOBILE_DEPLOYMENT.md)
- [Backend](BACKEND.md)
- [Model artifacts](MODEL_ARTIFACTS.md)
