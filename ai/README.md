# TSEBP2025 AI Workspace

This folder is the project-local Python workspace for model experiments,
file-based suppression, export packaging, comparison runs, and audio-routing
helpers. It is intentionally separate from the desktop UI, Android app, and
shared Nest backend.

## Fast Start

From the repository root:

```powershell
cd C:\SoftwareProjects\TSEBP2025

python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\ai\requirements-runtime.txt
python -m pip install -e .

python -m ai --help
python -m ai models list
python -m ai artifacts check
```

Or use the scripted setup:

```powershell
.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime -UpgradePip
```

## Main CLI

The supported front door is:

```powershell
python -m ai --help
tsebp-ai --help
```

Use `python -m ai` when the package is not installed. Use `tsebp-ai` after
`python -m pip install -e .`.

Common commands:

```powershell
python -m ai models list --categories
python -m ai artifacts check
python -m ai diagnostics env

python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --target dog `
  --backend waveformer `
  --aggressiveness 1.1
```

For fixed product categories, `--backend waveformer` uses the packaged
Waveformer ONNX runtime and the same 20-label surface as desktop and Android.

## Model Artifacts

Large generated model files are not committed. A working checkout needs:

```text
ai\models\Exports
```

Restore the portable artifact bundle described in
`docs/project/usage/MODEL_ARTIFACTS.md`, then verify:

```powershell
python -m ai artifacts check --strict
```

## Backend Surfaces

- `waveformer`: default product semantic suppressor.
- `target_speaker`: selected-speaker suppression from a reference clip.
- `audiosep_hive15cat`: optional exact-15 ONNX comparison backend.
- `codecsep_dnrv2_15cat`: optional exact-15 CodecSep ONNX/ExecuTorch backend.
- `codecsep`: research backend for fixed-category and prompt-compatible tests.

List the current local registry:

```powershell
python -m ai models list --categories
```

## Virtual Cable WAV Streaming

This feeds an audio file into a Windows playback endpoint such as VB-CABLE. It
does not run suppression by itself.

```powershell
python -m ai stream wav --list-devices

python -m ai stream wav `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --device-name "CABLE Input" `
  --channels 2 `
  --volume 0.9 `
  --start-silence 1.0
```

The desktop app should capture from the paired recording endpoint, usually
`CABLE Output`.

## Tests

Fast checks:

```powershell
python -m pytest ai\tests\runtime ai\tests\cli -q
```

Opt-in tests use markers and flags:

```powershell
python -m pytest ai\tests -m requires_artifacts --run-artifact-tests
python -m pytest ai\tests -m requires_audio_device --run-audio-device
python -m pytest ai\tests -m manual --run-manual
```

## Folder Roles

- `ai/cli`: Typer CLI commands.
- `ai/ai_runtime`: importable runtime, registry, artifact checks, suppression code.
- `ai/export`: export and package workflows.
- `ai/scripts`: compatibility wrappers and specialized historical utilities.
- `ai/tests`: runtime, CLI, integration, and manual tests.
- `ai/training`: heavy training dependencies and training-side tooling.
