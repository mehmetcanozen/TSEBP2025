"""Tests for WienerDDMasking and CIRMMasking strategy classes."""

from __future__ import annotations

import numpy as np
import pytest

from ai.ai_runtime.suppression.masking import CIRMMasking, WienerDDMasking


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tone_plus_noise(sr: int = 44100, duration: float = 1.0,
                     tone_freq: float = 1000.0, tone_amp: float = 0.5,
                     noise_amp: float = 0.3, seed: int = 42):
    """Create a mix = broadband noise + narrowband tone, with tone as unwanted."""
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    rng = np.random.RandomState(seed)
    noise = rng.randn(n).astype(np.float32) * noise_amp
    tone = (tone_amp * np.sin(2 * np.pi * tone_freq * t)).astype(np.float32)
    mix = noise + tone
    return mix, tone


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)))


# ---------------------------------------------------------------------------
# WienerDDMasking
# ---------------------------------------------------------------------------

class TestWienerDDMasking:

    def test_output_shape_mono(self):
        masking = WienerDDMasking()
        mix = np.random.randn(44100).astype(np.float32) * 0.3
        unwanted = mix * 0.5
        out = masking.apply(mix, unwanted, aggressiveness=1.0, sample_rate=44100)
        assert out.shape == mix.shape

    def test_output_shape_stereo(self):
        masking = WienerDDMasking()
        mix = np.random.randn(44100, 2).astype(np.float32) * 0.3
        unwanted = mix * 0.5
        out = masking.apply(mix, unwanted, aggressiveness=1.0, sample_rate=44100)
        assert out.shape == mix.shape

    def test_tone_is_suppressed(self):
        masking = WienerDDMasking()
        mix, tone = _tone_plus_noise()
        out = masking.apply(mix, tone, aggressiveness=1.0, sample_rate=44100)
        from scipy.signal import welch
        freqs, psd_mix = welch(mix, fs=44100, nperseg=2048)
        _, psd_out = welch(out, fs=44100, nperseg=2048)
        idx_1k = np.argmin(np.abs(freqs - 1000))
        assert psd_out[idx_1k] < psd_mix[idx_1k] * 0.6

    def test_state_persistence_across_chunks(self):
        masking = WienerDDMasking()
        chunk = np.random.randn(44100).astype(np.float32) * 0.3
        unw = chunk * 0.6
        out1 = masking.apply(chunk, unw, aggressiveness=1.0, sample_rate=44100)
        out2 = masking.apply(chunk, unw, aggressiveness=1.0, sample_rate=44100)
        # Second chunk should benefit from state — output should be stable
        rms1 = _rms(out1[-4410:])
        rms2 = _rms(out2[:4410])
        if rms1 > 1e-8 and rms2 > 1e-8:
            ratio = max(rms1, rms2) / min(rms1, rms2)
            assert ratio < 3.0

    def test_reset_state(self):
        masking = WienerDDMasking()
        chunk = np.random.randn(44100).astype(np.float32) * 0.3
        masking.apply(chunk, chunk * 0.5, aggressiveness=1.0, sample_rate=44100)
        assert masking._state  # State should exist
        masking.reset_state()
        assert not masking._state

    def test_mask_floor_softens_over_suppression(self):
        masking_default = WienerDDMasking()
        masking_soft = WienerDDMasking()
        mix = np.random.randn(22050).astype(np.float32) * 0.15
        unwanted = mix * 0.9

        out_default = masking_default.apply(
            mix, unwanted, aggressiveness=1.4, sample_rate=44100,
        )
        out_soft = masking_soft.apply(
            mix, unwanted, aggressiveness=1.4, sample_rate=44100, mask_floor=0.12,
        )

        assert _rms(mix - out_soft) < _rms(mix - out_default)

    def test_short_tail_chunk_uses_valid_stft_window(self):
        masking = WienerDDMasking(nperseg=2048)
        mix = np.random.randn(1297).astype(np.float32) * 0.1
        unwanted = mix * 0.4
        out = masking.apply(mix, unwanted, aggressiveness=1.0, sample_rate=24000)
        assert out.shape == mix.shape
        assert np.isfinite(out).all()


# ---------------------------------------------------------------------------
# CIRMMasking
# ---------------------------------------------------------------------------

class TestCIRMMasking:

    def test_output_shape_mono(self):
        masking = CIRMMasking()
        mix = np.random.randn(44100).astype(np.float32) * 0.3
        unwanted = mix * 0.5
        out = masking.apply(mix, unwanted, aggressiveness=1.0, sample_rate=44100)
        assert out.shape == mix.shape

    def test_output_shape_stereo(self):
        masking = CIRMMasking()
        mix = np.random.randn(44100, 2).astype(np.float32) * 0.3
        unwanted = mix * 0.5
        out = masking.apply(mix, unwanted, aggressiveness=1.0, sample_rate=44100)
        assert out.shape == mix.shape

    def test_tone_is_suppressed(self):
        masking = CIRMMasking(soft_blend=False, perceptual_floor_min=0.001,
                              perceptual_floor_max=0.005)
        mix, tone = _tone_plus_noise()
        out = masking.apply(mix, tone, aggressiveness=1.0, sample_rate=44100)
        from scipy.signal import welch
        freqs, psd_mix = welch(mix, fs=44100, nperseg=2048)
        _, psd_out = welch(out, fs=44100, nperseg=2048)
        idx_1k = np.argmin(np.abs(freqs - 1000))
        assert psd_out[idx_1k] < psd_mix[idx_1k] * 0.6

    def test_stateless_reset(self):
        masking = CIRMMasking()
        masking.reset_state()  # Should not raise

    def test_aggressiveness_scaling(self):
        """Higher aggressiveness should remove more of the unwanted signal."""
        masking_lo = CIRMMasking(soft_blend=False, perceptual_floor_min=0.001,
                                 perceptual_floor_max=0.005)
        masking_hi = CIRMMasking(soft_blend=False, perceptual_floor_min=0.001,
                                 perceptual_floor_max=0.005)
        mix, tone = _tone_plus_noise(tone_amp=0.8, noise_amp=0.1)
        out_lo = masking_lo.apply(mix, tone, aggressiveness=0.3, sample_rate=44100)
        out_hi = masking_hi.apply(mix, tone, aggressiveness=1.0, sample_rate=44100)
        from scipy.signal import welch
        freqs, _ = welch(mix, fs=44100, nperseg=2048)
        _, psd_lo = welch(out_lo, fs=44100, nperseg=2048)
        _, psd_hi = welch(out_hi, fs=44100, nperseg=2048)
        idx_1k = np.argmin(np.abs(freqs - 1000))
        assert psd_hi[idx_1k] < psd_lo[idx_1k]

    def test_soft_blend_reduces_artifacts(self):
        """Soft blend should attenuate subtraction when unwanted is weak."""
        masking_hard = CIRMMasking(soft_blend=False)
        masking_soft = CIRMMasking(soft_blend=True)
        rng = np.random.RandomState(0)
        mix = rng.randn(44100).astype(np.float32) * 0.5
        # Very weak unwanted signal
        unwanted = mix * 0.05
        out_hard = masking_hard.apply(mix, unwanted, aggressiveness=1.0,
                                      sample_rate=44100)
        out_soft = masking_soft.apply(mix, unwanted, aggressiveness=1.0,
                                      sample_rate=44100)
        # Soft should modify less than hard
        diff_hard = _rms(mix - out_hard)
        diff_soft = _rms(mix - out_soft)
        assert diff_soft <= diff_hard + 1e-6

    def test_phase_coherence(self):
        """cIRM preserves phase from complex subtraction (not from mix)."""
        from scipy.signal import stft
        masking = CIRMMasking(soft_blend=False, phase_mix_factor=1.0, max_phase_shift=np.pi / 2.0)
        sr = 44100
        mix, tone = _tone_plus_noise(sr=sr)
        out = masking.apply(mix, tone, aggressiveness=1.0, sample_rate=sr)

        _, _, Z_mix = stft(mix, nperseg=2048, noverlap=1024)
        _, _, Z_out = stft(out, nperseg=2048, noverlap=1024)
        _, _, Z_expected = stft(mix - tone, nperseg=2048, noverlap=1024)

        # Phase of output should be closer to expected than to mix
        phase_out = np.angle(Z_out)
        phase_mix = np.angle(Z_mix)
        phase_exp = np.angle(Z_expected)

        err_vs_expected = np.mean(np.abs(phase_out - phase_exp))
        err_vs_mix = np.mean(np.abs(phase_out - phase_mix))
        assert err_vs_expected < err_vs_mix

    def test_max_suppression_ratio_limits_cirm_damage(self):
        masking_hard = CIRMMasking(soft_blend=False)
        masking_limited = CIRMMasking(soft_blend=False)
        mix = np.random.randn(22050).astype(np.float32) * 0.2
        unwanted = mix * 2.0

        out_hard = masking_hard.apply(
            mix, unwanted, aggressiveness=1.6, sample_rate=44100,
        )
        out_limited = masking_limited.apply(
            mix,
            unwanted,
            aggressiveness=1.6,
            sample_rate=44100,
            max_suppression_ratio=0.6,
        )

        assert _rms(mix - out_limited) < _rms(mix - out_hard)

    def test_short_tail_chunk_uses_valid_stft_window(self):
        masking = CIRMMasking(nperseg=2048)
        mix = np.random.randn(1297).astype(np.float32) * 0.1
        unwanted = mix * 0.4
        out = masking.apply(mix, unwanted, aggressiveness=1.0, sample_rate=24000)
        assert out.shape == mix.shape
        assert np.isfinite(out).all()


# ---------------------------------------------------------------------------
# Cross-strategy comparison
# ---------------------------------------------------------------------------

class TestCrossStrategy:

    def test_both_reduce_unwanted_energy(self):
        mix, tone = _tone_plus_noise()
        for cls in (WienerDDMasking, CIRMMasking):
            masking = cls()
            out = masking.apply(mix, tone, aggressiveness=1.0, sample_rate=44100)
            assert _rms(out) < _rms(mix)
