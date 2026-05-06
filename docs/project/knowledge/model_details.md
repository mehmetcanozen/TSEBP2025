# Model Details

This document explains the model families in the repo and how they relate to
the current product. It intentionally separates active runtime contracts from
historical or research-only model paths.

## Waveformer Edge 100ms

Status: current default.

Waveformer Edge is the selected semantic suppression backend:

```text
model_id: waveformer_edge_100ms
runtime_kind: onnx_streaming_target_extractor
desktop artifact: semantic_hearing_100ms_desktop.onnx
Android artifact: model_fixed.ort
sample_rate: 44100
chunk_samples: 4416
categories: 20
```

The runtime receives a stereo mixture chunk and a 20-dimensional label vector.
It returns a target chunk plus updated streaming state. Product runtimes remove
the predicted unwanted target from the mixture:

```text
clean = mixture - aggressiveness * target_chunk
```

Desktop and Android share the same streaming tensor contract. Desktop uses an
optimized ONNX file; Android uses the ORT-format `model_fixed.ort` package
artifact plus metadata and required-operator config.

## YAMNet

Status: legacy/reference mapping component.

YAMNet is used in older Python flows for semantic detection and category
activation. It maps broad audio events into project categories using YAML/JSON
configuration under `ai/ai_runtime/config`.

Current packaged Waveformer desktop/mobile live paths do not depend on YAMNet
to choose the active category. The user selects categories from the packaged
model manifest.

## AudioSep

Status: quality anchor and research teacher, not current default product
runtime.

The full "naked" AudioSep model is valued because its outputs can sound better
than small fixed-category exports. It is not the deployed edge product in this
repo. The future direction is to use AudioSep as a teacher to train a smaller
category-conditioned student.

## AudioSepHive15Cat

Status: packaged exact-15 alternative.

AudioSepHive15Cat freezes a 15-category deployment surface into an ONNX category
separator. It uses fixed category ids rather than open text prompts at runtime.
The package declares both desktop and Android `onnx_category_separator`
contracts at `32000 Hz`.

Its deployable ONNX and category metadata live under:

```text
ai/models/Exports/AudioSepHive15Cat/audiosep_hive15cat_exact15/shared/
```

This model is useful for comparisons and package/runtime validation. It should
not be described as the current default unless `model_selection.json` changes.

## CodecSep

Status: research/runtime branch plus packaged exact-15 derivative.

Generic CodecSep remains available in Python for query-first experiments and
AudioCaps-native fixed-slot behavior. It can compile prompts and choose
reconstruction policies dynamically.

CodecSepDNRv2_15Cat is different: it is the frozen exact-15 deployment package.
Its exported runtime does not depend on arbitrary text prompts; it uses
category ids/vectors and packaged metadata.

## CodecSepDNRv2_15Cat

Status: packaged exact-15 export/runtime experiment and alternative.

The package declares:

- desktop `onnx_category_separator`
- Android `executorch_category_separator`
- `16000 Hz` sample rate
- 2 second segments with 0.5 second overlap
- exact-15 labels matching the AudioSepHive15Cat product surface

Its generated artifacts live under:

```text
ai/models/Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/
```

The `desktop/` subfolder contains the ONNX artifact, the `android/` subfolder
contains the ExecuTorch `.pte`, `shared/` contains category metadata, and
`source/` keeps the frozen checkpoint plus freeze manifest/spec.

Use it to explain the export/runtime exploration and ExecuTorch path, not the
current default product path.

## TargetSpeakerWindows

Status: desktop target-speaker package.

This package suppresses or isolates a speaker matching a reference clip. It is
not category-based semantic suppression.

The default engine is TSExtract ONNX:

- mixture input: `1 x 80000`
- reference input: `1 x 24000`
- reference length input: `1`
- output: `target`
- required external sidecar: `tsextract_fp32.onnx.data`

ClearVoice is included as an optional offline quality fallback. The desktop UI
should treat ClearVoice as offline-only unless runtime support changes.

## Native UNet / TFLite

Status: superseded historical mobile experiment.

Native UNet was introduced to avoid complex-number export problems in an early
TFLite mobile direction. The current Android app no longer uses that as the
product runtime. Current Android deployment uses generated model bundles with
ONNX Runtime Android and ExecuTorch support.

## Choosing The Right Model Story

- For current desktop/mobile demos: start with Waveformer Edge 100ms.
- For exact-15 package comparisons: use AudioSepHive15Cat and
  CodecSepDNRv2_15Cat.
- For speaker-conditioned suppression: use TargetSpeakerWindows.
- For future quality direction: describe AudioSep teacher to small
  category-conditioned student.
- For historical explanation only: mention Native UNet/TFLite.
