# Semantic Mappings Knowledge Item

This document details the mapping between YAMNet (Semantic Detection) and Waveformer (Signal Separation).

## Core Mapping Logic
The system uses `shared/mappings/yamnet_to_waveformer.yaml` to bridge the two models. YAMNet indices indicate *what* is present, and Waveformer targets indicate *what* can be removed.

### Critical Safety Overrides
Some sounds are flagged as `safety_override: true`.
- **Siren** (Categories: Siren, Ambulance, Police car)
- **Alarm** (Categories: Fire alarm, Smoke detector)

When these are detected with confidence > 0.5, **all suppression is bypassed** to ensure the user stays aware of their environment.

### Fine-Tuned Categories

| Category | YAMNet Indices (Ref) | Waveformer Target | Special Notes |
| :--- | :--- | :--- | :--- |
| **Typing** | 378, 380 | Computer_keyboard | Lowered threshold (0.03) to catch quiet keystrokes. |
| **Traffic** | 323-326 | Bus | Handles heavy engine drones well. |
| **Wind** | 486-487 | N/A | Currently marked for DSP fallback (Spectral Gating). |
| **Speech** | 0-5 | N/A | Never suppressed; used as the "Keep" signal. |

## Threshold Logic
- **Default Threshold**: 0.3 (30% confidence).
- **Typing Override**: 0.03. Empirical testing showed that YAMNet often detects typing at very low confidence levels when mixed with loud environments or speech. This low threshold ensures keyboard noise is aggressively targeted.

## Future Improvements
- **Spectral Gating**: For categories like "Wind" that lack a Waveformer target, we plan to implement traditional spectral gating.
- **Auto-Profile Switching**: Logic to automatically switch from "Office" to "Commute" based on sustained detection of traffic.
