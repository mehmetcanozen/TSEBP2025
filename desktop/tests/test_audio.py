import time
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from audio.audio_io import StreamConfig
from audio.gain_smoother import GainSmoother
from audio.mixer_controller import MixerController
from audio.ring_buffer import RingBuffer


class FakeBackend:
    def __init__(self, config: StreamConfig) -> None:
        self.config = config
        self.started = False
        self.writes = 0

    def start(self) -> None:
        self.started = True

    def read(self) -> np.ndarray:
        frames = self.config.frames_per_buffer * self.config.channels
        return np.zeros(frames, dtype=np.float32)

    def write(self, data: np.ndarray) -> None:
        self.writes += 1

    def close(self) -> None:
        self.started = False


class FakeSeparator:
    def __call__(self):
        return self

    def separate(self, audio, sample_rate, targets=None):
        return np.asarray(audio, dtype=np.float32)


def make_fake_backend(cfg: StreamConfig) -> FakeBackend:
    return FakeBackend(cfg)


def make_separator() -> FakeSeparator:
    return FakeSeparator()


def test_ring_buffer_read_write():
    buf = RingBuffer(capacity=4)
    buf.write(np.array([1, 2], dtype=np.float32))
    assert buf.available() == 2
    out = buf.read(2)
    assert out.tolist() == [1.0, 2.0]
    assert buf.read(1) is None


def test_gain_smoother_noise_floor():
    smoother = GainSmoother(smoothing=0.5, noise_floor=0.1)
    gains = smoother.smooth({"noise": 0.0})
    assert gains["noise"] >= 0.1


def test_mixer_controller_start_stop_without_audio_hardware():
    config = StreamConfig(sample_rate=16_000, frames_per_buffer=32, channels=1)
    controller = MixerController(
        config=config,
        backend_factory=make_fake_backend,
        separator_factory=make_separator,
    )
    controller.start()
    time.sleep(0.2)
    controller.set_gains(1.0, 0.1, 0.5)
    time.sleep(0.2)
    controller.stop()
    assert not controller.is_running()
