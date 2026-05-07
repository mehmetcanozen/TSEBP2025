# Python AI CLI

The Python AI workspace is the fastest place to test model artifacts,
file-based suppression, comparison runs, and VB-CABLE WAV streaming. Run
commands from the repository root.

## Setup

```powershell
cd C:\SoftwareProjects\TSEBP2025

python -m venv .\.venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\ai\requirements-runtime.txt
python -m pip install -e .
```

Shortcut:

```powershell
.\shared\scripts\setup-ai-runtime.ps1 -Profile runtime -UpgradePip
```

Use `python -m ai` before editable install, or `tsebp-ai` after editable
install.

The `runtime` profile is intentionally lightweight and does not install
PyTorch. It is enough for CLI diagnostics, artifact checks, ONNX-backed
Waveformer suppression, and VB-CABLE WAV streaming. Legacy PyTorch/CodecSep or
training/export paths need a heavier environment/profile.

## First Checks

```powershell
python -m ai --help
python -m ai models list --categories
python -m ai artifacts check
python -m ai diagnostics env
```

`artifacts check` verifies the restored `ai/models/Exports` bundle. If required
artifacts are missing, restore the bundle before debugging runtime code.

`models list --packages` also shows registered research packages. The current
raw research packages are:

- `audiosep_open_vocab`: vanilla AudioSep text-query runtime. Its tracked
  manifest is `ai/models/AudioSepOpenVocab/model_package.json`; the heavyweight
  source/checkpoints live in ignored `ai/models/AudioSep`.
- `audiosep_hive_raw`: `ai/models/AudioSep-Hive`, raw AudioSep-Hive checkpoint.
- `clapsep_research`: `ai/models/CLAPSep`, raw CLAPSep source/checkpoints.

`audiosep_open_vocab` is used through `--audiosep-prompt`, not as a
`--backend` enum value. The raw Hive and CLAPSep packages are intentionally not
exposed as `suppress file --backend` choices, but they are runnable through the
evaluation adapters.

## Default Waveformer File Suppression

For fixed product categories such as `dog`, `--backend waveformer` uses the
packaged Waveformer ONNX runtime and the same 20-label surface as desktop and
Android.

```powershell
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --target dog `
  --backend waveformer `
  --aggressiveness 1.1 `
  --output-noise
```

Waveformer uses the product category `dog` for barking demos. Exact-15
comparison backends use labels such as `dog barking`.

## Selected Speaker Suppression

```powershell
python -m ai suppress target-speaker `
  --input .\ai\data\audio\raw\conversation.wav `
  --reference .\ai\data\audio\raw\speaker_reference.wav `
  --output .\ai\data\audio\processed\conversation_target_removed.wav `
  --engine tsextract_onnx `
  --device cpu
```

The TSExtract ONNX path needs both `tsextract_fp32.onnx` and
`tsextract_fp32.onnx.data`.

## Vanilla AudioSep Open-Vocabulary And Suppress-All Paths

```powershell
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_boat.wav `
  --output .\ai\data\audio\processed\speech_boat_audiosep.wav `
  --audiosep-prompt "boat engine, water noise"

python -m ai suppress file `
  --input .\ai\data\audio\raw\noisy_speech.wav `
  --output .\ai\data\audio\processed\noisy_speech_suppress_all.wav `
  --suppress-all
```

`--audiosep-prompt` is the preferred name for the vanilla AudioSep
open-vocabulary path. Older scripts may still accept `--universal` as a legacy
alias, but new docs and examples should use the AudioSep naming.

## Exact-15 Comparison Backends

```powershell
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_alarm.wav `
  --output .\ai\data\audio\processed\speech_alarm_audiosep15.wav `
  --backend audiosep_hive15cat `
  --target "alarm" `
  --aggressiveness 1.4

python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_codecsep15.wav `
  --backend codecsep_dnrv2_15cat `
  --codecsep15-runtime onnx `
  --target "dog barking" `
  --aggressiveness 1.4
```

These are useful for evaluation, not the default desktop or Android product path.

## Model Comparison

```powershell
python -m ai compare run --list-models

python -m ai compare run `
  --input-dir .\ai\data\audio\raw `
  --model auto `
  --max-files 3 `
  --dry-run

python -m ai compare run `
  --model waveformer `
  --model waveformer_onnx_export `
  --dry-run

python -m ai compare run `
  --model audiosep_open_vocab `
  --audiosep-prompt "boat engine" `
  --dry-run

python -m ai compare run `
  --model audiosep_hive_raw `
  --model clapsep_research `
  --dry-run
```

`--dry-run` is handled by the lightweight CLI layer and does not import the
legacy PyTorch comparison runner. Real comparison runs still use the legacy
runner and may need the heavier runtime stack for non-ONNX backends.

Comparison outputs are written under `ai/data/audio/processed` unless
`--output-root` is supplied.

## Evaluation And Report Generation

Use `evaluate` for fair benchmarking and final report generation. It is stricter
than `compare`: each runnable model gets its own worker process, one model load,
the same ordered cases, the same repeat count, and the same resource monitor.

Setup:

```powershell
.\shared\scripts\setup-ai-runtime.ps1 -Profile evaluation
```

Inspect the semantic evaluation model list:

```powershell
python -m ai evaluate list-models
```

Plan without running models:

```powershell
python -m ai evaluate plan `
  --input-dir .\ai\data\audio\raw `
  --suite full `
  --models all `
  --output-root .\ai\data\audio\processed\evaluation_final
```

Smoke one packaged model:

```powershell
python -m ai evaluate run `
  --input-dir .\ai\data\audio\raw `
  --models waveformer_onnx_export `
  --max-cases 1 `
  --repeats 1 `
  --warmup-runs 0 `
  --output-root .\ai\data\audio\processed\evaluation_smoke `
  --report md-html
```

Full final run for the evaluation phase:

```powershell
python -m ai evaluate run `
  --input-dir .\ai\data\audio\raw `
  --suite full `
  --models all `
  --output-root .\ai\data\audio\processed\evaluation_final `
  --repeats 3 `
  --warmup-runs 1 `
  --include-unsupported `
  --save-audio `
  --report md-html
```

Main outputs:

```text
manifest.json
cases.csv
runs.csv
metrics.csv
resources.csv
rankings.csv
model_cards.json
outputs\<model>\<case>\clean.wav
outputs\<model>\<case>\removed.wav
figures\*.png
report.md
report.html
```

Ranking policy:

- Reference-tier cases drive the primary quality score.
- Coverage-tier files are robustness/proxy evidence only.
- Overall score defaults to 60% quality, 25% speed, 15% memory.
- `target_speaker_windows` is listed as available but out of scope because it
  needs speaker-reference cases rather than semantic target cases.

## VB-CABLE WAV Streaming

```powershell
python -m ai stream wav --list-devices

python -m ai stream wav `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --device-name "CABLE Input" `
  --channels 2 `
  --volume 0.9 `
  --start-silence 1.0
```

This only plays the WAV into a playback endpoint. The desktop app should capture
from the paired recording endpoint, usually `CABLE Output`.

The shared PowerShell wrapper calls the same CLI:

```powershell
.\shared\scripts\stream-loopback-wav.ps1 -ListDevices
.\shared\scripts\stream-loopback-wav.ps1 -InputPath .\ai\data\audio\raw\speech_barking.wav
```

## Export Entry Points

```powershell
python -m ai export waveformer-edge --help
python -m ai export target-speaker-windows --help
python -m ai export codecsep-dnrv2-15cat --help
```

Use dedicated export environments for heavyweight exporters. The lightweight
runtime setup is intentionally not the same as the full training/export stack.

## Tests

```powershell
python -m pytest ai\tests\runtime ai\tests\cli -q
```

Opt-in checks:

```powershell
python -m pytest ai\tests -m requires_artifacts --run-artifact-tests
python -m pytest ai\tests -m requires_audio_device --run-audio-device
python -m pytest ai\tests -m manual --run-manual
```
