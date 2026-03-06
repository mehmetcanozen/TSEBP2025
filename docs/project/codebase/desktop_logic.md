# 🧠 System Logic - Decisions & Profiles

> [!TIP]
> This module acts as the "Brain" of the application, translating raw AI detections into user-facing profile changes.

---

## ⚡ Quick Reference: Logic & Heuristics

| Component | Logic Pattern | Heuristic / Constants | Rationale |
| :--- | :--- | :--- | :--- |
| **`ControlEngine` (auto mode)** | Best-score | `auto_triggers` | Picks profile with highest trigger confidence sum; hysteresis may be added later. |
| **`ControlEngine`** | Efficiency skip | `RMS < 0.01` | Skips expensive 400ms inference if the room is silent. |
| **`ProfileManager`** | Persistence | `platformdirs` | Ensures user profiles survive app updates and OS reinstalls. |

---

## 📂 Component Deep Dive

### [control_engine.py](../../../ai/ai_runtime/profiles/control_engine.py)
*   **Method**: `process_audio()`
*   **Logic**: 
    1. Check for **Passthrough** (no active suppressions).
    2. Build list of active suppression categories from current profile.
    3. Route to suppressor pipeline.
*   **Why**: Running Waveformer on a 3-second buffer every few hundred milliseconds consumes ~15-30% CPU. If there is no sound to clean, we skip the work to save battery.

### Auto-mode profile switching (ControlEngine)
*   **Method**: `_evaluate_auto_mode()`
*   **Logic**: Scores each profile by sum of detection confidences above its trigger thresholds; selects highest.
*   **Note**: AutoController (hysteresis) was removed; auto-mode logic lives in ControlEngine.

---

> [!WARNING]
> **Performance Note**: The `ControlEngine` runs on the UI thread main loop. Never perform heavy file I/O or model inference here; delegate that to `AudioProcess`.
