# CodecSep Query-First Runtime

CodecSep appears in two different roles:

1. A Python research/runtime backend with query-first and AudioCaps-native
   behavior.
2. A frozen exact-15 deployment package named `codecsep_dnrv2_15cat`.

This document covers the first role and explains how it differs from packaged
product runtimes.

## Why Query-First Exists

Generic CodecSep can separate sources using text-like semantic descriptions.
That is useful for research because the desired sound may not fit a fixed
product category. The runtime can compile target prompts, preserve prompts,
negative prompts, and reconstruction policies before calling the separator.

The tradeoff is complexity: query-first behavior is less package-friendly than
a fixed category id or label vector.

## Modes

### `audiocaps_native`

AudioCaps-native mode treats the runtime as a fixed-slot query problem. It can
compile a plan, route prompts into slots, and choose policies such as keeping
the complement when suppressing speech-like categories.

This is the preferred generic CodecSep research mode when the goal is faithful
query behavior rather than legacy compatibility.

### `experimental_search`

Experimental search tries broader prompt/slot exploration. Use it for
investigation, not as product documentation or a default app behavior.

### `compat`

Compatibility mode preserves older behavior for legacy category mappings. It is
useful when old commands or tests depend on earlier category names, but it
should not be presented as the future product interface.

### `fixed_category`

The batch CLI defaults CodecSep-related arguments toward fixed-category
behavior where appropriate. For the packaged exact-15 derivative, use
`codecsep_dnrv2_15cat` rather than generic query-first mode.

## Inputs And Overrides

The Python CLI/runtime can accept:

- `--separator-backend codecsep`
- `--universal` prompts
- prompt overrides
- negative prompts
- preserve prompts
- product categories
- hive class ids
- query strategy and multistep settings

These options are intentionally research-facing. They are not part of the
current desktop/mobile packaged Waveformer default.

## Reconstruction

Generic CodecSep can reconstruct clean audio through residual subtraction,
normalized stem reconstruction, or complement policies depending on the plan.
This is different from the current Waveformer package, which predicts a target
chunk and directly subtracts it.

## Relation To CodecSepDNRv2_15Cat

`codecsep_dnrv2_15cat` freezes a selected fixed-category behavior into
deployable artifacts:

- desktop ONNX category separator
- Android ExecuTorch category separator
- exact-15 category metadata
- package manifest

At that point, runtime prompts are no longer the public interface. The app uses
category ids/vectors declared by the package.

## Safety And Documentation Boundary

When writing docs or demos:

- Say "generic CodecSep query-first" for the Python research backend.
- Say "CodecSepDNRv2 exact-15" for the packaged deployment model.
- Do not describe query-first prompt behavior as the desktop/mobile product
  default.
- Do not use CodecSep wording to explain the current Waveformer ONNX default.
