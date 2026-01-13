"""
Background detection thread for semantic classification.

Runs YAMNet every few seconds on a provided audio buffer, applies temporal smoothing,
and notifies a callback with detection results without blocking the audio pipeline.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_DIR = REPO_ROOT / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.append(str(TRAINING_DIR))

try:
    import psutil
except ImportError:  # pragma: no cover - dependency present in requirements
    psutil = None  # type: ignore

from training.models.semantic_detective import AdaptiveDutyCycle, SemanticDetective


class DetectionThread(threading.Thread):
    """
    Background detection that periodically pulls audio and runs SemanticDetective.

    Args:
        get_audio: Callable returning (audio_np, sample_rate). Should provide ~3s window.
        detective: SemanticDetective instance.
        callback: Function invoked with detection payload.
        duty_cycle: AdaptiveDutyCycle instance (optional).
        base_interval: Fallback interval if duty_cycle is not used.
        battery_fn: Optional callable returning battery percent (0-100).
    """

    def __init__(
        self,
        get_audio: Callable[[], Optional[Tuple[np.ndarray, int]]],
        detective: SemanticDetective,
        callback: Callable[[Dict], None],
        duty_cycle: Optional["AdaptiveDutyCycle"] = None,
        base_interval: float = 3.0,
        battery_fn: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.get_audio = get_audio
        self.detective = detective
        self.callback = callback
        self.duty_cycle = duty_cycle
        self.base_interval = base_interval
        self.battery_fn = battery_fn or self._default_battery_fn
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------ threading --------------------------------- #
    def run(self) -> None:
        """Main detection loop - runs until stop() is called."""
        while not self._stop_event.is_set():
            interval = self._compute_interval()
            payload = self._run_detection()
            if payload is not None:
                try:
                    self.callback(payload)
                except Exception:
                    # Detection results are non-critical; log but don't crash.
                    logger.exception("Detection callback failed")
            time.sleep(interval)

    def _run_detection(self) -> Optional[Dict]:
        """Execute one detection cycle and return results or None if no audio."""
        audio_result = self.get_audio()
        if audio_result is None:
            return None

        audio, sample_rate = audio_result
        try:
            detection = self.detective.classify(audio, sample_rate)
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return None

        top = self.detective.get_top_detections(detection["smoothed"])
        safety = self.detective.check_safety_override(detection["states"])

        return {
            "raw": detection["raw"],
            "smoothed": detection["smoothed"],
            "stable": detection["stable"],
            "states": detection["states"],
            "top": top,
            "safety_override": safety,
        }

    def _compute_interval(self) -> float:
        """Determine sleep interval based on battery level and duty cycle config."""
        if self.duty_cycle is None:
            return self.base_interval
        battery = self.battery_fn()
        if battery is None:
            return self.base_interval
        return self.duty_cycle.get_interval(battery)

    @staticmethod
    def _default_battery_fn() -> Optional[int]:
        """Return battery percentage using psutil, or None if unavailable."""
        if psutil is None or not hasattr(psutil, "sensors_battery"):
            return None
        battery = psutil.sensors_battery()
        if battery is None:
            return None
        return int(battery.percent)


__all__ = ["DetectionThread"]
