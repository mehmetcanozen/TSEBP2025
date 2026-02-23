# 🤖 Models & Training - AI Stabilization

> [!NOTE]
> This module handles the raw neural network weights and the "Signal Conditioning" required to make AI predictions usable in a real-time audio pipeline.

---

## ⚡ Quick Reference: Stabilization Heuristics

| Component | Logic Pattern | Heuristic / Constants | Rationale |
| :--- | :--- | :--- | :--- |
| **`SchmittTrigger`** | Hysteresis | `On: 0.7, Off: 0.4` | Stops toggle-flipping when noise volume is borderline. |
| **`ConfidenceBuffer`** | Majority Vote | `2-of-3 frames` | Ignores momentary spikes (e.g. a single hand clap) from triggering profiles. |
| **`Waveformer`** | Multitarget Query | `TARGETS (73)` | Allows a single model to separate dozens of different noise types. |
| **`AdaptiveDuty`** | Energy Control | `3s / 8s / 15s` | Scales detection cadence based on system battery percentage. |

---

## 📈 Signal Stabilization Pipeline

Raw AI detections are too unstable for direct audio mixing. Every prediction passes through this filter chain:

```mermaid
graph LR
    RAW[Raw YAMNet Scores] --> MED[Median Filter]
    MED --> CONF[Majority Voting Buffer]
    CONF --> SCHMITT{Schmitt Trigger}
    SCHMITT -- "On (High Confidence)" --> ON[Active Category]
    SCHMITT -- "Off (Low Confidence)" --> OFF[Inactive Category]
    
    style SCHMITT fill:#f1c40f,stroke:#333
    style CONF fill:#3498db,stroke:#333,color:#fff
```

---

## 📂 Component Deep Dive

### [semantic_detective.py](file:///c:/SoftwareProjects/TSEBP2025/training/models/semantic_detective.py)
*   **The "Schmitt Trigger" (Hysteresis)**:
    - **Logic**: A sound must hit **0.7** confidence to turn "On", but only needs to drop below **0.4** to turn "Off".
    - **Why**: Imagine a dog barking far away. The AI confidence might jump between 0.45 and 0.55. Without hysteresis, the noise suppression would rapidly click on and off.
*   **Majority Voting**:
    - **Logic**: We keep a history of the last 3 frames. A sound is "Stable" only if it was present in 2 out of those 3.

### [audio_mixer.py](file:///c:/SoftwareProjects/TSEBP2025/training/models/audio_mixer.py)
*   **Method**: `_build_query()`
*   **Detail**: Translates semantic group names (e.g., "Transportation") into a 73-dimensional multi-hot vector.
*   **Why**: Waveformer is a **Unified Architecture**. Instead of loading 70 different models, we load one model and "tell" it what to separate using these query vectors.

### [yamnet_to_waveformer.yaml](file:///c:/SoftwareProjects/TSEBP2025/shared/mappings/yamnet_to_waveformer.yaml)
*   **Logic**: This YAML bridges the 521 AudioSet classes to our 73 Waveformer target heads.
*   **Heuristic Overrides**: Keyboard noise (`typing`) has a lower detection threshold than `wind` because keyboards produce quiet but consistent high-frequency energy that YAMNet often under-scores.

---

> [!IMPORTANT]
> **Thread Safety**: `SemanticDetective` is **NOT** thread-safe. Each instance contains rolling history buffers. If shared across threads, the "Schmitt Trigger" states will become corrupted.
