# 🧠 System Logic - Decisions & Profiles

> [!TIP]
> This module acts as the "Brain" of the application, translating raw AI detections into user-facing profile changes.

---

## ⚡ Quick Reference: Logic & Heuristics

| Component | Logic Pattern | Heuristic / Constants | Rationale |
| :--- | :--- | :--- | :--- |
| **`AutoController`** | Hysteresis | `Min Diff: 0.1` | Prevents the system from "oscillating" between two similar profiles. |
| **`ControlEngine`** | Efficiency skip | `RMS < 0.01` | Skips expensive 400ms inference if the room is silent. |
| **`ProfileManager`** | Persistence | `platformdirs` | Ensures user profiles survive app updates and OS reinstalls. |

---

## 📂 Component Deep Dive

### [control_engine.py](file:///c:/SoftwareProjects/TSEBP2025/desktop/src/profiles/control_engine.py)
*   **Method**: `process_audio()`
*   **Logic**: 
    1. Check for **Passthrough** (no active suppressions).
    2. Build list of active suppression categories from current profile.
    3. Route to suppressor pipeline.
*   **Why**: Running Waveformer on a 3-second buffer every few hundred milliseconds consumes ~15-30% CPU. If there is no sound to clean, we skip the work to save battery.

### [auto_controller.py](file:///c:/SoftwareProjects/TSEBP2025/desktop/src/profiles/auto_controller.py)
*   **Method**: `should_switch_profile()`
*   **Heuristic**: `(new_confidence - current_confidence) > 0.1`
*   **Why**: If two profiles ("Office" and "Coffee Shop") have nearly identical detection triggers, YAMNet might flip-flop between them. The **10% Hysteresis** margin ensures we only switch if we are significantly more confident in the new environment.

---

> [!WARNING]
> **Performance Note**: The `ControlEngine` runs on the UI thread main loop. Never perform heavy file I/O or model inference here; delegate that to `AudioProcess`.
