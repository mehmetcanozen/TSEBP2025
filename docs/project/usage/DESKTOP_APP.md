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
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-backend.ps1
.\shared\scripts\start-desktop.ps1
```

The default launch opens the clean user UI. It is organized into four task
areas: `Live`, `File Render`, `Speaker Profiles`, and `Status`.

Launch the dev/debug UI only when you need routing diagnostics:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-desktop.ps1 -DevUi
```

The dev/debug UI keeps the full diagnostics, but splits them into task areas:
`Semantic Debug`, `Speaker Debug`, `Transmission`, and `Runtime/Devices`. That
is where Debug WAV source controls, Transmission Test, Loopback Monitor,
runtime/provider details, and device inspection live. The script writes
`VITE_DESKTOP_UI_SURFACE=user` or
`VITE_DESKTOP_UI_SURFACE=dev` into `desktop/.env`. A URL query can override it:
`?ui=user` or `?ui=dev`.

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

## User UI live modes

| Mode | What it does |
| --- | --- |
| Semantic live | Removes selected sound categories from the microphone path. |
| Speaker live | Uses a speaker reference clip or profile to suppress or extract that speaker. |
| Virtual mic output | Writes cleaned audio to `CABLE Input` for other apps to record from `CABLE Output`. |

Debug WAV source and transmission diagnostics are intentionally hidden from the
default user UI. Use `.\shared\scripts\start-desktop.ps1 -DevUi` for repeatable
developer demos and regression checks.

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
