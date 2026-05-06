"""Audio runtime components used by desktop integration."""

from .audio_io import AudioBackend, PyAudioBackend, StreamConfig, set_high_priority
from .gain_smoother import GainSmoother
from .latency_profiler import LatencyProfiler
from .ring_buffer import RingBuffer


def __getattr__(name: str):
    if name == "AudioProcess":
        from .audio_process import AudioProcess

        return AudioProcess
    if name == "MixerController":
        from .mixer_controller import MixerController

        return MixerController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AudioBackend",
    "AudioProcess",
    "GainSmoother",
    "LatencyProfiler",
    "MixerController",
    "PyAudioBackend",
    "RingBuffer",
    "StreamConfig",
    "set_high_priority",
]
