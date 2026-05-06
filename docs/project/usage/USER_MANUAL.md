# User manual

This manual is the compact operator overview. For setup and copyable commands,
use the focused guides in [Usage guide index](README.md).

## What the system does

TSEBP2025 Semantic Hearing removes selected unwanted sounds from local audio. The
common product pattern is:

```text
choose target category or target speaker
-> estimate the unwanted source
-> subtract or mask that unwanted source
-> output cleaner audio
```

Current product-facing modes:

- Python file-based suppression
- Windows desktop live monitor
- Windows desktop Virtual Mic through VB-CABLE
- Windows target-speaker suppression
- Android on-device live suppression
- Shared backend account/profile/settings/history/device support

## Current defaults

| Concern | Current answer |
| --- | --- |
| Semantic default | `waveformer_edge_100ms` |
| Android inference | On-device Waveformer ORT through ONNX Runtime Android CPU |
| Android audio engine | Oboe/AAudio first, Kotlin `AudioRecord`/`AudioTrack` fallback |
| Desktop semantic inference | Waveformer ONNX through ONNX Runtime CPU |
| Desktop target-speaker engine | TSExtract ONNX by default, ClearVoice as offline fallback |
| Backend | Shared auth, profiles, settings, history metadata, and devices only |

Native UNet, TFLite, `mobile-test`, `WFExports`, and lowercase `exports` are
historical paths, not the active product runtime.

## Current Waveformer categories

```text
alarm_clock, baby_cry, birds_chirping, cat, car_horn,
cock_a_doodle_doo, cricket, computer_typing, dog, glass_breaking,
gunshot, hammer, music, ocean, door_knock, singing, siren,
speech, thunderstorm, toilet_flush
```

Use `dog` for barking demos on the current Waveformer path. Exact-15
alternatives use labels such as `dog barking` and `keyboard typing`.

## Choose the right guide

| Task | Guide |
| --- | --- |
| First-time setup | [Getting started](GETTING_STARTED.md) |
| Restore model artifacts | [Model artifacts](MODEL_ARTIFACTS.md) |
| Run file-based suppression | [Python CLI](PYTHON_CLI.md) |
| Run the Windows desktop app | [Desktop app](DESKTOP_APP.md) |
| Route desktop output as a microphone | [Virtual mic](VIRTUAL_MIC.md) |
| Run Android on-device suppression | [Mobile app](MOBILE_APP.md) |
| Run app account/history backend | [Backend](BACKEND.md) |
| Fix a broken setup | [Troubleshooting](TROUBLESHOOTING.md) |

## Windows desktop user UI

The normal desktop launch opens a clean operator UI:

```powershell
cd C:\SoftwareProjects\TSEBP2025
.\shared\scripts\start-desktop.ps1
```

The user UI is split into four task areas:

| Area | Purpose |
| --- | --- |
| `Live` | Start or stop realtime semantic or speaker suppression. |
| `File Render` | Process an input WAV and write a cleaned WAV. |
| `Speaker Profiles` | Save and reuse reference clips for speaker suppression. |
| `Status` | Check virtual microphone readiness, live health, and file progress. |

Developer-only diagnostics are not shown in this UI. Use the dev/debug launch
only for repeatable routing checks and transmission diagnostics:

```powershell
.\shared\scripts\start-desktop.ps1 -DevUi
```

## Fresh-checkout rule

A clone with correct manifests can still be incomplete. Before debugging code,
download the portable `Exports` zip and verify the artifact bundle is restored:

```text
https://drive.google.com/file/d/1mQq1cagJf5lNTkQqo85s9qRCW1a-hN5c/view?usp=sharing
```

```powershell
cd C:\SoftwareProjects\TSEBP2025
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx
Test-Path .\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort
Test-Path .\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\windows_bundle_manifest.json
```

All three should print `True` for the current product setup.
