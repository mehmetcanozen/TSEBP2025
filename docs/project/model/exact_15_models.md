# Exact-15 Models

This page covers the fixed 15-category model packages:

- `audiosep_hive15cat`
- `codecsep_dnrv2_15cat`
- `ClapSepHive15Cat` prototype assets

They are important alternatives and comparison models, but they are not the
current default product model.

## Shared Exact-15 Category Surface

```text
speech
music
dog barking
car engine
footsteps
rain
wind
keyboard typing
phone ringing
crowd noise
bird singing
water flowing
door knocking
alarm
background noise
```

This differs from Waveformer's 20-label surface. For example, Waveformer uses
`dog`; exact-15 models use `dog barking`.

## AudioSepHive15Cat

Package:

```text
ai/models/AudioSepHive15Cat/model_package.json
```

Generated artifacts:

```text
ai/models/Exports/AudioSepHive15Cat/audiosep_hive15cat_exact15/
  shared/frozensep_hive_15cat.onnx
  shared/categories_15.yaml
  shared/categories_15.txt
  source/category_embeddings.pt
```

Role:

```text
Exact-15 ONNX category separator with Wiener post-masking.
```

Runtime contract:

| Field | Value |
| --- | --- |
| Model id | `audiosep_hive15cat` |
| Family | `audiosep` |
| Desktop runtime | `onnx_category_separator` |
| Android runtime | `onnx_category_separator` |
| Artifact | `../Exports/AudioSepHive15Cat/audiosep_hive15cat_exact15/shared/frozensep_hive_15cat.onnx` |
| Sample rate | `32000` |
| Segment length | `5.0` seconds |
| Overlap | `1.0` second |

The runtime uses a fixed category index rather than open text prompts. It is a
packaged exact-category deployment path, not the full naked AudioSep model.

## CodecSepDNRv2_15Cat

Package:

```text
ai/models/CodecSepDNRv2_15Cat/model_package.json
```

Generated artifacts:

```text
ai/models/Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/
  source/codecsep_dnrv2_15cat_frozen.pt
  source/embedding_init.pt
  source/freeze_manifest.json
  source/freeze_spec_15.yaml
  shared/categories_15.yaml
  shared/categories_15.txt
  desktop/codecsep_dnrv2_15cat.onnx
  desktop/codecsep_dnrv2_15cat.onnx.json
  android/codecsep_dnrv2_15cat.pte
  android/codecsep_dnrv2_15cat.pte.json
```

Role:

```text
Frozen CodecSep DNRv2 exact-15 separator.
```

Runtime contract:

| Field | Desktop | Android |
| --- | --- | --- |
| Runtime kind | `onnx_category_separator` | `executorch_category_separator` |
| Artifact | `../Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/desktop/codecsep_dnrv2_15cat.onnx` | `../Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15/android/codecsep_dnrv2_15cat.pte` |
| Sample rate | `16000` | `16000` |
| Segment length | `2.0` seconds | `2.0` seconds |
| Overlap | `0.5` seconds | `0.5` seconds |

The frozen runtime uses category ids/vectors. It does not expose generic
CodecSep text prompting at deployment time.

Important export script:

```text
ai/export/freeze_codecsep_dnrv2_15cat.py
```

## ClapSepHive15Cat

Folder:

```text
ai/models/ClapSepHive15Cat
```

Generated prototype assets now live under:

```text
ai/models/Exports/ClapSepHive15Cat/clapsep_hive15cat_prototype/
  desktop/frozensep_clapsep_15cat.onnx
  source/frozensep_clapsep_15cat.pt
  source/category_embeddings.pt
  source/clapsep_query_embeddings_15.pt
  source/clapsep_queries_15.yaml
```

Status:

```text
Prototype / historical exact-15 experiment.
```

It is not listed in `model_selection.json`, so desktop or mobile product code
should not treat it as an active packaged model.

## When To Use These Models

Use exact-15 models when:

- comparing fixed-category separator families
- demonstrating ONNX category separator behavior
- demonstrating ExecuTorch packaging through CodecSepDNRv2
- explaining the model exploration history

Use Waveformer Edge when describing the current default desktop/mobile semantic
suppression product.
