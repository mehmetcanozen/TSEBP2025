# Model artifacts

Large model files are intentionally not committed to Git. A working checkout
needs the portable artifact folder restored at:

```text
C:\SoftwareProjects\TSEBP2025\ai\models\Exports
```

Download the current portable `Exports` zip from:

```text
https://drive.google.com/file/d/1mQq1cagJf5lNTkQqo85s9qRCW1a-hN5c/view?usp=sharing
```

Open the link in a browser, download the zip, and keep it outside the Git
checkout until extraction. Do not commit the zip or the extracted `Exports`
folder.

Small manifests stay in Git and point to the restored artifacts. The important
manifests are:

```text
ai\models\model_selection.json
ai\models\Waveformer\model_package.json
ai\models\TargetSpeakerWindows\model_package.json
ai\models\AudioSepHive15Cat\model_package.json
ai\models\CodecSepDNRv2_15Cat\model_package.json
```

## Restore the artifact bundle

If the downloaded zip's top-level folder is `Exports`, extract it into
`ai\models`:

```powershell
cd C:\SoftwareProjects\TSEBP2025

Expand-Archive `
  -LiteralPath C:\path\to\Exports.zip `
  -DestinationPath .\ai\models `
  -Force
```

After extraction, this path must exist:

```text
C:\SoftwareProjects\TSEBP2025\ai\models\Exports
```

Avoid this nested shape:

```text
C:\SoftwareProjects\TSEBP2025\ai\models\Exports\Exports
```

If you get `Exports\Exports`, move the inner contents up one level or delete
the outer folder and extract again.

## Expected folder shape

```text
ai\models\Exports\
|-- Waveformer\
|   `-- waveformer_edge_100ms\
|       |-- source\
|       |-- desktop\
|       `-- android\
|-- TargetSpeakerWindows\
|   `-- target_speaker_windows_desktop\
|       |-- source\
|       `-- desktop\
|-- AudioSepHive15Cat\
|   `-- audiosep_hive15cat_exact15\
|-- CodecSepDNRv2_15Cat\
|   `-- codecsep_dnrv2_15cat_exact15\
`-- ClapSepHive15Cat\
    `-- clapsep_hive15cat_prototype\
```

## Verify required product artifacts

Preferred check:

```powershell
cd C:\SoftwareProjects\TSEBP2025
python -m ai artifacts check --required-only
```

For CI-style failure behavior, use:

```powershell
python -m ai artifacts check --strict
```

Manual PowerShell check:

```powershell
cd C:\SoftwareProjects\TSEBP2025

$required = @(
  ".\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx",
  ".\ai\models\Exports\Waveformer\waveformer_edge_100ms\desktop\semantic_hearing_100ms_desktop.onnx.json",
  ".\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort",
  ".\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\model_fixed.ort.json",
  ".\ai\models\Exports\Waveformer\waveformer_edge_100ms\android\required_operators.config",
  ".\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\windows_bundle_manifest.json",
  ".\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx",
  ".\ai\models\Exports\TargetSpeakerWindows\target_speaker_windows_desktop\desktop\tsextract_onnx\tsextract_fp32.onnx.data"
)

foreach ($path in $required) {
  if (!(Test-Path -LiteralPath $path)) {
    throw "Missing model artifact: $path"
  }
}

"Model artifacts are present."
```

The CLI check is the source of truth for new workflows because it uses the same
central artifact helpers as the AI runtime commands.

## How the apps consume the bundle

Desktop uses Tauri resources to copy or bundle the restored files during normal
development and build flows. You do not manually copy model files into
`desktop/src-tauri/target`.

Android uses the Gradle `prepareBundledSuppressionModel` task to read the
shared manifests and place the active Android model into generated app assets.
The shared backend is not involved in model selection, model delivery, or audio
suppression.

The AI CLI uses the same restored artifact root for local tests:

```powershell
python -m ai models list
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --target dog `
  --backend waveformer
```

## Rules

- Keep the folder name as `Exports`.
- Do not commit `ai/models/Exports`.
- Do not continue with partial model files.
- Treat `WFExports` and lowercase `exports` as stale historical paths.
- For the Android app, the current default artifact is
  `Waveformer/waveformer_edge_100ms/android/model_fixed.ort`.
- Use `python -m ai artifacts check --required-only` after restoring or
  changing the bundle.
