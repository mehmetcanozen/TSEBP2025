"""
Spectral masking strategies for the Semantic Noise Suppressor.

Two strategies are provided:
  * ``WienerDDMasking`` -- Ephraim-Malah Decision-Directed Wiener filter
    (the original default).
  * ``CIRMMasking`` -- bounded phase-aware masking driven by the unwanted
    estimate (stable cIRM-inspired alternative).

Both expose the same ``apply()`` / ``reset_state()`` interface so the
suppressor can swap between them at construction time.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

import numpy as np
from scipy import signal as scipy_signal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol (structural typing)
# ---------------------------------------------------------------------------

@runtime_checkable
class MaskingStrategy(Protocol):
    """Interface that every masking backend must satisfy."""

    def apply(
        self,
        mix: np.ndarray,
        unwanted: np.ndarray,
        aggressiveness: float,
        sample_rate: int,
        *,
        nperseg: int | None = None,
        dd_alpha: float | None = None,
        mask_floor: float | None = None,
        max_suppression_ratio: float | None = None,
        speech_dominance_threshold: float | None = None,
    ) -> np.ndarray: ...

    def reset_state(self) -> None: ...


# ---------------------------------------------------------------------------
# Helpers shared by both strategies
# ---------------------------------------------------------------------------

def _build_perceptual_floor(
    n_freq_bins: int,
    sample_rate: int,
    floor_min: float = 0.01,
    floor_max: float = 0.05,
    _cache: dict | None = None,
) -> np.ndarray:
    """Frequency-dependent minimum-gain floor based on A-weighting.

    Higher floor in ear-sensitive 1-5 kHz band (gentler suppression),
    lower floor below 200 Hz and above 10 kHz (more aggressive).
    """
    if _cache is None:
        _cache = _build_perceptual_floor._cache  # type: ignore[attr-defined]
    key = (n_freq_bins, sample_rate)
    if key in _cache:
        return _cache[key]

    freqs = np.linspace(0, sample_rate / 2, n_freq_bins)
    floor = np.full(n_freq_bins, floor_min, dtype=np.float64)
    f_low, f_peak, f_high = 200.0, 2500.0, 10000.0
    for i, f in enumerate(freqs):
        if f < f_low or f > f_high:
            floor[i] = floor_min
        elif f <= f_peak:
            t = (f - f_low) / (f_peak - f_low)
            floor[i] = floor_min + t * (floor_max - floor_min)
        else:
            t = (f - f_peak) / (f_high - f_peak)
            floor[i] = floor_max - t * (floor_max - floor_min)

    _cache[key] = floor
    return floor


_build_perceptual_floor._cache: dict = {}  # type: ignore[attr-defined]


def _smooth_tfr(mask: np.ndarray) -> np.ndarray:
    """Apply a light 2D smoothing pass over a time-frequency mask."""
    if mask.ndim != 2 or min(mask.shape) <= 1:
        return mask

    kernel = np.array(
        [
            [0.05, 0.10, 0.05],
            [0.10, 0.40, 0.10],
            [0.05, 0.10, 0.05],
        ],
        dtype=np.float64,
    )
    kernel /= np.sum(kernel)
    return scipy_signal.convolve2d(mask, kernel, mode="same", boundary="symm")


def _apply_unwanted_ratio_limit(
    mag_mix: np.ndarray,
    mag_unwanted: np.ndarray,
    *,
    max_suppression_ratio: float | None,
    eps: float,
) -> np.ndarray:
    """Clip an unwanted estimate so it cannot dominate the observed mixture."""
    if max_suppression_ratio is None:
        return mag_unwanted
    limit = max(0.0, float(max_suppression_ratio))
    return np.minimum(mag_unwanted, limit * (mag_mix + eps))


def _apply_floor_overrides(
    perceptual_floor: np.ndarray,
    *,
    mask_floor: float | None,
) -> np.ndarray:
    """Apply an optional scalar floor on top of the perceptual floor."""
    if mask_floor is None:
        return perceptual_floor
    return np.maximum(perceptual_floor, float(mask_floor))


def _speech_preserve_floor(
    floor_mat: np.ndarray,
    *,
    mix_power: np.ndarray,
    unwanted_power: np.ndarray,
    speech_dominance_threshold: float | None,
    max_extra_floor: float = 0.18,
) -> np.ndarray:
    """Raise the minimum gain in bins where the mixture strongly dominates the estimate."""
    if speech_dominance_threshold is None or speech_dominance_threshold <= 0:
        return floor_mat

    eps = 1e-10
    dominance = mix_power / np.maximum(unwanted_power, eps)
    preserve_bias = np.clip(
        (dominance - float(speech_dominance_threshold))
        / max(float(speech_dominance_threshold), eps),
        0.0,
        1.0,
    )
    preserve_floor = floor_mat + max_extra_floor * preserve_bias
    return np.clip(preserve_floor, floor_mat, 1.0)


# ---------------------------------------------------------------------------
# Strategy 1: Ephraim-Malah Decision-Directed Wiener filter
# ---------------------------------------------------------------------------

class WienerDDMasking:
    """Ephraim-Malah Decision-Directed spectral masking.

    Tracks a-priori SNR (xi) across time, producing a Wiener-style gain
    that suppresses transient noise without blurring.

    Pipeline:
      Layer 1 -- DD SNR tracking  -> xi / (aggressiveness + xi)
      Layer 2 -- Perceptual A-weighting floor
    """

    def __init__(
        self,
        nperseg: int = 2048,
        dd_alpha: float = 0.98,
        perceptual_floor_min: float = 0.01,
        perceptual_floor_max: float = 0.05,
    ) -> None:
        self.nperseg = nperseg
        self.dd_alpha = dd_alpha
        self.perceptual_floor_min = perceptual_floor_min
        self.perceptual_floor_max = perceptual_floor_max
        self._state: dict = {}

    def reset_state(self) -> None:
        self._state.clear()

    def apply(
        self,
        mix: np.ndarray,
        unwanted: np.ndarray,
        aggressiveness: float,
        sample_rate: int,
        *,
        nperseg: int | None = None,
        dd_alpha: float | None = None,
        mask_floor: float | None = None,
        max_suppression_ratio: float | None = None,
        speech_dominance_threshold: float | None = None,
    ) -> np.ndarray:
        nperseg = nperseg if nperseg is not None else self.nperseg
        noverlap = nperseg // 2
        alpha = dd_alpha if dd_alpha is not None else self.dd_alpha
        eps = 1e-10

        mix_2d = mix.reshape(-1, 1) if mix.ndim == 1 else mix
        unwanted_2d = unwanted.reshape(-1, 1) if unwanted.ndim == 1 else unwanted
        min_len = min(mix_2d.shape[0], unwanted_2d.shape[0])
        num_channels = mix_2d.shape[1]
        unw_channels = min(num_channels, unwanted_2d.shape[1])

        clean_channels: list[np.ndarray] = []
        for ch in range(num_channels):
            mix_ch = mix_2d[:min_len, ch].astype(np.float64)
            unw_ch = np.asarray(
                unwanted_2d[:min_len, ch % unw_channels], dtype=np.float64,
            ).ravel()[:min_len]

            _, _, Z_mix = scipy_signal.stft(
                mix_ch, nperseg=nperseg, noverlap=noverlap,
            )
            _, _, Z_unw = scipy_signal.stft(
                unw_ch, nperseg=nperseg, noverlap=noverlap,
            )

            mag_mix = np.abs(Z_mix)
            mag_unw = np.abs(Z_unw)
            phase_mix = np.angle(Z_mix)

            mag_unw = _apply_unwanted_ratio_limit(
                mag_mix,
                mag_unw,
                max_suppression_ratio=max_suppression_ratio,
                eps=eps,
            )

            mix_power = mag_mix ** 2
            unw_power = mag_unw ** 2 + eps

            n_freq_bins, n_frames = mix_power.shape
            xi = np.zeros_like(mix_power)

            if ch in self._state:
                prev_clean_power, prev_unw_power = self._state[ch]
                if prev_clean_power.shape[0] != n_freq_bins:
                    prev_clean_power = np.zeros(n_freq_bins)
                    prev_unw_power = np.ones(n_freq_bins) * eps
            else:
                prev_clean_power = np.zeros(n_freq_bins)
                prev_unw_power = np.ones(n_freq_bins) * eps

            for t in range(n_frames):
                gamma = mix_power[:, t] / unw_power[:, t]
                gamma_minus_1 = np.maximum(gamma - 1.0, 0.0)
                snr_prior = prev_clean_power / prev_unw_power
                xi[:, t] = alpha * snr_prior + (1.0 - alpha) * gamma_minus_1
                gain_t = xi[:, t] / (aggressiveness + xi[:, t])
                prev_clean_power = (gain_t ** 2) * mix_power[:, t]
                prev_unw_power = unw_power[:, t]

            self._state[ch] = (prev_clean_power, prev_unw_power)

            gain = xi / (aggressiveness + xi)

            perceptual_floor = _build_perceptual_floor(
                n_freq_bins, sample_rate,
                self.perceptual_floor_min, self.perceptual_floor_max,
            )
            perceptual_floor = _apply_floor_overrides(
                perceptual_floor,
                mask_floor=mask_floor,
            )
            gain = np.maximum(gain, perceptual_floor[:, np.newaxis])
            gain = np.maximum(
                gain,
                _speech_preserve_floor(
                    perceptual_floor[:, np.newaxis],
                    mix_power=mix_power,
                    unwanted_power=unw_power,
                    speech_dominance_threshold=speech_dominance_threshold,
                ),
            )

            Z_clean = (gain * mag_mix) * np.exp(1j * phase_mix)

            _, clean_ch = scipy_signal.istft(
                Z_clean, nperseg=nperseg, noverlap=noverlap,
            )
            clean_ch = clean_ch[:min_len]
            if len(clean_ch) < min_len:
                clean_ch = np.pad(clean_ch, (0, min_len - len(clean_ch)),
                                  mode="constant")
            clean_channels.append(clean_ch)

        clean_audio = np.column_stack(clean_channels)
        if mix.ndim == 1:
            clean_audio = clean_audio.flatten()
        return clean_audio.astype(mix.dtype)


# ---------------------------------------------------------------------------
# Strategy 2: Complex Ideal Ratio Mask (cIRM)
# ---------------------------------------------------------------------------

class CIRMMasking:
    """Bounded phase-aware mask derived from mix and unwanted estimates.

    The unwanted estimate is treated as a guide signal to build a stable,
    bounded soft mask. This keeps the phase-aware intent of cIRM-style
    masking, but avoids the raw complex subtraction that tends to create
    musical-noise / burst artifacts when the separator estimate is noisy.
    """

    def __init__(
        self,
        nperseg: int = 2048,
        perceptual_floor_min: float = 0.01,
        perceptual_floor_max: float = 0.05,
        soft_blend: bool = True,
        power_exponent: float = 2.0,
        phase_mix_factor: float = 0.35,
        max_phase_shift: float = np.pi / 3.0,
        unstable_gain_limit: float = 1.25,
    ) -> None:
        self.nperseg = nperseg
        self.perceptual_floor_min = perceptual_floor_min
        self.perceptual_floor_max = perceptual_floor_max
        self.soft_blend = soft_blend
        self.power_exponent = power_exponent
        self.phase_mix_factor = phase_mix_factor
        self.max_phase_shift = max_phase_shift
        self.unstable_gain_limit = unstable_gain_limit

    def reset_state(self) -> None:
        pass  # cIRM is stateless across chunks

    def apply(
        self,
        mix: np.ndarray,
        unwanted: np.ndarray,
        aggressiveness: float,
        sample_rate: int,
        *,
        nperseg: int | None = None,
        dd_alpha: float | None = None,
        mask_floor: float | None = None,
        max_suppression_ratio: float | None = None,
        speech_dominance_threshold: float | None = None,
    ) -> np.ndarray:
        nperseg = nperseg if nperseg is not None else self.nperseg
        noverlap = nperseg // 2
        eps = 1e-10

        mix_2d = mix.reshape(-1, 1) if mix.ndim == 1 else mix
        unwanted_2d = unwanted.reshape(-1, 1) if unwanted.ndim == 1 else unwanted
        min_len = min(mix_2d.shape[0], unwanted_2d.shape[0])
        num_channels = mix_2d.shape[1]
        unw_channels = min(num_channels, unwanted_2d.shape[1])

        clean_channels: list[np.ndarray] = []
        for ch in range(num_channels):
            mix_ch = mix_2d[:min_len, ch].astype(np.float64)
            unw_ch = np.asarray(
                unwanted_2d[:min_len, ch % unw_channels], dtype=np.float64,
            ).ravel()[:min_len]

            _, _, Z_mix = scipy_signal.stft(
                mix_ch, nperseg=nperseg, noverlap=noverlap,
            )
            _, _, Z_unw = scipy_signal.stft(
                unw_ch, nperseg=nperseg, noverlap=noverlap,
            )

            effective_agg = aggressiveness
            if self.soft_blend:
                mean_unw = np.mean(np.abs(Z_unw))
                mean_mix = np.mean(np.abs(Z_mix)) + eps
                confidence = float(np.clip(mean_unw / mean_mix, 0.15, 1.0))
                effective_agg = aggressiveness * confidence

            Z_noise = effective_agg * Z_unw
            Z_clean_est = Z_mix - Z_noise

            mag_mix = np.abs(Z_mix)
            mag_noise = np.abs(Z_noise)
            mag_clean_est = np.abs(Z_clean_est)
            n_freq_bins = mag_mix.shape[0]

            mag_noise = _apply_unwanted_ratio_limit(
                mag_mix,
                mag_noise,
                max_suppression_ratio=max_suppression_ratio,
                eps=eps,
            )

            mix_power = mag_mix ** self.power_exponent
            noise_power = mag_noise ** self.power_exponent
            clean_power = np.maximum(mag_clean_est, eps) ** self.power_exponent

            # Generalized Wiener-style soft gain from clean/noise estimates.
            wiener_gain = clean_power / (clean_power + noise_power + eps)

            # Stable bounded ratio gain, derived from the complex clean estimate.
            raw_ratio = Z_clean_est / (Z_mix + eps)
            raw_ratio_mag = np.abs(raw_ratio)
            ratio_gain = np.clip(raw_ratio_mag, 0.0, 1.0)

            perceptual_floor = _build_perceptual_floor(
                n_freq_bins, sample_rate,
                self.perceptual_floor_min, self.perceptual_floor_max,
            )
            perceptual_floor = _apply_floor_overrides(
                perceptual_floor,
                mask_floor=mask_floor,
            )
            floor_mat = perceptual_floor[:, np.newaxis]

            stable_mag_floor = max(1e-7, float(np.mean(mag_mix)) * 1e-3)
            stable_bins = (
                np.isfinite(raw_ratio_mag)
                & np.isfinite(np.real(raw_ratio))
                & np.isfinite(np.imag(raw_ratio))
                & (mag_mix > stable_mag_floor)
                & (raw_ratio_mag <= self.unstable_gain_limit)
            )

            gain = np.where(
                stable_bins,
                0.65 * wiener_gain + 0.35 * ratio_gain,
                wiener_gain,
            )
            gain = np.clip(gain, floor_mat, 1.0)
            gain = _smooth_tfr(gain)
            gain = np.clip(gain, floor_mat, 1.0)
            gain = np.maximum(
                gain,
                _speech_preserve_floor(
                    floor_mat,
                    mix_power=mix_power,
                    unwanted_power=noise_power,
                    speech_dominance_threshold=speech_dominance_threshold,
                    max_extra_floor=0.15,
                ),
            )

            phase_mix = np.angle(Z_mix)
            phase_delta = np.angle(raw_ratio)
            phase_delta = np.clip(phase_delta, -self.max_phase_shift, self.max_phase_shift)

            phase_strength = np.where(
                stable_bins,
                np.clip(
                    (gain - floor_mat) / np.maximum(1.0 - floor_mat, eps),
                    0.0,
                    1.0,
                ),
                0.0,
            )
            phase_strength = _smooth_tfr(phase_strength) * self.phase_mix_factor
            phase_strength = np.clip(phase_strength, 0.0, self.phase_mix_factor)
            phase_correction = phase_delta * phase_strength

            Z_clean = (gain * mag_mix) * np.exp(1j * (phase_mix + phase_correction))

            _, clean_ch = scipy_signal.istft(
                Z_clean, nperseg=nperseg, noverlap=noverlap,
            )
            clean_ch = clean_ch[:min_len]
            if len(clean_ch) < min_len:
                clean_ch = np.pad(clean_ch, (0, min_len - len(clean_ch)),
                                  mode="constant")
            clean_channels.append(clean_ch)

        clean_audio = np.column_stack(clean_channels)
        if mix.ndim == 1:
            clean_audio = clean_audio.flatten()
        return clean_audio.astype(mix.dtype)


__all__ = ["CIRMMasking", "MaskingStrategy", "WienerDDMasking"]
