# Semantic Mappings Knowledge Item

This document details the mapping between YAMNet (Semantic Detection) and Waveformer (Signal Separation).

## Core Mapping Logic
The system uses `shared/mappings/yamnet_to_waveformer.yaml` to bridge the two models. YAMNet indices indicate *what* is present, and Waveformer targets indicate *what* can be removed.

Most categories are user-controllable suppression targets. However, a category can only be suppressed if it has a corresponding Waveformer target (see the table below and `yamnet_to_waveformer.yaml`). As of now, Siren and Alarm do not have Waveformer targets and therefore cannot be directly suppressed via Waveformer.

### Fine-Tuned Categories

| Category | YAMNet Indices (Ref) | Waveformer Target | Special Notes |
| :--- | :--- | :--- | :--- |
| **Siren** | 388-390 | N/A | Not currently mapped to a Waveformer target; cannot be directly suppressed until the mapping/TARGETS list is updated. |
| **Alarm** | 387, 388, 403 | N/A | Not currently mapped to a Waveformer target; cannot be directly suppressed until the mapping/TARGETS list is updated. |
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
