# Target Speaker Windows

## Status

Packaged Windows desktop target-speaker model. It is not a semantic category
model.

Package:

```text
ai/models/TargetSpeakerWindows/model_package.json
```

Generated/exported assets:

```text
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/
```

## Purpose

Target-speaker suppression uses a reference clip to identify a speaker in a
mixture. It can remove the matching speaker or isolate that speaker, depending
on the requested output mode.

Core formula:

```text
target = f(mixture, reference)
clean = mixture - removal_scale * target
```

## Default Engine: TSExtract ONNX

Runtime contract:

| Field | Value |
| --- | --- |
| Runtime kind | `target_speaker_windows_bundle` |
| Default engine | `tsextract_onnx` |
| Sample rate | `8000` |
| Mixture samples | `80000` |
| Reference samples | `24000` |
| Output | `target` |
| External data | `tsextract_fp32.onnx.data` |

Required TSExtract files:

```text
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/tsextract_onnx/tsextract_fp32.onnx
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/tsextract_onnx/tsextract_fp32.onnx.data
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/tsextract_onnx/tsextract_fp32.manifest.json
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/tsextract_onnx/tsextract_fp32.validation.json
```

The `.onnx.data` sidecar is required. Without it, ONNX Runtime cannot load the
model correctly.

## Optional Engine: ClearVoice Bundle

ClearVoice is packaged as an offline quality fallback:

```text
ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/desktop/clearvoice_native/
```

It is not the default live engine. Desktop UI/runtime logic should use TSExtract
ONNX for fast/default behavior and treat ClearVoice as offline-only. The
ClearVoice `.venv` is installed after packaging by running the generated
installer; it is not bundled as a generated export artifact.

## Related Workspace: SpeakerSeperator

Folder:

```text
ai/models/SpeakerSeperator
```

This is the target-speaker toy/project workspace used to explore saved speaker
profiles, TSExtract/TSExcalibur, ClearVoice, sample audio, and Windows export
docs. The folder name is misspelled in the repo; keep the spelling when
referring to paths. It is not the deployable export destination; deployable
desktop artifacts belong under `ai/models/Exports/TargetSpeakerWindows/`.

## Product Usage

Desktop target-speaker features use:

- speaker reference/profile data
- `target_speaker_windows` package metadata
- TSExtract ONNX by default
- optional ClearVoice offline fallback

Android does not currently package `target_speaker_windows`.

## Common Confusions

- Target speaker is not `speech` category suppression.
- It ignores semantic category lists and uses a reference speaker instead.
- ClearVoice is a bundled optional engine, not the default live path.
- Missing ONNX external data is a packaging failure, not a UI issue.
