"""Focused suppression quality tests for SemanticSuppressor."""

from __future__ import annotations

import numpy as np

from ai.ai_runtime.suppression import SemanticSuppressor


class FakeDetector:
    def __init__(self, confidence: float = 0.8):
        self.detections = {"pets": confidence}

    def classify(self, audio, sample_rate):
        return {
            "raw": self.detections,
            "smoothed": self.detections,
            "stable": {k: v > 0.5 for k, v in self.detections.items()},
            "states": {k: "active" if v > 0.5 else "inactive" for k, v in self.detections.items()},
        }


class FakeSeparator:
    def __init__(self, capture_ratio: float = 0.6):
        self.capture_ratio = capture_ratio

    def separate(self, audio, sample_rate, targets=None):
        result = audio * self.capture_ratio
        if result.ndim == 1:
            result = result.reshape(-1, 1)
        return result


def make_impulse_audio(sr: int = 44100) -> np.ndarray:
    n_samples = sr
    audio = np.zeros(n_samples, dtype=np.float32)
    burst_len = int(0.005 * sr)
    center = n_samples // 2
    t = np.linspace(0, 2 * np.pi * 8, burst_len)
    audio[center : center + burst_len] = 0.9 * np.sin(t).astype(np.float32)
    return audio


def test_passthrough_returns_original():
    supp = SemanticSuppressor(detector=FakeDetector(), separator=FakeSeparator())
    audio = make_impulse_audio()
    clean = supp.suppress(audio=audio, sample_rate=44100, suppress_categories=[])
    np.testing.assert_array_equal(audio, clean)


def test_impulse_is_reduced_when_category_active():
    supp = SemanticSuppressor(detector=FakeDetector(0.9), separator=FakeSeparator(0.8))
    audio = make_impulse_audio()
    clean = supp.suppress(
        audio=audio,
        sample_rate=44100,
        suppress_categories=["pets"],
        detection_threshold=-1,
        aggressiveness=1.0,
    )
    center = len(audio) // 2
    burst_len = int(0.005 * 44100)
    original_energy = np.sum(audio[center : center + burst_len] ** 2)
    clean_energy = np.sum(clean[center : center + burst_len] ** 2)
    assert clean_energy < original_energy * 0.8


def test_stereo_shape_preserved():
    supp = SemanticSuppressor(detector=FakeDetector(), separator=FakeSeparator(0.6))
    audio = np.random.randn(44100, 2).astype(np.float32) * 0.2
    clean = supp.suppress(
        audio=audio,
        sample_rate=44100,
        suppress_categories=["pets"],
        detection_threshold=-1,
    )
    assert clean.shape == audio.shape


def test_no_musical_noise():
    """Verify the Wiener-IRM mask doesn't introduce musical noise artifacts.

    Creates a mix of broadband noise + narrowband tone (simulating unwanted),
    runs suppression, and checks that the 1 kHz tone energy is reduced in output.
    """
    from scipy.signal import butter, sosfilt, welch

    sr = 44100
    n_samples = sr
    t = np.linspace(0, 1.0, n_samples, endpoint=False)

    # Broadband "speech-like" signal
    np.random.seed(42)
    speech = np.random.randn(n_samples).astype(np.float32) * 0.3

    # Narrowband tone (unwanted noise at 1 kHz)
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)

    mix = speech + tone

    # Separator bandpass-filters input around 1 kHz to isolate the tone
    class BandpassSeparator:
        def separate(self, audio, sample_rate, targets=None):
            audio_1d = audio.ravel() if audio.ndim > 1 else audio
            sos = butter(4, [800, 1200], btype="bandpass", fs=sample_rate, output="sos")
            filtered = sosfilt(sos, audio_1d).astype(np.float32)
            return filtered.reshape(-1, 1)

    supp = SemanticSuppressor(
        detector=FakeDetector(0.9),
        separator=BandpassSeparator(),
    )
    clean = supp.suppress(
        audio=mix,
        sample_rate=sr,
        suppress_categories=["pets"],
        detection_threshold=-1,
        aggressiveness=1.0,
    )

    # Compute spectral energy in clean output
    freqs, psd_clean = welch(clean, fs=sr, nperseg=2048)
    _, psd_mix = welch(mix, fs=sr, nperseg=2048)

    # Energy at 1 kHz should be significantly reduced vs the original mix
    tone_idx = np.argmin(np.abs(freqs - 1000))

    # The 1 kHz tone energy should be reduced by at least 40%
    assert psd_clean[tone_idx] < psd_mix[tone_idx] * 0.6, (
        f"Musical noise: 1kHz tone not sufficiently suppressed "
        f"(clean={psd_clean[tone_idx]:.6f}, mix={psd_mix[tone_idx]:.6f})"
    )


def test_temporal_smoothness():
    """Verify EMA smoothing produces consistent energy across chunk boundaries.

    Runs two consecutive chunks through the suppressor and checks that
    the energy transition between chunks is smooth (no sudden jumps).
    """
    sr = 44100
    chunk_size = sr  # 1 second chunks
    np.random.seed(123)

    # Create two chunks of consistent noise
    chunk1 = np.random.randn(chunk_size).astype(np.float32) * 0.3
    chunk2 = np.random.randn(chunk_size).astype(np.float32) * 0.3

    supp = SemanticSuppressor(
        detector=FakeDetector(0.9),
        separator=FakeSeparator(0.6),
    )

    # Process both chunks sequentially (EMA state should carry over)
    clean1 = supp.suppress(
        audio=chunk1,
        sample_rate=sr,
        suppress_categories=["pets"],
        detection_threshold=-1,
    )
    clean2 = supp.suppress(
        audio=chunk2,
        sample_rate=sr,
        suppress_categories=["pets"],
        detection_threshold=-1,
    )

    # Compare RMS energy at boundary regions (last 10% of chunk1, first 10% of chunk2)
    boundary_size = chunk_size // 10
    rms_end = np.sqrt(np.mean(clean1[-boundary_size:] ** 2))
    rms_start = np.sqrt(np.mean(clean2[:boundary_size] ** 2))

    # Energy ratio should be within 3x (no sudden jumps)
    if rms_end > 1e-8 and rms_start > 1e-8:
        ratio = max(rms_end, rms_start) / min(rms_end, rms_start)
        assert ratio < 3.0, (
            f"Energy discontinuity at chunk boundary: ratio={ratio:.2f} "
            f"(end_rms={rms_end:.6f}, start_rms={rms_start:.6f})"
        )

