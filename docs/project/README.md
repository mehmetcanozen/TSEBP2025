# TSEBP2025 Project Documentation

This directory is the structured project handbook for the semantic noise
suppression system. It is written for future developers and for instructor or
reviewer readers who need to understand what the project actually does, how it
is wired, and which parts are current versus historical.

## Current Truth Snapshot

The active product path is a shared packaged-model system. The default model is
`waveformer_edge_100ms`, selected by
[`ai/models/model_selection.json`](../../ai/models/model_selection.json). Its
package lives at
[`ai/models/Waveformer/model_package.json`](../../ai/models/Waveformer/model_package.json)
and declares:

- model family: `waveformer`
- runtime kind: `onnx_streaming_target_extractor`
- desktop runtime: ONNX Runtime CPU
- Android runtime: ONNX Runtime Android CPU
- sample rate: `44100`
- chunk size: `4416` samples, about `100 ms`
- suppression formula: `clean = mixture - aggressiveness * target_chunk`
- generated desktop artifact:
  `ai/models/Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx`
- generated Android artifact:
  `ai/models/Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort`

The same package contract feeds the desktop app and the Android app. The mobile
app runs suppression on device from bundled assets: ONNX Runtime Android CPU for
Waveformer inference, native Oboe/AAudio audio IO first, and the Kotlin
`AudioRecord`/`AudioTrack` path as compatibility fallback. The shared backend
is not part of model delivery or inference. Older docs and experiments mention
AudioSepHive15Cat as a default, `mobile-test`, Native UNet, and TFLite. Those
paths are historical unless a document explicitly says otherwise.

`ai/models/Exports` is the canonical generated-artifact root, but it is ignored
by Git. A fresh clone or a cleaned checkout can have correct manifests while
the actual ONNX/ORT files are absent.

The portable `Exports` zip is currently shared outside Git here:

```text
https://drive.google.com/file/d/1mQq1cagJf5lNTkQqo85s9qRCW1a-hN5c/view?usp=sharing
```

Download it and restore it to `ai/models/Exports` before running Python,
desktop, or Android suppression paths. The detailed restore and verification
steps are in [Model artifacts](usage/MODEL_ARTIFACTS.md).

The Python AI workspace has one supported CLI front door:

```powershell
python -m ai --help
python -m ai models list
python -m ai artifacts check --required-only
```

Install it with `.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime` on a
fresh machine. Legacy script/module paths remain available only as compatibility
wrappers.

## Reading Order

1. [Architecture overview](architecture/overview.md): the whole system and the
   current-vs-historical boundary.
2. [Audio pipeline](architecture/pipeline.md): offline Python, desktop live,
   mobile live, backend API boundary, and target-speaker flow.
3. [Model catalogue](model/README.md): all packaged, supporting, research, and
   historical model assets in one place.
4. [Models and training](codebase/models_and_training.md): model taxonomy,
   exports, scripts, validation status, and future model direction.
5. [Desktop audio](codebase/desktop_audio.md) and
   [desktop logic](codebase/desktop_logic.md): Tauri/Rust live audio plus React
   state and command contracts.
6. [Export and mobile](codebase/export_and_mobile.md): shared model packages,
   Android asset generation, native runtimes, and the mobile/backend boundary.
7. [Shared backend](codebase/backend.md): NestJS/Prisma backend modules, auth
   modes, database model, client wiring, and non-audio boundary.
8. [Model details](knowledge/model_details.md) and
   [semantic mappings](knowledge/semantic_mappings.md): category surfaces,
   mapping behavior, and model-specific semantics.
9. [Usage guide index](usage/README.md): model artifacts, getting started,
   Python CLI, desktop, Virtual Mic, Android, backend, and troubleshooting
   runbooks.

## Subsystem Map

| Subsystem | Main role | Current responsibility |
| --- | --- | --- |
| `ai/ai_runtime` | Python reference/runtime layer | Shared contracts, backend registry, artifact diagnostics, batch suppression, model-specific separators, mapping logic, profiles, target-speaker integration, and tests. |
| `ai/cli` | Python command surface | Typer CLI for `python -m ai` / `tsebp-ai`: suppression, models, artifact checks, comparison, streaming, exports, and diagnostics. |
| `ai/models` | Packaged model source of truth | Shared model selection and per-model package manifests for desktop and Android. |
| `ai/models/Exports` | Generated model artifact root | Canonical Waveformer, TargetSpeakerWindows, AudioSepHive15Cat exact-15, CodecSepDNRv2 exact-15, and ClapSepHive15Cat prototype outputs. Ignored by Git. |
| `ai/export`, `ai/scripts`, `ai/training` | Experiment and packaging tools | Waveformer audit/demo scripts, exact-15 exports, target-speaker Windows export, comparison scripts, and historical TFLite tooling. |
| `desktop` | Windows desktop app | React UI plus Tauri/Rust runtime for offline jobs, live monitor, Debug WAV, VB-CABLE virtual mic routing, and target-speaker workflows. |
| `mobile-part` | Android mobile app | React Native UI/services plus native Android `SuppressionEngine` using bundled on-device ONNX/ExecuTorch model packages and Oboe/AAudio-first live audio. |
| `backend` | Shared NestJS backend | Auth, profiles, settings, history metadata, and devices for desktop and mobile. It does not serve model files or run suppression inference. |

## Usage Guides

| Guide | Purpose |
| --- | --- |
| [Usage index](usage/README.md) | Entry point for operational docs. |
| [Getting started](usage/GETTING_STARTED.md) | First working setup path. |
| [Model artifacts](usage/MODEL_ARTIFACTS.md) | Restore and verify `ai/models/Exports`. |
| [Python CLI](usage/PYTHON_CLI.md) | Typer CLI for file suppression, artifacts, model surfaces, export entrypoints, streaming, and comparison commands. |
| [Desktop app](usage/DESKTOP_APP.md) | Tauri desktop app and target-speaker workflow. |
| [Virtual mic](usage/VIRTUAL_MIC.md) | VB-CABLE routing for desktop cleaned audio. |
| [Mobile app](usage/MOBILE_APP.md) | Android on-device suppression workflow. |
| [Backend](usage/BACKEND.md) | Shared desktop/mobile auth/profile/device backend. |
| [Backend setup](usage/BACKEND_SETUP.md) | Start-to-finish runbook for getting the shared backend running. |
| [Troubleshooting](usage/TROUBLESHOOTING.md) | Common setup and runtime failures. |

## Current Model Families

- `waveformer_edge_100ms`: current default product backend and the only
  documented default for desktop/mobile live suppression.
- `audiosep_hive15cat`: exact-15 ONNX category separator. Useful as a packaged
  alternative and comparison target, but not the default.
- `codecsep_dnrv2_15cat`: frozen exact-15 CodecSep path with desktop ONNX and
  Android ExecuTorch package contracts. Useful as an export/runtime experiment
  and alternative backend.
- `target_speaker_windows`: Windows desktop target-speaker suppression package.
  The default engine is TSExtract ONNX; ClearVoice is an offline quality
  fallback, not the normal live path.
- Native UNet/TFLite: superseded mobile experiment. Keep it in history, but do
  not describe it as the current Android runtime.

## Documentation Rules

When updating these docs, treat manifests and code as the source of truth before
preserving old prose:

- `ai/models/model_selection.json`
- `ai/models/*/model_package.json`
- `desktop/src-tauri/src/config.rs`
- `desktop/src-tauri/src/engine/`
- `desktop/src-tauri/src/audio/`
- `mobile-part/android/app/build.gradle`
- `mobile-part/android/app/src/main/cpp/`
- `mobile-part/android/app/src/main/java/.../suppression/`
- `backend/src/`

If a historical path is mentioned, label it as historical, superseded, or
experimental in the same paragraph.
