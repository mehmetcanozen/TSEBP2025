"""
Multiprocessing audio process that isolates I/O and inference from the UI.

Architecture:
- Runs in its own process to bypass the GIL.
- Uses ring buffers to decouple fast audio callbacks from slower inference.
- Applies gain smoothing with a soft noise floor to avoid zipper noise.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
from typing import Callable, Dict, Optional

import numpy as np

from .audio_io import PyAudioBackend, StreamConfig, set_high_priority
from .gain_smoother import GainSmoother
from .ring_buffer import RingBuffer
from inference.waveformer_wrapper import WaveformerSeparator


class AudioProcess(mp.Process):
    """Dedicated audio process for low-latency streaming."""

    def __init__(
        self,
        gain_queue: mp.Queue,
        detection_queue: mp.Queue,
        config: Optional[StreamConfig] = None,
        targets=None,
        backend_factory: Optional[Callable[[StreamConfig], PyAudioBackend]] = None,
        separator_factory: Optional[Callable[[], WaveformerSeparator]] = None,
        shutdown_event: Optional[mp.Event] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.gain_queue = gain_queue
        self.detection_queue = detection_queue
        self.config = config or StreamConfig()
        self.targets = targets
        self.backend_factory = backend_factory or (lambda cfg: PyAudioBackend(cfg))
        self.separator_factory = separator_factory or WaveformerSeparator
        self.shutdown_event = shutdown_event or mp.Event()

    def stop(self) -> None:
        self.shutdown_event.set()

    # ----------------------------- internal helpers --------------------------
    def _drain_gains(self, smoother: GainSmoother) -> Dict[str, float]:
        gains = None
        while True:
            try:
                gains = self.gain_queue.get_nowait()
            except queue.Empty:
                break
        if gains is None:
            gains = smoother.current
        return smoother.smooth(gains)

    # ----------------------------- process entry -----------------------------
    def run(self) -> None:
        set_high_priority()

        backend = self.backend_factory(self.config)
        backend.start()

        # Ring buffers sized for ~300ms of audio
        capacity = int(self.config.sample_rate * self.config.channels * 0.3)
        input_buffer = RingBuffer(capacity=capacity)
        output_buffer = RingBuffer(capacity=capacity)

        smoother = GainSmoother()
        separator = self.separator_factory()

        stop_event = self.shutdown_event
        capture_thread = threading.Thread(
            target=self._capture_loop, args=(backend, input_buffer, stop_event), daemon=True
        )
        playback_thread = threading.Thread(
            target=self._playback_loop,
            args=(backend, output_buffer, stop_event),
            daemon=True,
        )
        capture_thread.start()
        playback_thread.start()

        self._inference_loop(
            input_buffer=input_buffer,
            output_buffer=output_buffer,
            separator=separator,
            smoother=smoother,
            stop_event=stop_event,
        )

        capture_thread.join(timeout=1.0)
        playback_thread.join(timeout=1.0)
        backend.close()

    # ----------------------------- capture/playback --------------------------
    def _capture_loop(
        self, backend: PyAudioBackend, input_buffer: RingBuffer, stop_event: mp.Event
    ) -> None:
        while not stop_event.is_set():
            data = backend.read()
            input_buffer.write(data)

    def _playback_loop(
        self, backend: PyAudioBackend, output_buffer: RingBuffer, stop_event: mp.Event
    ) -> None:
        frame_samples = self.config.frames_per_buffer * self.config.channels
        silence = np.zeros(frame_samples, dtype=np.float32)
        while not stop_event.is_set():
            chunk = output_buffer.read(frame_samples)
            if chunk is None:
                backend.write(silence)
            else:
                backend.write(chunk)

    # ----------------------------- inference loop ---------------------------
    def _inference_loop(
        self,
        input_buffer: RingBuffer,
        output_buffer: RingBuffer,
        separator: WaveformerSeparator,
        smoother: GainSmoother,
        stop_event: mp.Event,
    ) -> None:
        frame_samples = self.config.frames_per_buffer * self.config.channels
        sr = self.config.sample_rate

        while not stop_event.is_set():
            # Apply latest gains
            gains = self._drain_gains(smoother)

            # Pull audio; sleep briefly if underrun
            chunk = input_buffer.read(frame_samples)
            if chunk is None:
                time.sleep(0.001)
                continue

            chunk = chunk.reshape(-1, self.config.channels)

            # Run separation
            separated = separator.separate(chunk, sr, targets=self.targets)

            # Simple residual to approximate noise stem
            residual = chunk - separated[:chunk.shape[0]]

            mixed = (separated * gains.get("speech", 1.0)) + (
                residual * gains.get("noise", smoother.noise_floor)
            )

            # Write to output ring buffer
            output_buffer.write(mixed)

            # Push level info for UI (RMS)
            rms = float(np.sqrt(np.mean(np.square(chunk))))
            try:
                self.detection_queue.put_nowait({"rms": rms, "gains": gains})
            except queue.Full:
                pass

