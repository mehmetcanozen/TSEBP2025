# Troubleshooting

Use this page when a fresh checkout, desktop run, Android run, or audio route
does not behave as expected.

## Model artifacts are missing

Symptoms:

- Desktop cannot load Waveformer.
- Android bundle preparation cannot find `model_fixed.ort`.
- Tests fail even though manifests are present.

Check:

```powershell
cd C:\SoftwareProjects\TSEBP2025
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort
```

Fix: restore `ai/models/Exports` from the portable artifact bundle. See
[Model artifacts](MODEL_ARTIFACTS.md).

## Wrong folder casing

Use:

```text
ai\models\Exports
```

Do not use:

```text
ai\models\exports
```

The capitalized folder is part of the current package contract.

## Android bundle is stale

Check:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part\android
.\gradlew.bat :app:prepareBundledSuppressionModel
.\gradlew.bat :app:mergeDebugAssets
```

Inspect:

```text
mobile-part\android\app\build\generated\suppression-assets\suppression-model-bundle\manifest.json
```

Expected values:

```text
model_id = waveformer_edge_100ms
runtime_kind = onnx_streaming_target_extractor
artifact format = ort
sample_rate = 44100
chunk_samples = 4416
```

## Android native module is unavailable

Rebuild the development client:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part
npm run android
```

Metro reload alone is not enough after native Kotlin, CMake, or C++ changes.

## Android audio engine shows legacy

`legacy` means the Oboe/AAudio path could not open and the app fell back to the
Kotlin `AudioRecord`/`AudioTrack` path.

Check:

```powershell
cd C:\SoftwareProjects\TSEBP2025\mobile-part\android
.\gradlew.bat :app:externalNativeBuildDebug
.\gradlew.bat :app:mergeDebugNativeLibs
```

Then test on a physical Android device when possible. Emulator audio is useful
for smoke testing, but it is not a strong latency benchmark.

## Android inference is too slow

Watch the runtime panel:

```text
inference p95
queue depth
callback underruns
input overflows
render underruns
fail-open count
```

The current target is p95 below the 100 ms hop budget and fail-open count at
zero during normal live use. If the device misses that target, collect runtime
diagnostics before changing model quality settings.

## Desktop Virtual Mic is silent

Check the route:

```text
desktop output sink -> CABLE Input
receiving app microphone -> CABLE Output
```

Then:

- Click Refresh devices in the desktop app.
- Confirm `CABLE Output` is enabled in Windows Sound settings.
- If the receiving app does not expose a microphone selector, set
  `CABLE Output (VB-Audio Virtual Cable)` as the Windows default recording
  device before opening that app:

  ```powershell
  Start-Process control.exe -ArgumentList 'mmsys.cpl,,1'
  ```

- After testing, restore your real microphone as the Windows default recording
  device.
- Use Debug WAV source for a repeatable test.
- Use category `dog` for `speech_barking.wav` on the Waveformer path.

See [Virtual mic](VIRTUAL_MIC.md).

## Target-speaker ONNX fails to load

Check both files:

```powershell
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx.data
```

The `.onnx.data` sidecar is required.

## Backend is unreachable from Android emulator

Use this app URL:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Check the backend from Windows:

```text
http://localhost:4000/api/v1/health
```

Suppression should still be on-device. Backend problems should affect
login/history/device features, not model preparation or audio inference.

## TFLite or Native UNet appears in old notes

Treat those as historical unless a current manifest and runtime code path says
otherwise. The active Android product path is packaged Waveformer ORT through
ONNX Runtime Android.
