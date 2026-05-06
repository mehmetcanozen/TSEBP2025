# Semantic Mappings Knowledge Item

Semantic mapping is where many stale explanations can go wrong. The project has
multiple category surfaces, and they are not interchangeable.

## Current Product Surface: Waveformer 20

The active default package exposes these 20 ids:

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

Desktop and Android product UIs should display categories from the active
package manifest. Do not substitute YAMNet aliases or exact-15 labels when the
runtime reports `waveformer_edge_100ms`.

## Exact-15 Surface

AudioSepHive15Cat and CodecSepDNRv2_15Cat use a different fixed surface:

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

This surface is useful for exact-category package experiments. It should be
presented as exact-15, not as the current Waveformer category list.

## Python Legacy Mapping

The Python reference runtime still contains mapping files such as:

- `yamnet_class_map.yaml`
- `yamnet_to_waveformer.yaml`
- `category_to_codecsep.yaml`
- `product_to_hive_fixedset.json`
- `default_profiles.json`

These are used for detection, aliasing, profile defaults, and bridging product
categories to backend-specific category names. They are especially relevant for
offline Python commands and legacy Waveformer/YAMNet flows.

## Detection Thresholds

The YAMNet-based path uses confidence thresholds and category-specific mapping
rules. Some categories are effectively manual or always-suppress in certain
backend paths because exact packaged category separators do not need YAMNet to
detect the sound first.

For product packaged runtimes, category selection is explicit: the UI sends the
selected package category id and aggressiveness to the runtime.

## Backend-Specific Mapping Rules

- Waveformer package: use the 20 manifest ids directly.
- AudioSepHive15Cat: resolve exact-15 ids/class ids.
- CodecSepDNRv2_15Cat: resolve exact-15 ids and runtime-specific category
  vector/index inputs.
- Generic CodecSep: compile prompts or fixed-slot plans depending on mode.
- TargetSpeakerWindows: ignore category labels and use a reference speaker.

## Common Mistakes

- Using `barking` as a category. The current Waveformer id is `dog`; exact-15
  uses `dog barking`.
- Calling the current desktop/mobile model AudioSepHive15Cat. The default is
  Waveformer unless `model_selection.json` changes.
- Treating Native UNet/TFLite labels as current mobile truth. That path is
  historical.
- Mixing human display labels with backend ids in command examples.

## Documentation Rule

When documenting a category, state which surface it belongs to:

```text
Waveformer 20: dog
Exact-15: dog barking
Generic CodecSep prompt: dog barking sounds
Target speaker: reference clip, no semantic category
```
