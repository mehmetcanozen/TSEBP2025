# Semantic Mappings Knowledge Item

This document details the mapping between YAMNet (Semantic Detection) and Waveformer (Signal Separation).

## Core Mapping Logic
The system uses `shared/mappings/yamnet_to_waveformer.yaml` to bridge the two models. YAMNet indices indicate *what* is present, and Waveformer targets indicate *what* can be removed.

All categories — including siren and alarm — are user-controllable suppression targets. There are no hardcoded restrictions on which sounds can be suppressed.

### Fine-Tuned Categories

| Category | YAMNet Indices (Ref) | Waveformer Target | Special Notes |
| :--- | :--- | :--- | :--- |
| **Siren** | 388-390 | Siren | Now suppressible like any other category. |
| **Alarm** | 387, 388, 403 | Alarm | Now suppressible like any other category. |
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
