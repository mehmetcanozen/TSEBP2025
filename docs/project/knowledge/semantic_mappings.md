# Semantic Mappings Knowledge Item

This document describes how runtime suppression categories map into the active backends.

## Core Mapping Logic

The runtime uses two backend-specific mapping files:

- `ai/ai_runtime/config/yamnet_to_waveformer.yaml`
- `ai/ai_runtime/config/category_to_codecsep.yaml`

Waveformer and CodecSep now use those mappings differently:

- Waveformer remains detector-oriented and YAMNet-aware.
- CodecSep explicit suppression is now **AudioCaps-native and detector-free**.

Waveformer remains the default backend unless a command or profile explicitly switches to CodecSep.

## CodecSep AudioCaps-Native Mapping

When `separator_backend=codecsep` is used explicitly:

- YAMNet is bypassed
- requested categories are compiled directly into fixed-slot CodecSep plans
- nuisance/environmental suppression targets the `sfx` slot
- `speech` suppression targets `speech`
- `music` suppression targets `music`

The active default mode is `codecsep_mode=audiocaps_native`.

`experimental_search` still exists, but it is no longer the default contract.

## Runtime Defaults

- Offline batch CodecSep: `audiocaps_native`, mono-shared stereo by default
- Realtime CodecSep: `audiocaps_native`, single-pass fixed-slot behavior
- `codecsep_mode=experimental_search` enables the older slot-search / CLAP-rescoring / multistep path
- `codecsep_mode=compat` forces the old stem-routing fallback

## Runtime Notes

| Category | Waveformer | CodecSep | Notes |
| :--- | :--- | :--- | :--- |
| **Typing** | `Computer_keyboard`, `Writing` | fixed-slot `sfx` prompt profile | Explicit CodecSep suppression does not wait for YAMNet. |
| **Pets** | `Bark`, `Meow` | fixed-slot `sfx` prompt profile | Barking stays on `sfx`; no slot search by default. |
| **Traffic** | `Bus` | fixed-slot `sfx` prompt profile | Prompt text is more specific than the Waveformer target name. |
| **Wind** | No direct target | fixed-slot `sfx` prompt profile | CodecSep covers open-vocabulary nuisance classes through `sfx`. |
| **Speech** | Not suppressed by target mapping | fixed-slot `speech` profile | Clean audio is built from the normalized complement. |
| **Music** | Not suppressed by target mapping | fixed-slot `music` profile | Clean audio is built from the normalized complement. |

## Threshold Logic

- Default threshold is `0.5` for detector-driven Waveformer usage.
- Category-specific detection overrides live in `yamnet_to_waveformer.yaml`.
- CodecSep prompt/slot profiles live in `category_to_codecsep.yaml`.
- Explicit CodecSep suppression does not depend on YAMNet thresholds or detector state.

## CodecSep Default Runtime Source

- Default CodecSep source: `ai/models/CodecSep/codecsep_supplementary_material/codecsep_code/model-checkpoints/CodecSep_AudioCaps_400k_Run1`
- Checkpoint resolution order inside that run directory:
  - `ckpt_best/pytorch_model.bin`
  - `ckpt_best/ckpt_model_best.pth`
  - `ckpt_final/ckpt_model_final.pth`

## Why Native Fixed-Slot

This redesign aligns the runtime with the AudioCaps training/eval contract found in the paper and archived code:

- fixed `speech/music/sfx` slots per forward pass
- detailed nuisance prompts live on `sfx`
- normalized stem outputs are treated as the authoritative separation result
- nuisance `sfx` requests subtract the extracted target from the original mix
- `speech` and `music` requests keep the normalized complement

Supporting references:

- CodecSep OpenReview: <https://openreview.net/forum?id=MDHVDfUrDz>
- AudioCaps dataset card: <https://huggingface.co/datasets/OpenSound/AudioCaps>
- LAION-CLAP README: <https://github.com/LAION-AI/CLAP>
