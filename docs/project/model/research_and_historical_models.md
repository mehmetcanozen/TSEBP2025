# Research, Support, And Historical Models

This page covers model folders and components that matter to the project but are
not the current packaged default.

## Full AudioSep

Folder:

```text
ai/models/AudioSep
```

Role:

- Vendored AudioSep project.
- Contains `audiosep_base_4M_steps.ckpt`.
- Contains Hive checkpoint/config assets.
- Provides the high-quality "naked AudioSep" reference that motivated future
  student-model planning.

Current status:

```text
Quality anchor and possible teacher source, not the deployed edge default.
```

The strategic future direction is:

```text
AudioSep teacher -> cached teacher outputs -> small category-conditioned student -> ONNX/edge export
```

That future student would predict the unwanted source for fixed categories, then
the app would subtract or mask that estimate.

## Generic CodecSep

Folder:

```text
ai/models/CodecSep
```

Role:

- Source/run bundle for CodecSep experiments.
- Contains paper docs and a DNR USS model bundle run.
- Feeds Python query-first runtime behavior.
- Feeds the exact-15 freeze/export workflow that produced
  `CodecSepDNRv2_15Cat`.

Current status:

```text
Research/runtime source and export source, not a direct product package.
```

Packaged product deployment should use `codecsep_dnrv2_15cat` rather than
generic CodecSep prompt mode.

## YAMNet

Folder:

```text
ai/models/YAMNet
```

Role:

- Audio event classifier.
- Provides class metadata and TensorFlow SavedModel assets.
- Used by legacy/reference Python detection and semantic mapping flows.

Current status:

```text
Supporting detector for Python/reference flows, not required by the packaged Waveformer desktop/mobile ONNX path.
```

The current product UI selects package categories directly. YAMNet is still
important for understanding older profile/detection code and some Python
commands.

## ClapSepHive15Cat

Folder:

```text
ai/models/ClapSepHive15Cat
```

Role:

- CLAPSep exact-15 prototype.
- Keeps the prototype model identity/workspace. Generated ONNX/PT assets and
  query/category embeddings are centralized under
  `ai/models/Exports/ClapSepHive15Cat/clapsep_hive15cat_prototype/`.

Current status:

```text
Historical/prototype exact-15 model. Not selected by model_selection.json.
```

## SpeakerSeperator

Folder:

```text
ai/models/SpeakerSeperator
```

Role:

- Target-speaker experimentation workspace.
- Contains sample audio, speaker profiles, ClearVoice/TSExtract style tooling,
  and Windows export notes.

Current status:

```text
Research/toy workspace that informed TargetSpeakerWindows packaging.
```

The packaged product version is `target_speaker_windows`.

## DeepFilterNet / SpeechEnhancer

Code:

```text
ai/ai_runtime/enhancement/speech_enhancer.py
```

Role:

- Optional universal speech enhancement path.
- Invoked by Python `--suppress-all`.
- Useful when the user wants generic voice cleanup rather than semantic category
  removal.

Current status:

```text
Optional third-party enhancement helper, not a semantic model package.
```

## Native UNet / TFLite

Role:

- Historical mobile export experiment.
- Intended to avoid complex-number conversion problems in early TFLite work.

Current status:

```text
Superseded.
```

The current Android path uses generated package bundles with ONNX Runtime
Android and ExecuTorch support. Do not describe Native UNet/TFLite as the
current mobile product runtime.

## Generated Exports

Folder:

```text
ai/models/Exports
```

Role:

- Generated model exports and runtime bundles.
- Canonical generated-artifact root for Waveformer, TargetSpeakerWindows,
  AudioSepHive15Cat exact-15, CodecSepDNRv2 exact-15, and the ClapSepHive15Cat
  prototype.

Current status:

```text
Generated artifact area. Verify local existence before relying on it in demos or fresh clones.
```
