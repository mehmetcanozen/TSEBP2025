# Semantic Suppressor: Comprehensive User Manual

Welcome to the **Semantic Suppressor** user manual. This document is the master guide for batch processing, real-time recording, live demos, and backend selection.

---

## Table of Contents
1. [Introduction](#introduction)
2. [Key Technologies](#key-technologies)
3. [Setup and Installation](#setup--installation)
4. [Semantic Categories and Tuning](#semantic-categories--tuning)
5. [User Guide: Tooling](#user-guide-tooling)
6. [Developer Tools: Virtual Microphone](#developer-tools-virtual-microphone)
7. [Advanced Features](#advanced-features)
8. [Troubleshooting and FAQ](#troubleshooting--faq)

**Mobile**: See [MOBILE_DEPLOYMENT.md](MOBILE_DEPLOYMENT.md) for React Native / Expo deployment.

---

## 1. Introduction <a name="introduction"></a>

The Semantic Suppressor is an audio-cleaning pipeline for removing unwanted sounds while preserving useful foreground content such as speech. Two backend families are relevant:

- **Waveformer** remains detector-oriented and YAMNet-aware.
- **CodecSep** now uses an **AudioCaps-native fixed-slot runtime** for explicit suppression and open-vocabulary nuisance removal.

That means when you explicitly choose `--separator-backend codecsep`, the runtime no longer waits for YAMNet detections before acting. It directly compiles your request into an AudioCaps-style `speech/music/sfx` separation pass.

## 2. Key Technologies <a name="key-technologies"></a>

- **YAMNet**: Sound classifier used for detector-driven Waveformer flows.
- **Waveformer**: Target separator for detector-oriented suppression.
- **CodecSep**: AudioCaps-native prompt-conditioned separator with fixed `speech/music/sfx` slots.
- **DeepFilterNet**: High-performance `--suppress-all` voice-cleaning mode.
- **Spectral Masking**: Phase-aware cleanup used where appropriate to reduce artifacts.

## 3. Setup and Installation <a name="setup--installation"></a>

- **Virtual Environment**: Use `.\shared\scripts\setup_env.ps1` on Windows to create the shared project `.venv`.
- **Base Models**: Run `python ai\scripts\setup\download_models.py` to fetch pretrained Waveformer and YAMNet assets.
- **AudioSep**: Run `python ai\scripts\setup\install_audiosep.py` to install the open-vocabulary foundation model and its large weights.
- **VB-Audio Cable**: Optional, but useful for virtual microphone testing.

### Pre-requisites

Run the shared setup script, or install dependencies manually:

```bash
pip install -r desktop/requirements.txt
pip install -r ai/training/requirements.txt
```

If you hit `ImportError` issues involving `lightning`, `transformers`, or `torchlibrosa`, rerun the setup flow and verify the shared environment is active.

---

## 4. Semantic Categories and Tuning <a name="semantic-categories--tuning"></a>

The system groups many low-level sound classes into practical suppression categories.

| Category | Typical Sounds |
| :--- | :--- |
| `speech` | Human voices, narration, conversation |
| `typing` | Mechanical and laptop keyboard clicks |
| `pets` | Dog barks, cat meows, bird chirps |
| `phone` | Ringtones, dial tones, digital notifications |
| `music` | Singing, instruments, background tracks |
| `nature` | Wind, rain, thunder, water |
| `explosions` | Fireworks, gunshots, loud booms |
| `glass_impact` | Shattering, smashing, impacts |
| `bodily_functions` | Coughing, sneezing, throat noises |
| `misc` | Knocks, laughter, keys jangling, everyday sounds |

### Tuning Parameters

- **`--threshold [0.0-1.0]`**: Detection sensitivity for detector-driven Waveformer usage. Explicit CodecSep suppression does not depend on YAMNet thresholds or detector confidence.
- **`--aggressiveness [1.0-2.5+]`**: Suppression strength. Default `1.5`. Higher values remove more target content. CodecSep category profiles may also raise effective strength internally for categories like `typing` and `pets`.

---

## 5. User Guide: Tooling <a name="user-guide-tooling"></a>

### A. Batch Processing (Offline) <a name="batch-processing-offline"></a>

Process existing files with maximum offline quality.

- **Script**: `python -m ai.ai_runtime.batch.batch_processor`
- **Flag `--output-noise`**: Saves an extra file containing what was removed. In native CodecSep mode, this is the extracted target stem.

```bash
# Clean a keyboard recording and save the removed target
python -m ai.ai_runtime.batch.batch_processor --input mysample.wav --output clean.wav --suppress typing --output-noise

# Stronger multi-category suppression
python -m ai.ai_runtime.batch.batch_processor --input noisy.wav --output clean.wav --suppress typing,pets --aggressiveness 1.8

# AudioCaps-native CodecSep batch suppression
python -m ai.ai_runtime.batch.batch_processor --input noisy.wav --output clean.wav --output-noise --suppress typing --separator-backend codecsep --codecsep-device cpu --codecsep-sfx-prompt "keyboard typing sounds, key clicks from a computer keyboard"
```

#### CodecSep offline defaults

When `--separator-backend codecsep` is used in batch mode, the runtime defaults to:

- `codecsep_mode=audiocaps_native`
- fixed-slot AudioCaps-native execution
- `codecsep_stereo_mode=mono_shared`
- no external CLAP rescoring
- no slot search
- no multistep refinement

In practice:

- nuisance and environmental categories target the `sfx` slot
- `speech` suppression targets `speech`
- `music` suppression targets `music`
- the runtime first applies AudioCaps-style input conditioning to the mix before separation
- target prompting now uses richer caption-like phrasing internally instead of only terse keyword bags
- nuisance `sfx` requests remove the extracted target from the original mix
- `speech` and `music` requests keep the normalized complement
- `--output-noise` saves the extracted target stem itself

### B. Real-time Recorder and Cleaner <a name="real-time-recorder--cleaner"></a>

Record from a microphone and get cleaned output immediately.

- **Script**: `python -m ai.ai_runtime.audio.recorder_cleaner`
- **Flag `--device [ID]`**: Select a specific microphone or virtual cable input.

```bash
# Record for 15 seconds, suppressing pets and phone sounds
python -m ai.ai_runtime.audio.recorder_cleaner --duration 15 --suppress pets,phone --device 0

# Stronger suppression
python -m ai.ai_runtime.audio.recorder_cleaner --duration 15 --suppress typing,pets --aggressiveness 1.8 --device 0

# Realtime CodecSep with AudioCaps-native fixed-slot suppression
python -m ai.ai_runtime.audio.recorder_cleaner --duration 15 --suppress typing --separator-backend codecsep --codecsep-device cpu --codecsep-sfx-prompt "keyboard typing sounds, key clicks from a computer keyboard" --device 0
```

### C. Live Suppression Demo <a name="live-suppression-demo"></a>

Monitor live suppression through speakers or headphones.

- **Script**: `ai/scripts/demos/demo_custom_realtime.py`

```bash
# Live voice extraction with DeepFilterNet
python ai/scripts/demos/demo_custom_realtime.py --suppress-all --device 1
```

---

## 6. Developer Tools: Virtual Microphone <a name="developer-tools-virtual-microphone"></a>

Use VB-Audio Virtual Cable to stream a WAV file into the suppressor as if it were a microphone.

1. Install **VB-Cable**.
2. Start the streamer:

```bash
python ai/scripts/demos/virtual_mic_streamer.py --input ai/data/audio/raw/barking.wav
```

3. Find the `CABLE Output` device ID:

```bash
python ai/scripts/demos/demo_custom_realtime.py --list-devices
```

4. Use that `--device` ID in the recorder or live demo commands.

---

## 7. Advanced Features <a name="advanced-features"></a>

- **Universal Prompts**: Use `--universal "heavy breathing, mechanical fan"` for prompt-based removal.
- **Selectable Backends**: `waveformer` is still the default backend. `codecsep` can be enabled explicitly for AudioCaps-native prompt-conditioned suppression.
- **CodecSep Runtime Controls**:
  - `--codecsep-mode audiocaps_native|experimental_search|compat|auto`
  - `--codecsep-stereo-mode mono_shared|per_channel`
  - `--codecsep-speech-prompt "..."`, `--codecsep-music-prompt "..."`, `--codecsep-sfx-prompt "..."`
  - `--codecsep-query-strategy single_pass|slot_search` for `experimental_search` only
  - `--codecsep-multistep-steps N` for `experimental_search` only
  - `--codecsep-negative-prompt "..."` for `experimental_search` only
  - `--codecsep-preserve-prompt "..."` for `experimental_search` only
- **Compatibility Escape Hatch**: `--codecsep-mode compat` forces the older routed-stem fallback for debugging or regression checks.

---

## 8. Troubleshooting and FAQ <a name="troubleshooting--faq"></a>

- **"Empty Files"**: Verify the correct `--device` ID with `--list-devices`.
- **"Clicks and Pops"**: The CPU may be overloaded. Close other apps or reduce aggressiveness.
- **"Missing Detection"**: For Waveformer, check `ai/ai_runtime/config/yamnet_to_waveformer.yaml`. For explicit CodecSep suppression, check `ai/ai_runtime/config/category_to_codecsep.yaml` to confirm the category's fixed-slot prompt profile.
- **"CodecSep sounds like plain 3-stem extraction"**: That is partly expected. The active runtime intentionally uses the AudioCaps-native fixed-slot contract, so `speech/music/sfx` remain the model's internal slots and nuisance suppression usually targets `sfx` directly.
- **"Why does CodecSep ignore my negative/preserve prompts?"**: In default `audiocaps_native` mode, those controls are intentionally ignored. Use `--codecsep-mode experimental_search` only if you are deliberately testing the heavier research path.
- **"ImportError: No module named..."**: Reinstall the project dependencies and verify the intended environment is active.
- **"AudioSep Path Errors"**: Ensure `install_audiosep.py` has been run and `ai/models/AudioSep/pipeline.py` exists.
