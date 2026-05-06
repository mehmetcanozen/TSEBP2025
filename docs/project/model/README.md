# Model Catalogue

This folder explains every model family and model asset currently present in
the project. Start here when you need to know what a model is for, whether it is
part of the active product path, and which runtime owns it.

## Current Source Of Truth

The product model registry is:

```text
ai/models/model_selection.json
```

Current default:

```text
default_model_id: waveformer_edge_100ms
```

Only models listed in `model_selection.json` are packaged product models. Other
folders under `ai/models` are research sources, vendored upstream projects,
supporting classifiers, prototype exports, or target-speaker tooling.

## Packaged Product Models

| Model id | Folder | Product role | Desktop runtime | Android runtime | Default |
| --- | --- | --- | --- | --- | --- |
| `waveformer_edge_100ms` | `ai/models/Waveformer` | Current semantic suppression model | `onnx_streaming_target_extractor` | `onnx_streaming_target_extractor` | Yes |
| `audiosep_hive15cat` | `ai/models/AudioSepHive15Cat` | Exact-15 AudioSep category separator | `onnx_category_separator` | `onnx_category_separator` | No |
| `codecsep_dnrv2_15cat` | `ai/models/CodecSepDNRv2_15Cat` | Frozen exact-15 CodecSep category separator | `onnx_category_separator` | `executorch_category_separator` | No |
| `target_speaker_windows` | `ai/models/TargetSpeakerWindows` | Windows target-speaker package | `target_speaker_windows_bundle` | Not packaged | No |

Detailed pages:

- [Waveformer Edge 100ms](waveformer_edge_100ms.md)
- [Exact-15 Models](exact_15_models.md)
- [Target Speaker Windows](target_speaker_windows.md)
- [Research And Historical Models](research_and_historical_models.md)

## Supporting And Historical Model Assets

| Folder or component | What it is | Current status |
| --- | --- | --- |
| `ai/models/AudioSep` | Vendored full AudioSep project and checkpoints | Quality anchor and future teacher source; not deployed directly as the default edge runtime. |
| `ai/models/CodecSep` | Generic CodecSep source/run bundle and paper docs | Python research/runtime source for query-first and exact-15 freeze work. |
| `ai/models/ClapSepHive15Cat` | CLAPSep exact-15 prototype manifest/workspace | Historical/prototype exact-15 separator, not selected in the package registry. Generated assets live under `ai/models/Exports/ClapSepHive15Cat/clapsep_hive15cat_prototype`. |
| `ai/models/YAMNet` | YAMNet classifier SavedModel and metadata | Legacy/reference detector for Python flows and semantic mappings. |
| `ai/models/SpeakerSeperator` | Target-speaker toy/project workspace | Source for selected-speaker experiments and Windows export work. |
| `ai/models/Exports` | Generated export artifacts | Canonical root for deployable/generated assets: Waveformer, TargetSpeakerWindows, AudioSepHive15Cat exact-15, CodecSepDNRv2 exact-15, and ClapSepHive15Cat prototype exports. Ignored/generated style assets. |
| DeepFilterNet via `SpeechEnhancer` | Third-party universal speech enhancement path | Optional `--suppress-all` voice cleanup helper, not semantic category suppression. |
| Native UNet/TFLite | Old mobile experiment | Superseded by shared ONNX/ExecuTorch package bundles. |

## How To Read Model Status

- **Default** means selected by `ai/models/model_selection.json`.
- **Packaged** means there is a `model_package.json` with platform contracts.
- **Runtime kind** tells desktop/mobile which native runtime class to use.
- **Research/supporting** means the code or weights are useful, but not the
  current product path until a package manifest selects them.

## Rules For Future Docs

- Use `waveformer_edge_100ms` as the current default until
  `model_selection.json` changes.
- Call AudioSepHive15Cat and CodecSepDNRv2 exact-15 alternatives, not defaults.
- Call Native UNet/TFLite historical unless a new package manifest reintroduces
  it.
- Treat `TargetSpeakerWindows` as a separate speaker-reference workflow, not a
  semantic category model.
