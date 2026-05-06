# Desktop app

The desktop app is the Windows product shell. It combines the React UI, Tauri
commands, Rust audio runtime, packaged Waveformer ONNX inference, local monitor
playback, optional VB-CABLE routing, and target-speaker workflows.

## Prerequisites

- Node.js and npm
- Rust/Cargo
- WebView2 runtime
- Restored `ai/models/Exports` bundle
- VB-CABLE only if you want Virtual Mic mode

## Run the app

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop
npm install
npm run tauri:dev
```

If Cargo is not on `PATH`, add it for the current terminal:

```powershell
$env:Path += ";$env:USERPROFILE\.cargo\bin"
```

## Semantic suppression path

The current default model is `waveformer_edge_100ms`.

```text
desktop UI
-> Tauri command
-> Rust live/offline audio engine
-> Waveformer desktop ONNX
-> clean audio output
```

The desktop artifact comes from:

```text
ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx
```

Use the category id `dog` for barking demos on the Waveformer path.

## Live modes

| Mode | What it does |
| --- | --- |
| Listen locally | Plays cleaned audio to the selected monitor output. |
| Virtual mic | Writes cleaned audio to `CABLE Input` for other apps to record from `CABLE Output`. |
| Debug WAV source | Feeds a WAV file through the live path as if it were microphone input. |

Use Debug WAV source for repeatable demos and regression checks. It exercises
the live machinery instead of using a separate offline shortcut.

For apps that do not expose their own microphone picker, Windows must use
`CABLE Output` as the default recording device. The full Windows routing steps
are in [Virtual mic](VIRTUAL_MIC.md).

## Target-speaker mode

Target-speaker suppression uses a reference speaker clip instead of semantic
categories.

Current package:

```text
ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\windows_bundle_manifest.json
```

Engine policy:

| Engine | Role |
| --- | --- |
| TSExtract ONNX | Default desktop engine and the live-capable path. |
| ClearVoice native bundle | Optional offline quality fallback. |

Required TSExtract files:

```text
ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx
ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx.data
```

The `.onnx.data` sidecar is part of the model. If it is missing, the ONNX file
is incomplete.

## Useful checks

```powershell
cd C:\SoftwareProjects\TSEBP2025

Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\windows_bundle_manifest.json
Test-Path .\desktop\src-tauri\runtime\onnxruntime.dll
```

Rust build check:

```powershell
cd C:\SoftwareProjects\TSEBP2025\desktop\src-tauri
& "$env:USERPROFILE\.cargo\bin\cargo.exe" check
```

## Related docs

- [Virtual mic](VIRTUAL_MIC.md)
- [Model artifacts](MODEL_ARTIFACTS.md)
- [Desktop audio architecture](../codebase/desktop_audio.md)
- [Desktop logic architecture](../codebase/desktop_logic.md)
