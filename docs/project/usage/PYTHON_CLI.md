# Python CLI

The Python CLI is the fastest way to test file-based suppression and compare
model families. Run commands from the repository root.

## Default Waveformer batch suppression

```powershell
cd C:\SoftwareProjects\TSEBP2025

python -m ai.ai_runtime.batch.batch_processor `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_waveformer_dog.wav `
  --suppress dog `
  --aggressiveness 1.1 `
  --output-noise
```

Waveformer uses `dog` for barking demos. Exact-15 alternatives use different
labels such as `dog barking`.

## Record and clean a microphone session

```powershell
python -m ai.ai_runtime.audio.recorder_cleaner `
  --duration 10 `
  --suppress typing,wind `
  --output .\ai\data\audio\processed\session_clean.wav
```

## Live Python demo helpers

```powershell
python .\ai\scripts\demos\demo_custom_realtime.py --list-categories
python .\ai\scripts\demos\demo_custom_realtime.py --list-devices
python .\ai\scripts\demos\demo_custom_realtime.py --suppress typing
```

## Exact-15 AudioSepHive15Cat

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input .\ai\data\audio\raw\speech_alarm.wav `
  --output .\ai\data\audio\processed\speech_alarm_audiosep15.wav `
  --separator-backend audiosep_hive15cat `
  --suppress "keyboard typing,alarm" `
  --aggressiveness 1.4
```

## CodecSepDNRv2 exact-15 ONNX

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input .\ai\data\audio\raw\speech_barking.wav `
  --output .\ai\data\audio\processed\speech_barking_codecsep15.wav `
  --separator-backend codecsep_dnrv2_15cat `
  --codecsep15-runtime onnx `
  --suppress "dog barking" `
  --aggressiveness 1.4
```

## Open-vocabulary AudioSep

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input .\ai\data\audio\raw\speech_boat.wav `
  --output .\ai\data\audio\processed\speech_boat_universal.wav `
  --universal "boat engine, water noise"
```

## DeepFilterNet suppress-all path

Use this when you want speech-focused enhancement without category selection:

```powershell
python -m ai.ai_runtime.batch.batch_processor `
  --input .\ai\data\audio\raw\noisy_speech.wav `
  --output .\ai\data\audio\processed\noisy_speech_suppress_all.wav `
  --suppress-all
```

## Notes

- The product default is still `waveformer_edge_100ms`.
- Comparison backends are useful for evaluation, but they are not the normal
  desktop or Android live path unless model selection is intentionally changed.
- If a model artifact is missing, restore `ai/models/Exports` first. Do not
  debug runtime code while the artifact bundle is incomplete.
