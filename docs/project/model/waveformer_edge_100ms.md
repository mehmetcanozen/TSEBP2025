# Waveformer Edge 100ms

## Status

Current default semantic suppression model.

Package:

```text
ai/models/Waveformer/model_package.json
```

Canonical source copy, when generated:

```text
ai/models/Exports/Waveformer/waveformer_edge_100ms/source/semantic_hearing_100ms_source.onnx
ai/models/Exports/Waveformer/waveformer_edge_100ms/source/semantic_hearing_100ms_source.onnx.json
```

Desktop artifact:

```text
ai/models/Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx
```

Sidecar metadata:

```text
ai/models/Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx.json
```

Android artifact:

```text
ai/models/Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort
ai/models/Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort.json
ai/models/Exports/Waveformer/waveformer_edge_100ms/android/required_operators.config
```

## Runtime Contract

| Field | Value |
| --- | --- |
| Model id | `waveformer_edge_100ms` |
| Family | `waveformer` |
| Package version | `waveformer_edge_100ms_exports_20260505` |
| Suppression strategy | `direct_residual` |
| Desktop runtime | `onnx_streaming_target_extractor` |
| Android runtime | `onnx_streaming_target_extractor` |
| Desktop provider | ONNX Runtime CPU |
| Android provider | ONNX Runtime Android CPU |
| Android audio path | Oboe/AAudio first, Kotlin `AudioRecord`/`AudioTrack` fallback |
| Sample rate | `44100` |
| Chunk size | `4416` samples, about `100 ms` |
| Input channels | `2` |
| Category count | `20` |

The runtime predicts the unwanted semantic target and subtracts it:

```text
clean = mixture - aggressiveness * target_chunk
```

## ONNX Inputs And Outputs

Inputs:

- `mixture`: `[1, 2, 4416]`
- `label_vector`: `[1, 20]`
- `enc_buf`: `[1, 256, 2046]`
- `dec_buf`: `[1, 2, 13, 256]`
- `out_buf`: `[1, 256, 4]`

Outputs:

- `target_chunk`
- `enc_buf_out`
- `dec_buf_out`
- `out_buf_out`

The state outputs become the next chunk's state inputs.

## Category Surface

```text
alarm_clock
baby_cry
birds_chirping
cat
car_horn
cock_a_doodle_doo
cricket
computer_typing
dog
glass_breaking
gunshot
hammer
music
ocean
door_knock
singing
siren
speech
thunderstorm
toilet_flush
```

For barking demos, use `dog`. Do not use `barking` as a Waveformer category.

## Product Usage

Waveformer Edge is the model used by:

- desktop semantic live suppression
- desktop Debug WAV live testing
- desktop packaged offline semantic jobs
- Android generated bundled model
- Android on-device live suppression through native `SuppressionEngine`
- Waveformer wide demo/eval spot checks

The desktop and Android apps both read this model through package manifests
rather than through old hard-coded model paths.

On Android, Waveformer inference stays on device. The default live path uses
the ORT-format artifact with ONNX Runtime Android CPU, Oboe/AAudio for live
audio IO when available, about 300 ms lookahead, no default post-filter, and no
default quantization. The mobile backend is not part of model delivery or
inference.

## Validation Notes

The package validation summary reports
`onnx_contract_validated_cpu_and_android_ort_packaged` after the export
packager has run. The audit script is:

```text
ai/scripts/audit_waveformer_onnx.py
```

Known reference cases in the package include:

- `speech_barking_to_speech` targeting `dog`
- `speech_keyboard_to_speech` targeting `computer_typing`

These are contract and spot-check facts, not a full scientific quality claim
for every category.

## Regeneration Note

`ai/models/Exports` is generated and ignored by Git. If desktop or Android
artifact paths are missing, rerun `ai.export.export_waveformer_edge`; it uses
the canonical `Exports/source` copy when present. If that source copy is also
absent, restore the trusted 100 ms ONNX from artifact storage or a known-good
generated Android build cache before generating platform artifacts.

## Common Confusions

- This model is not the old Native UNet/TFLite mobile model.
- This model is not AudioSepHive15Cat.
- Its 20 labels differ from the exact-15 labels used by AudioSepHive15Cat and
  CodecSepDNRv2.
- Python legacy Waveformer/YAMNet flows are useful for reference, but the
  product desktop/mobile path uses the packaged ONNX streaming target
  extractor.
