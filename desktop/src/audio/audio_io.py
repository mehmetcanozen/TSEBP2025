"""
Desktop audio I/O helpers.

Provides:
- `set_high_priority` to elevate the process for stable low-latency audio.
- A lightweight pluggable backend interface with a PyAudio implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import psutil

try:
    import pyaudio as _pyaudio
except ImportError:  # pragma: no cover - optional during tests
    _pyaudio = None


def set_high_priority() -> None:
    """
    Elevate OS scheduling priority for the current process.
    Windows: REALTIME_PRIORITY_CLASS
    POSIX: nice(-10)
    """
    proc = psutil.Process()
    if psutil.WINDOWS:
        proc.nice(psutil.REALTIME_PRIORITY_CLASS)
    else:
        proc.nice(-10)


@dataclass
class StreamConfig:
    """Audio stream configuration."""

    sample_rate: int = 44_100
    channels: int = 1
    frames_per_buffer: int = 512
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None


class AudioBackend:
    """Interface for audio backends."""

    def start(self) -> None:
        raise NotImplementedError

    def read(self) -> np.ndarray:
        raise NotImplementedError

    def write(self, data: np.ndarray) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class PyAudioBackend(AudioBackend):
    """PyAudio implementation with float32 I/O."""

    def __init__(self, config: StreamConfig) -> None:
        if _pyaudio is None:
            raise ImportError(
                "PyAudio is required for the desktop audio backend. "
                "Install with `pip install pyaudio`."
            )
        self.config = config
        self._pa = _pyaudio.PyAudio()
        self._input_stream = None
        self._output_stream = None

    def start(self) -> None:
        fmt = _pyaudio.paFloat32
        self._input_stream = self._pa.open(
            format=fmt,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            input=True,
            frames_per_buffer=self.config.frames_per_buffer,
            input_device_index=self.config.input_device_index,
            stream_callback=None,
        )
        self._output_stream = self._pa.open(
            format=fmt,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            output=True,
            frames_per_buffer=self.config.frames_per_buffer,
            output_device_index=self.config.output_device_index,
            stream_callback=None,
        )

    def read(self) -> np.ndarray:
        if self._input_stream is None:
            raise RuntimeError("Input stream not started.")
        data = self._input_stream.read(
            self.config.frames_per_buffer, exception_on_overflow=False
        )
        array = np.frombuffer(data, dtype=np.float32)
        if self.config.channels > 1:
            array = array.reshape(-1, self.config.channels)
        return array

    def write(self, data: np.ndarray) -> None:
        if self._output_stream is None:
            raise RuntimeError("Output stream not started.")
        float_data = np.asarray(data, dtype=np.float32)
        if float_data.ndim == 2:
            float_data = float_data.reshape(-1)
        self._output_stream.write(float_data.tobytes())

    def close(self) -> None:
        if self._input_stream is not None:
            self._input_stream.stop_stream()
            self._input_stream.close()
            self._input_stream = None
        if self._output_stream is not None:
            self._output_stream.stop_stream()
            self._output_stream.close()
            self._output_stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None


__all__ = ["StreamConfig", "AudioBackend", "PyAudioBackend", "set_high_priority"]
