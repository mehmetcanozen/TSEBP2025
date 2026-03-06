"""
Background detection thread for semantic classification.

Runs YAMNet every few seconds on a provided audio buffer, applies temporal smoothing,
and notifies a callback with detection results without blocking the audio pipeline.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional, Tuple

import numpy as np

from .semantic_detective import AdaptiveDutyCycle, SemanticDetective

logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


class DetectionThread(threading.Thread):
    """Background detection that periodically pulls audio and runs SemanticDetective."""

    def __init__(
        self,
        get_audio: Callable[[], Optional[Tuple[np.ndarray, int]]],
        detective: SemanticDetective,
        callback: Callable[[Dict], None],
        duty_cycle: Optional[AdaptiveDutyCycle] = None,
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

    def run(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.monotonic()
            payload = self._run_detection()
            if payload is not None:
                try:
                    self.callback(payload)
                except Exception:
                    logger.exception("Detection callback failed")

            elapsed = time.monotonic() - start_time
            interval = self._compute_interval()
            sleep_time = max(0.0, interval - elapsed)
            if self._stop_event.wait(sleep_time):
                break

    def _run_detection(self) -> Optional[Dict]:
        audio_result = self.get_audio()
        if audio_result is None:
            return None

        audio, sample_rate = audio_result
        try:
            detection = self.detective.classify(audio, sample_rate)
        except Exception as exc:
            logger.error("Classification failed: %s", exc)
            return None

        top = self.detective.get_top_detections(detection["smoothed"])
        return {
            "raw": detection["raw"],
            "smoothed": detection["smoothed"],
            "stable": detection["stable"],
            "states": detection["states"],
            "top": top,
        }

    def _compute_interval(self) -> float:
        if self.duty_cycle is None:
            return self.base_interval
        battery = self.battery_fn()
        if battery is None:
            return self.base_interval
        return self.duty_cycle.get_interval(battery)

    @staticmethod
    def _default_battery_fn() -> Optional[int]:
        if psutil is None or not hasattr(psutil, "sensors_battery"):
            return None
        battery = psutil.sensors_battery()
        if battery is None:
            return None
        return int(battery.percent)


__all__ = ["DetectionThread"]
