"""
Semantic Noise Suppressor - Core Intelligence.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import yaml
from scipy import signal as scipy_signal

from ai.ai_runtime.detection import SemanticDetective
from ai.ai_runtime.enhancement import SpeechEnhancer
from ai.ai_runtime.separation import UniversalSeparator, WaveformerSeparator
from ai.ai_runtime.utils.paths import get_config_path

logger = logging.getLogger(__name__)

try:
    from ai.ai_runtime.profiles.profiler import get_profiler

    profiler = get_profiler()
except ImportError:
    profiler = None
    logger.warning("Profiler not available, performance tracking disabled")

DEFAULT_MAPPING_PATH = get_config_path("yamnet_to_waveformer.yaml")


class SemanticSuppressor:
    """Intelligent noise suppressor using semantic understanding."""

    def __init__(
        self,
        mapping_path: Path = DEFAULT_MAPPING_PATH,
        detector: Optional[SemanticDetective] = None,
        separator: Optional[WaveformerSeparator] = None,
        enhancer: Optional[SpeechEnhancer] = None,
        universal: Optional[UniversalSeparator] = None,
    ) -> None:
        self.mapping_path = mapping_path
        self.category_map = self._load_mapping(mapping_path)
        self._detector = detector
        self._separator = separator
        self._enhancer = enhancer
        self._universal = universal
        self._overlap_save_tail = None

        # Separation params
        self.weak_stem_boost_cap = 4.5  # Higher cap for under-extracted stems
        self.under_extract_scale = 2.0  # Scale unwanted when under-extracted (ratio low)
        # Adaptive spectral masking params
        self.spectral_nperseg = 2048
        self.perceptual_floor_min = 0.01  # Floor in ear-insensitive bands (<200Hz, >10kHz)
        self.perceptual_floor_max = 0.05  # Floor in ear-sensitive bands (1-5 kHz)
        self.dd_alpha = 0.98              # Decision-Directed tracking factor (Ephraim-Malah)
        self._decision_directed_state: dict = {} # Per-channel tracking state (clean_power, unw_power)
        self._perceptual_floor_cache: dict = {}  # Cache keyed by (nperseg, sample_rate)

    @property
    def enhancer(self) -> SpeechEnhancer:
        if self._enhancer is None:
            logger.info("Initializing SpeechEnhancer...")
            self._enhancer = SpeechEnhancer()
        return self._enhancer

    @property
    def detector(self) -> SemanticDetective:
        if self._detector is None:
            logger.info("Initializing SemanticDetective...")
            self._detector = SemanticDetective()
        return self._detector

    @property
    def separator(self) -> WaveformerSeparator:
        if self._separator is None:
            logger.info("Initializing WaveformerSeparator...")
            self._separator = WaveformerSeparator()
        return self._separator

    @property
    def universal_separator(self) -> UniversalSeparator:
        if self._universal is None:
            logger.info("Initializing UniversalSeparator (AudioSep)...")
            self._universal = UniversalSeparator()
        return self._universal

    def suppress(
        self,
        audio: np.ndarray,
        sample_rate: int,
        suppress_categories: Sequence[str] = (),
        detection_threshold: float = 0.5,
        aggressiveness: float = 1.0,
        suppress_all: bool = False,
        universal_prompts: Sequence[str] = (),
        mask_floor: Optional[float] = None,
        max_suppression_ratio: Optional[float] = None,
        speech_dominance_threshold: Optional[float] = None,
    ) -> np.ndarray:
        # Legacy params (mask_floor, etc.) ignored; residual output used for all

        if suppress_all:
            if profiler:
                profiler.start("speech_enhancement")
            clean_audio = self.enhancer.enhance(audio, sample_rate)
            if profiler:
                profiler.end("speech_enhancement")
            return clean_audio

        if len(suppress_categories) == 0 and not universal_prompts:
            self._overlap_save_tail = None
            return audio

        if universal_prompts:
            detections = None
            smoothed_scores = {}
        else:
            if profiler:
                profiler.start("yamnet_detection")
            detections = self.detector.classify(audio, sample_rate)
            smoothed_scores = detections["smoothed"]
            if profiler:
                profiler.end("yamnet_detection")

        states = detections.get("states", {}) if detections else {}
        per_category_targets = []
        targets_to_suppress = []
        max_detection_confidence = 0.0
        has_transient_category = False
        for category in suppress_categories:
            if category not in self.category_map:
                logger.warning("Unknown category '%s', skipping", category)
                continue

            cat_config = self.category_map[category]
            wf_targets = cat_config.get("waveformer_targets", [])
            if not wf_targets:
                continue

            confidence = smoothed_scores.get(category, 0.0)
            if detection_threshold < 0:
                effective_threshold = detection_threshold
            else:
                effective_threshold = cat_config.get("detection_threshold", detection_threshold)

            # Gate on SchmittTrigger states for high-threshold categories (reduces false positives)
            use_stability_gate = effective_threshold >= 0.4
            meets_threshold = effective_threshold < 0 or confidence >= effective_threshold
            is_stable = states.get(category, False) if use_stability_gate else True

            if (effective_threshold < 0 or (meets_threshold and is_stable)):
                if effective_threshold < 0:
                    confidence = max(confidence, 0.9)
                per_category_targets.append((category, wf_targets))
                targets_to_suppress.extend(wf_targets)
                max_detection_confidence = max(max_detection_confidence, confidence)
                if cat_config.get("transient", False):
                    has_transient_category = True

        if not targets_to_suppress and not universal_prompts:
            self._overlap_save_tail = None
            return audio

        if universal_prompts:
            if profiler:
                profiler.start("universal_separation")
            unwanted_audio = self.universal_separator.separate(
                audio=audio,
                sample_rate=sample_rate,
                prompts=list(universal_prompts),
            )
            if profiler:
                profiler.end("universal_separation")
            max_detection_confidence = 0.9
            # Compute separation ratio for under-extraction scaling
            min_len_u = min(audio.shape[0], unwanted_audio.shape[0])
            mix_rms_u = np.sqrt(np.mean(audio[:min_len_u] ** 2)) + 1e-8
            unwanted_rms_u = np.sqrt(np.mean(unwanted_audio[:min_len_u] ** 2)) + 1e-8
            separation_ratio = unwanted_rms_u / mix_rms_u
        else:
            if profiler:
                profiler.start("input_normalization")
            max_val = np.max(np.abs(audio))
            if max_val < 1e-8:
                if profiler:
                    profiler.end("input_normalization")
                return audio
            scale_factor = 1.0 / max_val
            audio_norm = audio * scale_factor
            if profiler:
                profiler.end("input_normalization")

            if profiler:
                profiler.start("waveformer_separation")
            target_groups = [list(set(ct)) for _, ct in per_category_targets]
            if hasattr(self.separator, "separate_multi_query"):
                stems = self.separator.separate_multi_query(
                    audio=audio_norm,
                    sample_rate=sample_rate,
                    target_groups=target_groups,
                )
            else:
                stems = [
                    self.separator.separate(audio=audio_norm, sample_rate=sample_rate, targets=tg)
                    for tg in target_groups
                ]

            # Boost weak stems when detection is confident (under-extraction)
            mix_rms = np.sqrt(np.mean(audio_norm**2)) + 1e-8
            for i, stem in enumerate(stems):
                stem_rms = np.sqrt(np.mean(stem**2))
                relative_level = stem_rms / mix_rms
                if relative_level < 0.3 and max_detection_confidence >= 0.2:
                    boost = min(0.3 / (relative_level + 1e-8), self.weak_stem_boost_cap)
                    stems[i] = stem * boost

            unwanted_norm = stems[0]
            for stem in stems[1:]:
                min_samples = min(unwanted_norm.shape[0], stem.shape[0])
                unwanted_norm[:min_samples] = unwanted_norm[:min_samples] + stem[:min_samples]
            if profiler:
                profiler.end("waveformer_separation")

            unwanted_audio = unwanted_norm * (1.0 / scale_factor)

            # Compute separation ratio for under-extraction scaling
            mix_rms_post = np.sqrt(np.mean(audio[: unwanted_audio.shape[0]] ** 2)) + 1e-8
            unwanted_rms = np.sqrt(np.mean(unwanted_audio**2)) + 1e-8
            separation_ratio = unwanted_rms / mix_rms_post

        if profiler:
            profiler.start("decision_directed_mask")

        # Scale unwanted when under-extracted (low ratio = weak stem)
        under_extract_threshold = 0.3
        if separation_ratio < under_extract_threshold and separation_ratio > 1e-6:
            scale = min(
                self.under_extract_scale,
                under_extract_threshold / separation_ratio,
            )
            unwanted_audio = unwanted_audio * scale

        # Per-category aggressiveness override (stronger suppression for typing/pets)
        aggressiveness_override = 0.0
        for cat, _ in per_category_targets:
            override = self.category_map.get(cat, {}).get("aggressiveness_override", 0)
            aggressiveness_override = max(aggressiveness_override, override)
        effective_aggressiveness = max(aggressiveness, aggressiveness_override)

        # Transient categories: shorter STFT window + faster DD alpha for better time resolution
        mask_nperseg = 1024 if has_transient_category else self.spectral_nperseg
        mask_dd_alpha = 0.92 if has_transient_category else self.dd_alpha

        # Adaptive Wiener-IRM masking: three-layer pipeline
        # Layer 1: Wiener-IRM gain (SNR-proportional soft mask)
        # Layer 2: Perceptual A-weighting floor (frequency-dependent minimum gain)
        # Layer 3: Temporal EMA smoothing (cross-frame continuity)
        clean_audio = self._decision_directed_mask(
            mix=audio,
            unwanted=unwanted_audio,
            aggressiveness=effective_aggressiveness,
            sample_rate=sample_rate,
            nperseg=mask_nperseg,
            dd_alpha=mask_dd_alpha,
        )

        if profiler:
            profiler.end("decision_directed_mask")

        if audio.ndim == 1:
            return clean_audio.flatten()
        return clean_audio

    def detect_categories(
        self,
        audio: np.ndarray,
        sample_rate: int,
        threshold: float = 0.3,
    ) -> Dict[str, float]:
        detections = self.detector.classify(audio, sample_rate)
        smoothed = detections["smoothed"]
        return {cat: conf for cat, conf in smoothed.items() if conf >= threshold}

    def _build_perceptual_floor(self, n_freq_bins: int, sample_rate: int) -> np.ndarray:
        """Build a frequency-dependent minimum gain floor based on A-weighting.

        Human hearing is most sensitive at 1-5 kHz (higher floor = gentler
        suppression) and least sensitive below 200 Hz and above 10 kHz
        (lower floor = more aggressive suppression allowed).
        """
        cache_key = (n_freq_bins, sample_rate)
        if cache_key in self._perceptual_floor_cache:
            return self._perceptual_floor_cache[cache_key]

        freqs = np.linspace(0, sample_rate / 2, n_freq_bins)
        floor = np.full(n_freq_bins, self.perceptual_floor_min, dtype=np.float64)

        # Simplified A-weighting sensitivity curve:
        # Peak sensitivity at ~2.5 kHz, falls off below 200 Hz and above 10 kHz
        f_low, f_peak, f_high = 200.0, 2500.0, 10000.0
        for i, f in enumerate(freqs):
            if f < f_low or f > f_high:
                # Insensitive region: allow aggressive suppression
                floor[i] = self.perceptual_floor_min
            elif f <= f_peak:
                # Rising sensitivity: linearly interpolate toward max floor
                t = (f - f_low) / (f_peak - f_low)
                floor[i] = self.perceptual_floor_min + t * (
                    self.perceptual_floor_max - self.perceptual_floor_min
                )
            else:
                # Falling sensitivity: linearly interpolate back toward min floor
                t = (f - f_peak) / (f_high - f_peak)
                floor[i] = self.perceptual_floor_max - t * (
                    self.perceptual_floor_max - self.perceptual_floor_min
                )

        self._perceptual_floor_cache[cache_key] = floor
        return floor

    def _decision_directed_mask(
        self,
        mix: np.ndarray,
        unwanted: np.ndarray,
        aggressiveness: float,
        sample_rate: int,
        nperseg: Optional[int] = None,
        dd_alpha: Optional[float] = None,
    ) -> np.ndarray:
        """Ephraim-Malah Decision-Directed masking pipeline.

        Eliminates musical noise temporally without spectral blurring.
        Tracks a priori SNR (xi) over time to distinguish continuous sounds (speech)
        from transient noise spikes.

        Layer 1 — Decision-Directed SNR tracking:
            gamma(f,t) = |mix|² / |unw|²  (a posteriori SNR)
            xi(f,t) = α * (|clean_prev|² / |unw_prev|²) + (1-α) * max(gamma - 1, 0)
            Gain = xi / (xi + aggressiveness)

        Layer 2 — Perceptual A-weighting floor:
            Gain_clamped = max(Gain, perceptual_floor(f))
        """
        nperseg = nperseg if nperseg is not None else self.spectral_nperseg
        noverlap = nperseg // 2
        alpha = dd_alpha if dd_alpha is not None else self.dd_alpha
        eps = 1e-10

        mix_2d = mix.reshape(-1, 1) if mix.ndim == 1 else mix
        unwanted_2d = unwanted.reshape(-1, 1) if unwanted.ndim == 1 else unwanted
        min_len = min(mix_2d.shape[0], unwanted_2d.shape[0])
        num_channels = mix_2d.shape[1]

        unw_channels = min(num_channels, unwanted_2d.shape[1])
        clean_channels = []
        for ch in range(num_channels):
            mix_ch = mix_2d[:min_len, ch].astype(np.float64)
            unw_ch = np.asarray(
                unwanted_2d[:min_len, ch % unw_channels], dtype=np.float64
            ).ravel()[:min_len]

            _, _, Z_mix = scipy_signal.stft(
                mix_ch, nperseg=nperseg, noverlap=noverlap
            )
            _, _, Z_unw = scipy_signal.stft(
                unw_ch, nperseg=nperseg, noverlap=noverlap
            )

            mag_mix = np.abs(Z_mix)
            mag_unw = np.abs(Z_unw)
            phase_mix = np.angle(Z_mix)

            mix_power = mag_mix ** 2
            unw_power = (mag_unw ** 2) + eps

            # --- Layer 1: Decision-Directed tracking ---
            n_freq_bins, n_frames = mix_power.shape
            xi = np.zeros_like(mix_power)
            
            # Retrieve or initialize state
            if ch in self._decision_directed_state:
                prev_clean_power, prev_unw_power = self._decision_directed_state[ch]
                if prev_clean_power.shape[0] != n_freq_bins:
                    prev_clean_power = np.zeros(n_freq_bins)
                    prev_unw_power = np.ones(n_freq_bins) * eps
            else:
                prev_clean_power = np.zeros(n_freq_bins)
                prev_unw_power = np.ones(n_freq_bins) * eps

            # Iterate frames to compute a priori SNR (xi)
            for t in range(n_frames):
                gamma = mix_power[:, t] / unw_power[:, t]
                # A posteriori SNR max(gamma - 1, 0)
                gamma_minus_1 = np.maximum(gamma - 1.0, 0.0)
                
                # Decision-Directed update
                snr_prior = prev_clean_power / prev_unw_power
                xi[:, t] = alpha * snr_prior + (1.0 - alpha) * gamma_minus_1
                
                # Wiener gain from a priori SNR
                # Standard Wiener: xi / (1 + xi)
                # Aggressive Wiener: xi / (aggressiveness + xi)
                gain_t = xi[:, t] / (aggressiveness + xi[:, t])
                
                # Update state for next frame
                prev_clean_power = (gain_t ** 2) * mix_power[:, t]
                prev_unw_power = unw_power[:, t]

            # Save state for next audio chunk
            self._decision_directed_state[ch] = (prev_clean_power, prev_unw_power)
            
            # Vectorized gain
            gain = xi / (aggressiveness + xi)

            # --- Layer 2: Perceptual A-weighting floor ---
            perceptual_floor = self._build_perceptual_floor(n_freq_bins, sample_rate)
            gain = np.maximum(gain, perceptual_floor[:, np.newaxis])

            # Apply gain mask to mix (preserve mix phase)
            Z_clean = (gain * mag_mix) * np.exp(1j * phase_mix)

            _, clean_ch = scipy_signal.istft(
                Z_clean, nperseg=nperseg, noverlap=noverlap
            )
            clean_ch = clean_ch[:min_len]
            if len(clean_ch) < min_len:
                clean_ch = np.pad(
                    clean_ch, (0, min_len - len(clean_ch)), mode="constant"
                )
            clean_channels.append(clean_ch)

        clean_audio = np.column_stack(clean_channels)
        if mix.ndim == 1:
            clean_audio = clean_audio.flatten()
        return clean_audio.astype(mix.dtype)

    def _load_mapping(self, path: Path) -> Dict[str, dict]:
        if not path.exists():
            raise FileNotFoundError(f"Mapping file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        categories = data.get("categories", {})
        logger.info("Loaded %d category mappings from %s", len(categories), path)
        return categories


__all__ = ["SemanticSuppressor"]
