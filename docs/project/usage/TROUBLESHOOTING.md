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
python -m ai artifacts check --required-only
```

Fix: restore `ai/models/Exports` from the portable artifact bundle. See
[Model artifacts](MODEL_ARTIFACTS.md).

## Python AI CLI is not available

Symptoms:

- `python -m ai --help` fails.
- `tsebp-ai --help` is not recognized.
- Local model tests still use old `ai.ai_runtime.batch.batch_processor`
  commands.

Fix:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime -UpgradePip
.\.venv\Scripts\Activate.ps1
python -m ai --help
python -m ai models list
```

If the editable script entrypoint is still unavailable, use `python -m ai ...`.
That path does not require `tsebp-ai` to be on PATH.

## AI CLI suppression command fails

First verify the front door and artifacts:

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai diagnostics env
python -m ai artifacts check --required-only
python -m ai suppress file --help
```

Then run a small known sample:

```powershell
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --target dog `
  --backend waveformer
```

If this command fails before inference starts, the issue is usually environment
or artifact restore. If it runs but quality is poor, collect the command,
target category, input file, and output file; that is model behavior, not CLI
routing.

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
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-mobile-android.ps1 -CleanInstall
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

For the standalone WAV feeder, install the optional audio-device profile:

```powershell
.\shared\scripts\setup-ai-runtime.ps1 -Profile audio-device
.\shared\scripts\stream-loopback-wav.ps1 -ListDevices
```

The script now routes through `python -m ai stream wav`, so the same behavior is
available directly:

```powershell
python -m ai stream wav --list-devices
python -m ai stream wav `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --device-name "CABLE Input"
```

## Target-speaker ONNX fails to load

Check both files:

```powershell
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx.data
```

The `.onnx.data` sidecar is required.

## Backend is unreachable from Android emulator

Use this app URL for the Android emulator:

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:4000/api/v1
```

Check the backend from Windows:

```text
http://localhost:4000/api/v1/health
```

For a physical USB device, use ADB reverse:

```powershell
.\shared\scripts\start-mobile-android.ps1 -UseAdbReverseBackend
```

For a physical device on the same Wi-Fi network, use your Windows host LAN IP:

```powershell
.\shared\scripts\start-mobile-android.ps1 -BackendHost "192.168.1.50"
```

Suppression should still be on-device. Backend problems should affect
login/history/device features, not model preparation or audio inference.

## TFLite or Native UNet appears in old notes

Treat those as historical unless a current manifest and runtime code path says
otherwise. The active Android product path is packaged Waveformer ORT through
ONNX Runtime Android.
