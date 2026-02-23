# Semantic Suppressor: Comprehensive User Manual

Welcome to the **Semantic Suppressor** user manual. This document serves as the master guide for all components of the system, including batch processing, real-time recording, and interactive developer tools.

---

## 🚀 Table of Contents
1. [Introduction](#introduction)
2. [Key Technologies](#key-technologies)
3. [Setup & Installation](#setup--installation)
4. [Semantic Categories & Tuning](#semantic-categories--tuning)
5. [User Guide: Tooling](#user-guide-tooling)
    - [Batch Processing (Offline)](#batch-processing-offline)
    - [Real-time Recorder & Cleaner](#real-time-recorder--cleaner)
    - [Live Suppression Demo](#live-suppression-demo)
6. [Developer Tools: Virtual Microphone](#developer-tools-virtual-microphone)
7. [Advanced Features](#advanced-features)
8. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## 1. Introduction <a name="introduction"></a>
The Semantic Suppressor is an AI-driven audio pipeline designed to intelligently remove background noises while preserving speech and critical safety sounds (like sirens). Unlike traditional noise suppressors that use static filters, this system uses **Semantic Recognition (YAMNet)** to first identify *what* the sound is, and then uses **Target Sound Extraction (Waveformer)** to surgically remove it.

## 2. Key Technologies <a name="key-technologies"></a>
- **YAMNet**: Analyzes 521 categories of sounds.
- **Waveformer**: Extracts specific audio targets from a mixture.
- **DeepFilterNet**: High-performance "Suppress All" mode for pure voice extraction.
- **Spectral Masking (Ratio Masking)**: Used for Phase-accurate noise removal to prevent artifacts.

## 3. Setup & Installation <a name="setup--installation"></a>
- **Virtual Environment**: Use `.\scripts\setup_env.ps1` on Windows.
- **Models**: Run `python scripts\download_models.py` to fetch pretrained weights.
- **VB-Audio Cable (Optional but Recommended)**: Required for the [Virtual Microphone Simulation](#developer-tools-virtual-microphone).

---

## 4. Semantic Categories & Tuning <a name="semantic-categories--tuning"></a>
The system groups 500+ YAMNet classes into actionable categories. You can control these via the `--suppress` flag.

| Category | Typical Sounds |
| :--- | :--- |
| `speech` | Human voices, narration, conversation. |
| `typing` | Mechanical and laptop keyboard clicks. |
| `pets` | Dog barks, cat meows, bird chirps. |
| `phone` | Ringtones, dial tones, digital notifications. |
| `music` | 16+ instruments, singing, background tracks. |
| `nature` | Wind, rain, thunder, water. |
| `explosions` | Gunshots, fireworks, loud booms. |
| `glass_impact` | Shattering, smashing, impacts. |
| `bodily_functions` | Burping, hiccuping, etc. |
| `misc` | Coughing, laughter, sneezing, keys jangling. |

### Tuning Parameters
- **`--threshold [0.0-1.0]`**: Sensitivity. Lower values (e.g., `0.03`) make the detector more aggressive.
- **`--aggressiveness [1.0-4.0]`**: Determines how "deeply" to strip the noise. `1.0` is natural, `4.0` is total erasure.

---

## 5. User Guide: Tooling <a name="user-guide-tooling"></a>

### A. Batch Processing (Offline) <a name="batch-processing-offline"></a>
Process existing audio files with maximum accuracy.
- **Script**: `desktop/src/batch/batch_processor.py`
- **Flag `--output-noise`**: Saves an extra file containing *exactly* what was removed.

```bash
# Example: Clean a keyboard recording and save the noise stem
python desktop/src/batch/batch_processor.py --input mysample.wav --output clean.wav --suppress typing --output-noise
```

### B. Real-time Recorder & Cleaner <a name="real-time-recorder--cleaner"></a>
Record directly from your mic and get a cleaned version instantly.
- **Script**: `python -m desktop.src.audio.recorder_cleaner`
- **Flag `--device [ID]`**: Use this to select a specific microphone.

```bash
# Record for 15 seconds, suppressing pets and phone sounds
python -m desktop.src.audio.recorder_cleaner --duration 15 --suppress pets,phone --device 0
```

### C. Live Suppression Demo <a name="live-suppression-demo"></a>
A "monitor" mode where you can hear the suppression in real-time through your speakers/headphones.
- **Script**: `desktop/scripts/demo_custom_realtime.py`

```bash
# Live Voice Extraction (DeepFilterNet Mode)
python desktop/scripts/demo_custom_realtime.py --suppress-all --device 1
```

---

## 6. Developer Tools: Virtual Microphone <a name="developer-tools-virtual-microphone"></a>
To test the suppressor without physically making noise, you can "stream" a WAV file into the system as if it were a microphone.

1. Install **VB-Cable**.
2. Run the streamer:
   ```bash
   python desktop/scripts/virtual_mic_streamer.py --input samples/audio/barking.wav
   ```
3. Find your "CABLE Output" ID:
   ```bash
   python desktop/scripts/demo_custom_realtime.py --list-devices
   ```
4. Run your test scripts using that `--device` ID.

---

## 7. Advanced Features <a name="advanced-features"></a>
- **Universal Prompts**: Users of Phase 3 can specify a text prompt for *any* sound.
  `--universal "heavy breathing, mechanical fan"`
- **Safety Bypass**: `siren` and `alarm` categories are hard-coded to NEVER be suppressed in the `ControlEngine` to ensure user awareness of emergencies.

## 8. Troubleshooting & FAQ <a name="troubleshooting--faq"></a>
- **"Empty Files"**: Ensure you have selected the correct `--device` ID. Use `--list-devices` to verify.
- **"Clicks and Pops"**: This usually indicates the CPU is struggling. Try closing other apps or lowering the `--aggressiveness`.
- **"Missing Detection"**: Check `shared/mappings/yamnet_to_waveformer.yaml` to ensure the sound you want is mapped to a category.
