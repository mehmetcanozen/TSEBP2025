# CodecSep AudioCaps-Native Runtime

This note documents the active runtime integration strategy for CodecSep after the AudioCaps-native overhaul.

## Why This Exists

The previous runtime treated the AudioCaps-trained CodecSep checkpoint as if it were a slot-searchable query engine. That diverged from the paper and archived AudioCaps eval path, which use CodecSep as a **fixed three-slot separator** with prompt-conditioned semantics:

- `speech` stays speech-like
- `music` stays music-like
- `sfx` carries the open-vocabulary nuisance/environmental prompt

The active runtime now defaults to that native contract.

## Active Runtime Contract

Default mode is `codecsep_mode=audiocaps_native`.

In this mode:

- one fixed forward pass predicts `speech`, `music`, and `sfx`
- explicit suppression does **not** use YAMNet gating
- nuisance/environmental categories route to `sfx`
- `speech` suppression routes to `speech`
- `music` suppression routes to `music`
- nuisance `sfx` requests subtract the extracted target from the original mix
- `speech` and `music` requests keep the normalized complement stems
- extracted/noise audio is the target stem itself

`CodecSepQueryPlan` is still used internally, but in native mode it is much simpler:

- `target_prompts`
- `preferred_slot`
- optional prompt overrides for the non-target anchor slots
- `subtract_target` for nuisance `sfx`
- `keep_complement` for `speech` and `music`

## Modes

### `audiocaps_native`

This is the default and recommended mode.

- fixed-slot AudioCaps behavior
- no external CLAP rescoring
- no slot search
- no multistep refinement

### `experimental_search`

This preserves the older search-heavy runtime for debugging and research only.

- slot search can inspect alternate slots
- external CLAP rescoring is allowed
- negative/preserve prompts are used
- multistep refinement is allowed

### `compat`

Legacy stem-routing fallback.

- uses the old `stems:` / `prompts:` path
- kept only for debugging and regression checks

## Offline vs Realtime

### Offline batch

- defaults to `audiocaps_native`
- mono-shared stereo policy by default
- lightweight overlap/crossfade chunking
- `--codecsep-stereo-mode per_channel` is available as a slower debug path

### Realtime

- defaults to `audiocaps_native`
- low-latency single-pass fixed-slot behavior
- no search/refinement by default

## Config Shape

`ai/ai_runtime/config/category_to_codecsep.yaml` still contains:

- `stems`
- `prompts`
- `queries`

But the intent is now:

- `queries` primarily define the **fixed slot + target prompt profile**
- `stems` / `prompts` remain the compatibility fallback
- richer fields such as `negative_prompts`, `preserve_prompts`, `alternate_slots`, and `use_multistep` are only used by `experimental_search`

## Safety

This redesign is runtime-only.

It does **not** modify:

- the active 400k training process
- training configs
- training checkpoints
- training code under `ai/models/CodecSep/.../codecsep_code`

## External Grounding

- CodecSep OpenReview: <https://openreview.net/forum?id=MDHVDfUrDz>
- AudioCaps dataset card: <https://huggingface.co/datasets/OpenSound/AudioCaps>
- LAION-CLAP README: <https://github.com/LAION-AI/CLAP>
