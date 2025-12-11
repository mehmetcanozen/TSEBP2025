"""
UI-facing controller for the audio process.

Responsibilities:
- Spawn/stop the multiprocessing audio worker.
- Push gain updates non-blockingly.
- Expose detection/level telemetry to the UI layer.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
from typing import Dict, Optional

from .audio_io import StreamConfig
from .audio_process import AudioProcess


class MixerController:
    def __init__(
        self,
        config: Optional[StreamConfig] = None,
        targets=None,
        backend_factory=None,
        separator_factory=None,
    ) -> None:
        self.config = config or StreamConfig()
        self.targets = targets
        self.backend_factory = backend_factory
        self.separator_factory = separator_factory
        self._gain_queue: mp.Queue = mp.Queue(maxsize=8)
        self._detection_queue: mp.Queue = mp.Queue(maxsize=16)
        self._shutdown_event = mp.Event()
        self._process: Optional[AudioProcess] = None

    # ----------------------------- lifecycle ---------------------------------
    def start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        self._process = AudioProcess(
            gain_queue=self._gain_queue,
            detection_queue=self._detection_queue,
            config=self.config,
            targets=self.targets,
            backend_factory=self.backend_factory,
            separator_factory=self.separator_factory,
            shutdown_event=self._shutdown_event,
        )
        self._process.start()

    def stop(self, timeout: float = 1.0) -> None:
        if self._process is None:
            return
        if self._process.is_alive():
            self._shutdown_event.set()
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                self._process.terminate()
        self._process = None
        self._shutdown_event = mp.Event()

    def __enter__(self) -> "MixerController":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ----------------------------- interactions ------------------------------
    def set_gains(self, speech: float, noise: float, events: float = 0.5) -> None:
        """
        Update the gain values for speech, noise, and events.

        Parameters:
            speech (float): Gain value for speech.
            noise (float): Gain value for noise.
            events (float, optional): Gain value for events. Currently, this parameter
                is a placeholder for future functionality and is not used in the audio
                processing pipeline.
        """
        gains = {"speech": float(speech), "noise": float(noise), "events": float(events)}
        # Drop stale values if queue is full
        while not self._gain_queue.empty():
            try:
                self._gain_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._gain_queue.put_nowait(gains)
        except queue.Full:
            # Non-critical: drop if UI is spamming updates
            pass

    def get_levels(self) -> Optional[Dict]:
        try:
            return self._detection_queue.get_nowait()
        except queue.Empty:
            return None

    def is_running(self) -> bool:
        return self._process is not None and self._process.is_alive()


__all__ = ["MixerController"]
