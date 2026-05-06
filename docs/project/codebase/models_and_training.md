# Models, Training, Exports, And Validation

This project contains multiple model lines. The important documentation rule is:
the active product default comes from `ai/models/model_selection.json`, while
training and export scripts describe possible or historical paths.

## Active Model Taxonomy

| Model id | Role | Runtime contract | Current status |
| --- | --- | --- | --- |
| `waveformer_edge_100ms` | Default semantic suppressor | Desktop and Android `onnx_streaming_target_extractor` | Current default product path. |
| `audiosep_hive15cat` | Exact-15 category separator | Desktop and Android `onnx_category_separator` | Packaged alternative/comparison path. |
| `codecsep_dnrv2_15cat` | Frozen exact-15 CodecSep separator | Desktop `onnx_category_separator`, Android `executorch_category_separator` | Packaged export/runtime experiment and alternative. |
| `target_speaker_windows` | Reference-speaker suppression | Desktop `target_speaker_windows_bundle` | Windows target-speaker package; offline-first. |
| Native UNet/TFLite | Early mobile experiment | Historical `.tflite` asset idea | Superseded. |

## Waveformer Edge 100ms

`waveformer_edge_100ms` is the current default. Its package declares a direct
residual strategy:

```text
clean = mixture - aggressiveness * target_chunk
```

The ONNX contract uses stereo chunks of `4416` samples at `44100 Hz` plus three
state tensors:

- `enc_buf`
- `dec_buf`
- `out_buf`

The validation summary in the package reports an ONNX CPU contract audit and
known reference cases for dog and computer typing suppression. The relevant
audit path is `ai/scripts/audit_waveformer_onnx.py`; the reusable runtime
adapter is `ai/ai_runtime/separation/waveformer_onnx_stream.py`.

The product category surface is 20 labels:

```text
alarm_clock, baby_cry, birds_chirping, cat, car_horn,
cock_a_doodle_doo, cricket, computer_typing, dog, glass_breaking,
gunshot, hammer, music, ocean, door_knock, singing, siren,
speech, thunderstorm, toilet_flush
```

Do not confuse these with the older Python/YAMNet category aliases or with the
exact-15 AudioSep/CodecSep labels.

## AudioSepHive15Cat

`audiosep_hive15cat` packages an exact-15 ONNX separator with a fixed category
index input. It is not the current default, but it remains important because it
represents a simpler fixed-category deployment contract and a quality comparison
point.

The package manifest stays in `ai/models/AudioSepHive15Cat/model_package.json`.
The generated ONNX, category YAML/TXT, and embedding source asset live under:

```text
ai/models/Exports/AudioSepHive15Cat/audiosep_hive15cat_exact15/
```

Its categories use human-readable labels such as `dog barking`, `keyboard
typing`, `phone ringing`, `door knocking`, `alarm`, and `background noise`.
Runtime code treats it as `onnx_category_separator` with longer segment windows
and overlap, followed by suppression reconstruction.

## CodecSepDNRv2_15Cat

`codecsep_dnrv2_15cat` freezes a prompt-conditioned CodecSep model into a
15-category deployment form. Text prompts are not part of the exported runtime
contract; the packaged form uses category ids/vectors.

The export script `ai/export/freeze_codecsep_dnrv2_15cat.py` builds:

- frozen checkpoint
- ONNX artifact and sidecar
- ExecuTorch `.pte` artifact and sidecar
- freeze manifest and category metadata

Those generated files are centralized under:

```text
ai/models/Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/
```

The model package folder `ai/models/CodecSepDNRv2_15Cat` should contain the
manifest, not the deployable ONNX/PTE/PT payloads.

Desktop currently describes the ONNX path. Android describes the ExecuTorch
path. This model is useful for export/runtime demonstrations and comparison,
not as the selected product default unless `model_selection.json` is changed.

## Generic CodecSep Runtime

The Python `codecsep` backend still exists separately from the frozen exact-15
package. It supports query-first behavior, AudioCaps-native fixed-slot plans,
compatibility mappings, prompt overrides, negative prompts, preserve prompts,
and several reconstruction policies.

This path is valuable for research and experiments, but product desktop/mobile
packaging should prefer explicit package manifests over ad hoc prompt runtime
behavior.

## TargetSpeakerWindows

`target_speaker_windows` is a separate Windows package for suppressing or
isolating a speaker that matches a reference clip.

The default engine is TSExtract ONNX:

- sample rate: `8000`
- mixture window: `80000` samples
- reference window: `24000` samples
- external data sidecar: `tsextract_fp32.onnx.data`

ClearVoice is also packaged as an offline quality fallback when its native
runtime is available. It should not be presented as the default live engine.

## Training And Export Tooling

The AI workspace now has one supported CLI front door:

```powershell
python -m ai --help
tsebp-ai --help
python -m ai models list
python -m ai artifacts check --required-only
python -m ai suppress file --help
```

The CLI is implemented under `ai/cli/` and routes through shared runtime
contracts in `ai/ai_runtime/contracts.py`, backend discovery in
`ai/ai_runtime/registry.py`, and artifact diagnostics in
`ai/ai_runtime/artifacts.py`. Old script entrypoints remain runnable for
compatibility, but new docs and workflows should prefer `python -m ai` or
`tsebp-ai`.

Important script groups:

- `ai/cli/commands/*`: Typer command groups for suppression, models,
  artifacts, comparison, streaming, exports, and diagnostics.
- `ai/export/export_onnx.py` and `ai/export/export_tflite.py`: older Waveformer
  export utilities; TFLite is historical for product mobile.
- `ai/export/export_waveformer_edge.py`: current Waveformer edge packager. It
  takes the trusted 100 ms source ONNX, writes canonical source metadata,
  produces the desktop optimized ONNX and Android ORT artifacts under
  `ai/models/Exports`, and can update `model_package.json`.
- `ai/scripts/audit_waveformer_onnx.py`: current Waveformer ONNX contract audit.
- `ai/scripts/run_android_waveformer_audition.py`: audition the generated
  Android Waveformer bundle from Python.
- `ai/scripts/prepare_waveformer_wide_eval.py`: build reproducible demo/eval
  mixtures for the Waveformer 20-label surface.
- `ai/scripts/run_model_comparison.py`: compare available model runtimes for
  final-pitch style evidence. New workflows should call
  `python -m ai compare run`.
- `ai/export/freeze_codecsep_dnrv2_15cat.py`: freeze/export exact-15 CodecSep
  into the canonical `ai/models/Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/`
  layout.
- `ai/export/export_codecsep_dnrv2_15cat_pte_only.py`: rebuild only the
  CodecSepDNRv2 exact-15 ExecuTorch artifact from the canonical frozen source
  checkpoint under `Exports`.
- `ai/export/export_target_speaker_windows.py`: export/package TSExtract ONNX
  and ClearVoice runtime assets for Windows. The canonical desktop output root
  is `ai/models/Exports/TargetSpeakerWindows/target_speaker_windows_desktop/`;
  `ai/models/SpeakerSeperator` stays the source/toy workspace.
- `ai/scripts/setup/*`: install/download setup helpers for model dependencies.

Primary CLI equivalents:

```powershell
python -m ai suppress file `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --target dog `
  --backend waveformer

python -m ai suppress target-speaker --help
python -m ai compare run --list-models
python -m ai stream wav --list-devices
python -m ai export waveformer-edge --help
python -m ai export target-speaker-windows --help
python -m ai diagnostics env
```

Generated datasets, downloaded corpora, and heavyweight model outputs are often
ignored by Git. `ai/models/Exports` is one of those generated roots. Check local
file existence, and restore the portable `Exports` folder when needed, before
assuming a fresh clone can run the same demo.

## Validation Caveats

What is validated:

- Current Waveformer package declares a CPU ONNX contract audit.
- Android generated bundle manifest matches the active Waveformer package when
  Gradle has prepared assets.
- Desktop config resolves model packages and the ONNX Runtime DLL.
- Runtime tests cover many parser, mapping, target-speaker, Waveformer ONNX,
  mobile package, and exact-15 behaviors.

What is not proven by the docs alone:

- Full perceptual quality across all real-world sounds.
- That ignored model artifacts exist on another machine.
- That VB-CABLE or Android native dev-client setup is correct on a fresh
  environment.
- Historical TFLite/Native UNet behavior as a product path; it is specifically
  documented as superseded, not current.

## Future Model Direction

The strongest future direction for better edge quality is an AudioSep-like
teacher/student path: use high-quality AudioSep outputs as teacher targets, then
train a smaller category-conditioned student that predicts the unwanted source
for fixed product categories and exports cleanly to ONNX or another edge
runtime. That direction is planning guidance, not current validated product
state in this repo.
