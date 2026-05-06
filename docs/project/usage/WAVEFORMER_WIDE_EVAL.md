# Waveformer Wide Demo and Evaluation Dataset

Current runtime note: this runbook targets the active
`waveformer_edge_100ms` product surface. The suppression spot-check commands use
the packaged Waveformer ONNX runtime via
`ai.ai_runtime.separation.waveformer_onnx_stream`, with the generated desktop artifact
`ai/models/Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx`.
It is not a Native UNet/TFLite or exact-15 AudioSep/CodecSep runbook.

This runbook explains the reproducible Waveformer wide demo dataset pipeline:
download public audio datasets, normalize source clips, create curated real-life
mixtures, validate the generated WAVs, and run Waveformer suppression spot
checks.

The implementation lives at:

```text
ai/scripts/prepare_waveformer_wide_eval.py
```

The generated local output paths are:

```text
ai/data/audio/waveformertestdownloads/  # cached archives and extracted datasets
ai/data/audio/waveformertestsources/    # normalized 5 second source WAVs
ai/data/audio/waveformertestmixed/      # final curated mix WAVs and manifests
```

These folders are ignored by Git because the downloaded datasets are large.

## What It Builds

The script targets the current shipped Waveformer 20-label product surface, not
the older Python-only 41-label research target list. It creates:

- 74 normalized source clips
- 37 source classes, 2 clips per class
- 50 curated demo mixtures
- 25 two-sound mixes, 15 three-sound mixes, and 10 four-sound mixes
- `source_manifest.csv`, `mix_manifest.csv`, and `dataset_sources.json`

The mixes are designed around product stories where suppressing one sound is
clearly useful, for example:

```text
dog + engine -> suppress dog
computer_typing + speech -> suppress computer_typing
siren + speech -> suppress siren
toilet_flush + speech -> suppress toilet_flush
birds_chirping + speech + wind -> suppress birds_chirping
```

## Data Sources

The script downloads these public datasets automatically:

```text
ESC-50
https://github.com/karolpiczak/ESC-50

FSDKaggle2018
https://zenodo.org/records/2552860

LibriSpeech dev-clean
https://www.openslr.org/12
```

Use the generated manifests for attribution and license review before sharing
any audio outside local demos. ESC-50 and FSDKaggle2018 include Creative Commons
material; FSDKaggle2018 uses per-clip Freesound licenses. LibriSpeech dev-clean
is used only for clean speech examples.

## Requirements

From the repo root, make sure Python, FFmpeg, and ffprobe are available:

```powershell
cd C:\SoftwareProjects\TSEBP2025

python --version
ffmpeg -version
ffprobe -version
```

The full download cache is large. The validated local run used about:

```text
waveformertestdownloads: 12.31 GB
waveformertestsources:   0.03 GB
waveformertestmixed:     0.02 GB
```

## Dry Run

Run a dry run first. It validates the static recipe, checks FFmpeg and ffprobe,
and prints the planned datasets and mix recipe counts without downloading or
writing audio.

```powershell
cd C:\SoftwareProjects\TSEBP2025

python .\ai\scripts\prepare_waveformer_wide_eval.py `
  --download-root .\ai\data\audio\waveformertestdownloads `
  --source-root .\ai\data\audio\waveformertestsources `
  --mix-root .\ai\data\audio\waveformertestmixed `
  --clips-per-source 2 `
  --mix-count 50 `
  --seed 20260502 `
  --dry-run
```

Expected dry-run shape:

```text
recipes: 50 ({2: 25, 3: 15, 4: 10})
classes: 37
```

## Generate The Dataset

Run this from the repo root when you are ready to download and generate the
audio. This can take a while because it downloads and extracts the public
datasets.

```powershell
cd C:\SoftwareProjects\TSEBP2025

python .\ai\scripts\prepare_waveformer_wide_eval.py `
  --download-root .\ai\data\audio\waveformertestdownloads `
  --source-root .\ai\data\audio\waveformertestsources `
  --mix-root .\ai\data\audio\waveformertestmixed `
  --clips-per-source 2 `
  --mix-count 50 `
  --seed 20260502
```

If the archives are already downloaded and extracted, reuse them with:

```powershell
python .\ai\scripts\prepare_waveformer_wide_eval.py `
  --download-root .\ai\data\audio\waveformertestdownloads `
  --source-root .\ai\data\audio\waveformertestsources `
  --mix-root .\ai\data\audio\waveformertestmixed `
  --clips-per-source 2 `
  --mix-count 50 `
  --seed 20260502 `
  --skip-downloads
```

## How The Script Works

The script performs these steps:

1. Downloads ESC-50, FSDKaggle2018 audio/meta/doc, and LibriSpeech dev-clean
   into `waveformertestdownloads/archives`.
2. Extracts the archives into `waveformertestdownloads/extracted`.
3. Collects source candidates using static mappings from product-friendly source
   class IDs to dataset labels.
4. Selects 2 clips per required source class using the fixed seed.
5. Normalizes every selected source clip with FFmpeg to:

```text
mono WAV
44100 Hz
s16
about 5 seconds
loudnorm target I=-18, TP=-1.5, LRA=11
short fade in/out
```

6. Creates 50 deterministic mix recipes with FFmpeg using per-source volume and
   delay offsets.
7. Validates rendered WAV files with ffprobe unless `--no-validate` is passed.
8. Writes manifests.

Source conversion uses this shape internally:

```powershell
ffmpeg -y -i INPUT `
  -vn -ac 1 -ar 44100 `
  -af "apad=pad_dur=5,atrim=0:5,loudnorm=I=-18:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.03,afade=t=out:st=4.95:d=0.05" `
  -sample_fmt s16 OUTPUT.wav
```

Mixing uses this shape internally:

```powershell
ffmpeg -y -i A.wav -i B.wav `
  -filter_complex "[0:a]volume=1.00[a0];[1:a]adelay=450:all=1,volume=0.78[a1];[a0][a1]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,loudnorm=I=-18:TP=-1.5:LRA=11,atrim=0:5,asetpts=N/SR/TB[out]" `
  -map "[out]" -ac 1 -ar 44100 -sample_fmt s16 MIX.wav
```

## Important Output Files

After generation, inspect:

```text
ai/data/audio/waveformertestsources/source_manifest.csv
ai/data/audio/waveformertestmixed/mix_manifest.csv
ai/data/audio/waveformertestmixed/dataset_sources.json
```

`source_manifest.csv` records each normalized source clip:

```text
class_id
clip_index
normalized_path
dataset
original_label
original_path
source_id
split
license
citation_source
```

`mix_manifest.csv` records each final mix:

```text
mix_index
mix_name
target
output_path
sound_count
source_classes
source_files
story
suppression_hint
```

Use `target` as the Waveformer category to suppress for that mix.

## Validate A Generated Run

Use this command to validate manifests, expected row counts, file existence, and
target consistency:

```powershell
cd C:\SoftwareProjects\TSEBP2025

$sourceManifest = Import-Csv -LiteralPath 'ai\data\audio\waveformertestsources\source_manifest.csv'
$mixManifest = Import-Csv -LiteralPath 'ai\data\audio\waveformertestmixed\mix_manifest.csv'
$knownTargets = @(
  'alarm_clock','baby_cry','birds_chirping','cat','car_horn',
  'cock_a_doodle_doo','cricket','computer_typing','dog',
  'glass_breaking','gunshot','music','ocean','door_knock',
  'siren','speech','thunderstorm','toilet_flush'
)

$missingSources = @($sourceManifest | Where-Object { -not (Test-Path -LiteralPath $_.normalized_path) })
$missingMixes = @($mixManifest | Where-Object { -not (Test-Path -LiteralPath $_.output_path) })
$badTargets = @($mixManifest | Where-Object { $knownTargets -notcontains $_.target })
$targetNotInSources = @($mixManifest | Where-Object { ($_.source_classes -split '\+') -notcontains $_.target })

[pscustomobject]@{
  SourceRows = $sourceManifest.Count
  SourceClasses = (($sourceManifest | Select-Object -ExpandProperty class_id -Unique).Count)
  MixRows = $mixManifest.Count
  MissingNormalizedSources = $missingSources.Count
  MissingMixes = $missingMixes.Count
  BadTargets = $badTargets.Count
  TargetNotInSources = $targetNotInSources.Count
} | Format-List

$sourceManifest | Group-Object class_id | Sort-Object Name | Select-Object Name,Count | Format-Table -AutoSize
$mixManifest | Group-Object sound_count | Sort-Object Name | Select-Object Name,Count | Format-Table -AutoSize
```

Expected result for the standard run:

```text
SourceRows: 74
SourceClasses: 37
MixRows: 50
MissingNormalizedSources: 0
MissingMixes: 0
BadTargets: 0
TargetNotInSources: 0

Every source class count: 2
Sound count split: 2 -> 25, 3 -> 15, 4 -> 10
```

Validate the generated audio format:

```powershell
cd C:\SoftwareProjects\TSEBP2025

$files = @()
$files += Get-ChildItem -LiteralPath 'ai\data\audio\waveformertestsources' -File -Filter *.wav
$files += Get-ChildItem -LiteralPath 'ai\data\audio\waveformertestmixed' -File -Filter *.wav
$bad = New-Object System.Collections.Generic.List[object]
$durations = New-Object System.Collections.Generic.List[double]

foreach ($file in $files) {
  $json = & ffprobe -v error -select_streams a:0 `
    -show_entries stream=sample_rate,channels,sample_fmt `
    -show_entries format=duration -of json -- $file.FullName
  $probe = $json | ConvertFrom-Json
  $stream = @($probe.streams)[0]
  $duration = [double]$probe.format.duration
  $durations.Add($duration) | Out-Null
  if ([int]$stream.sample_rate -ne 44100 -or [int]$stream.channels -ne 1 -or [string]$stream.sample_fmt -ne 's16' -or $duration -lt 4.90 -or $duration -gt 5.10) {
    $bad.Add([pscustomobject]@{
      File=$file.FullName
      SampleRate=$stream.sample_rate
      Channels=$stream.channels
      SampleFmt=$stream.sample_fmt
      Duration=[math]::Round($duration,3)
    }) | Out-Null
  }
}

[pscustomobject]@{
  CheckedFiles = $files.Count
  BadFiles = $bad.Count
  MinDuration = [math]::Round((($durations | Measure-Object -Minimum).Minimum), 3)
  MaxDuration = [math]::Round((($durations | Measure-Object -Maximum).Maximum), 3)
  AvgDuration = [math]::Round((($durations | Measure-Object -Average).Average), 3)
} | Format-List

if ($bad.Count -gt 0) { $bad | Select-Object -First 20 | Format-Table -AutoSize }
```

The validated local run checked 124 WAVs and found 0 bad files.

## Run Waveformer Suppression Spot Checks

The dataset only creates mixtures. To prove that the mixes are consumable by the
current Waveformer ONNX runtime, suppress a subset or all mixes using the target
listed in `mix_manifest.csv`.

### Suppress The First 10 Mixes

```powershell
cd C:\SoftwareProjects\TSEBP2025

@'
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.ai_runtime.separation.waveformer_onnx_stream import suppress_file

mix_manifest = PROJECT_ROOT / "ai" / "data" / "audio" / "waveformertestmixed" / "mix_manifest.csv"
out_dir = PROJECT_ROOT / "ai" / "data" / "audio" / "processed" / ("waveformer_wide_spotcheck_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
out_dir.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader(mix_manifest.open("r", encoding="utf-8", newline="")))
summary = []

for row in rows[:10]:
    mix_index = int(row["mix_index"])
    target = row["target"]
    input_path = Path(row["output_path"])
    output_path = out_dir / f"{mix_index:03d}_{row['mix_name']}__suppress_{target}.wav"
    stats = suppress_file(
        input_path=input_path,
        output_path=output_path,
        categories=[target],
        aggressiveness=1.1,
        mode="offline",
    )
    stats.pop("noise_audio", None)
    item = {
        "mix_index": mix_index,
        "mix_name": row["mix_name"],
        "target": target,
        "input": str(input_path),
        "output": str(output_path),
        "duration_seconds": round(float(stats.get("duration_seconds", 0.0)), 3),
        "real_time_factor": round(float(stats.get("real_time_factor", 0.0)), 4),
        "rms_reduction_db": round(float(stats.get("rms_reduction_db", 0.0)), 3),
    }
    summary.append(item)
    print(json.dumps(item))

summary_path = out_dir / "spotcheck_summary.json"
summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(f"SUMMARY={summary_path}")
'@ | python -B -
```

### Add Suppression Outputs For Mixes 11-50 To An Existing Spotcheck Folder

Replace `EXISTING_SPOTCHECK_DIR` with the folder you already created, for
example:

```text
C:\SoftwareProjects\TSEBP2025\ai\data\audio\processed\waveformer_wide_spotcheck_20260502_024531
```

Then run:

```powershell
cd C:\SoftwareProjects\TSEBP2025

@'
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.ai_runtime.separation.waveformer_onnx_stream import suppress_file

out_dir = Path(r"EXISTING_SPOTCHECK_DIR")
mix_manifest = PROJECT_ROOT / "ai" / "data" / "audio" / "waveformertestmixed" / "mix_manifest.csv"
rows = list(csv.DictReader(mix_manifest.open("r", encoding="utf-8", newline="")))
summary = []

for row in rows:
    mix_index = int(row["mix_index"])
    if mix_index <= 10:
        continue
    target = row["target"]
    input_path = Path(row["output_path"])
    output_path = out_dir / f"{mix_index:03d}_{row['mix_name']}__suppress_{target}.wav"
    if output_path.exists():
        print(f"skip existing: {output_path.name}")
        continue
    stats = suppress_file(
        input_path=input_path,
        output_path=output_path,
        categories=[target],
        aggressiveness=1.1,
        mode="offline",
    )
    stats.pop("noise_audio", None)
    item = {
        "mix_index": mix_index,
        "mix_name": row["mix_name"],
        "target": target,
        "input": str(input_path),
        "output": str(output_path),
        "duration_seconds": round(float(stats.get("duration_seconds", 0.0)), 3),
        "real_time_factor": round(float(stats.get("real_time_factor", 0.0)), 4),
        "rms_reduction_db": round(float(stats.get("rms_reduction_db", 0.0)), 3),
    }
    summary.append(item)
    print(json.dumps(item))

summary_path = out_dir / "spotcheck_more_summary.json"
summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {len(summary)} new suppressions -> {summary_path}")
'@ | python -B -
```

### Suppress All 50 Mixes Into A Fresh Folder

```powershell
cd C:\SoftwareProjects\TSEBP2025

@'
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.ai_runtime.separation.waveformer_onnx_stream import suppress_file

mix_manifest = PROJECT_ROOT / "ai" / "data" / "audio" / "waveformertestmixed" / "mix_manifest.csv"
out_dir = PROJECT_ROOT / "ai" / "data" / "audio" / "processed" / ("waveformer_wide_all_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
out_dir.mkdir(parents=True, exist_ok=True)
rows = list(csv.DictReader(mix_manifest.open("r", encoding="utf-8", newline="")))
summary = []

for row in rows:
    mix_index = int(row["mix_index"])
    target = row["target"]
    input_path = Path(row["output_path"])
    output_path = out_dir / f"{mix_index:03d}_{row['mix_name']}__suppress_{target}.wav"
    stats = suppress_file(
        input_path=input_path,
        output_path=output_path,
        categories=[target],
        aggressiveness=1.1,
        mode="offline",
    )
    stats.pop("noise_audio", None)
    item = {
        "mix_index": mix_index,
        "mix_name": row["mix_name"],
        "target": target,
        "input": str(input_path),
        "output": str(output_path),
        "duration_seconds": round(float(stats.get("duration_seconds", 0.0)), 3),
        "real_time_factor": round(float(stats.get("real_time_factor", 0.0)), 4),
        "rms_reduction_db": round(float(stats.get("rms_reduction_db", 0.0)), 3),
    }
    summary.append(item)
    print(json.dumps(item))

summary_path = out_dir / "waveformer_wide_all_summary.json"
summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {len(summary)} suppressions -> {summary_path}")
'@ | python -B -
```

## Listening QA

The validation commands prove the dataset shape and runtime compatibility, but
they do not replace listening. For demo selection, listen to:

1. Original mix from `waveformertestmixed`.
2. Suppressed output from `ai/data/audio/processed/...`.
3. The manifest story and target.

Good demo candidates should have:

- a target sound that is audible before suppression
- useful non-target context that remains after suppression
- a clear story, such as car diagnosis, meeting cleanup, baby monitor, street
  speech, podcast cleanup, or travel recording

If one mix has low audible change, keep it for broad testing but choose a
stronger one for presentation.

## Known Boundaries

- This is a local demo/evaluation dataset pipeline, not a training pipeline.
- Generated folders are intentionally ignored by Git.
- It tests the shipped Waveformer 20-label surface.
- `hammer` and `singing` are excluded from required success-demo mixes because
  the chosen reproducible sources do not provide clean exact coverage for those
  labels.
- The dataset generation validates file format and references. Human listening
  is still required to choose the best presentation examples.
