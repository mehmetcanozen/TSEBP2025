"""
Semantic Noise Suppressor - Core Intelligence

Bridges YAMNet detection → Waveformer separation for intelligent noise removal.

Key Innovation: "Inverse Separation"
Instead of extracting unwanted sounds, we:
1. Detect unwanted sounds with YAMNet
2. Separate them with Waveformer
3. Subtract from original: clean = original - unwanted

This preserves audio quality better than traditional noise gates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import scipy.signal as signal
import scipy.ndimage
import yaml

from training.models.semantic_detective import SemanticDetective
from training.models.audio_mixer import WaveformerSeparator
from training.models.speech_enhancer import SpeechEnhancer
from training.models.universal_separator import UniversalSeparator

logger = logging.getLogger(__name__)

# Import performance profiler for optimization analysis
try:
    from .profiler import get_profiler
    profiler = get_profiler()
except ImportError:
    # Fallback if profiler not available
    profiler = None
    logger.warning("Profiler not available, performance tracking disabled")

DEFAULT_MAPPING_PATH = (
    Path(__file__).resolve().parents[3] / "shared" / "mappings" / "yamnet_to_waveformer.yaml"
)


class SemanticSuppressor:
    """
    Intelligent noise suppressor using semantic understanding.
    
    Usage:
        suppressor = SemanticSuppressor()
        clean_audio = suppressor.suppress(
            audio=noisy_audio,
            sample_rate=44100,
            suppress_categories=["typing", "traffic"]
        )
    
    Thread Safety:
        NOT thread-safe due to underlying SemanticDetective state.
        Each thread should create its own instance.
    """

    def __init__(
        self,
        mapping_path: Path = DEFAULT_MAPPING_PATH,
        detector: Optional[SemanticDetective] = None,
        separator: Optional[WaveformerSeparator] = None,
        enhancer: Optional[SpeechEnhancer] = None,
        universal: Optional[UniversalSeparator] = None,
    ) -> None:
        """
        Initialize semantic suppressor.
        
        Args:
            mapping_path: Path to yamnet_to_waveformer.yaml mapping config
            detector: Optional pre-initialized SemanticDetective instance
            separator: Optional pre-initialized WaveformerSeparator instance
            enhancer: Optional pre-initialized SpeechEnhancer instance
        """
        self.mapping_path = mapping_path
        self.category_map = self._load_mapping(mapping_path)
        
        # Lazy initialization of heavy models
        self._detector = detector
        self._separator = separator
        self._enhancer = enhancer
        self._universal = universal
        
        # Pre-computed STFT windows for spectral masking (avoids per-call allocation)
        self._stft_windows = {
            512: signal.get_window('hann', 512),
            1024: signal.get_window('hann', 1024),
        }
        
        # Overlap-save state for cross-call phase continuity.
        # Stores the last `nperseg` samples from the previous iSTFT output
        # so consecutive calls blend smoothly without chunk-boundary clicks.
        self._overlap_save_tail = None

    @property
    def enhancer(self) -> SpeechEnhancer:
        """Lazy load enhancer only when needed."""
        if self._enhancer is None:
            logger.info("Initializing SpeechEnhancer...")
            self._enhancer = SpeechEnhancer()
        return self._enhancer

    @property
    def detector(self) -> SemanticDetective:
        """Lazy load detector only when needed."""
        if self._detector is None:
            logger.info("Initializing SemanticDetective...")
            self._detector = SemanticDetective()
        return self._detector

    @property
    def separator(self) -> WaveformerSeparator:
        """Lazy load separator only when needed."""
        if self._separator is None:
            logger.info("Initializing WaveformerSeparator...")
            self._separator = WaveformerSeparator()
        return self._separator

    @property
    def universal_separator(self) -> UniversalSeparator:
        """Lazy load universal separator (AudioSep) only when needed."""
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
    ) -> np.ndarray:
        """
        Suppress specified semantic categories from audio.
        
        Uses a two-stage masking pipeline for high-fidelity suppression:
          Stage 1: Primary spectral mask with adaptive floor and mask smoothing.
          Stage 2: Wiener post-filter on residual to catch leaked transient energy.
        
        Args:
            audio: Input audio (mono/stereo), shape (samples,) or (samples, channels)
            sample_rate: Sample rate of input audio
            suppress_categories: List of categories to suppress (e.g., ["typing", "wind", "siren"])
            detection_threshold: Confidence threshold for detection (0.0-1.0)
            aggressiveness: Multiplier for subtraction (1.0 = normal, >1.0 = aggressive)
            suppress_all: If True, bypass categories and use generalized speech enhancement
            universal_prompts: If provided, bypasses YAMNet/Waveformer and uses literal text prompts (Phase 3).
                Highly effective for sounds NOT in the fixed Waveformer category list.
        
        Returns:
            Clean audio with suppressed sounds removed, same shape as input
        """
        
        if suppress_all:
            if profiler:
                profiler.start('speech_enhancement')
            logger.info("Suppress All mode active - routing to DeepFilterNet")
            clean_audio = self.enhancer.enhance(audio, sample_rate)
            if profiler:
                profiler.end('speech_enhancement')
            return clean_audio

        if len(suppress_categories) == 0 and not universal_prompts:
            # Passthrough mode - no suppression needed
            logger.debug("No suppression categories or universal prompts specified, returning original audio")
            self._overlap_save_tail = None
            return audio
            
        if universal_prompts:
            # Bypass detection and waveformer translation entirely!
            targets_to_suppress = []
            detections = None
            smoothed_scores = {}
        else:
            # Step 1: Detect sounds in the audio
            if profiler:
                profiler.start('yamnet_detection')
            detections = self.detector.classify(audio, sample_rate)
            smoothed_scores = detections["smoothed"]
            if profiler:
                profiler.end('yamnet_detection')
        
        if not universal_prompts:
            logger.debug(f"Detections: {smoothed_scores}")

        # Step 2: Build per-category Waveformer target lists
        # Each category gets its own Waveformer pass to prevent loud sources
        # from dominating quiet ones in the neural network output.
        per_category_targets = []  # list of (category_name, wf_targets_list)
        targets_to_suppress = []   # flat list for logging / early-exit check
        max_detection_confidence = 0.0
        has_transient_category = False
        logger.debug(f"[DEBUG] Processing {len(suppress_categories)} categories: {suppress_categories}")
        for category in suppress_categories:
            if category not in self.category_map:
                logger.debug(f"[DEBUG] Category '{category}' NOT in mapping!")
                logger.warning(f"Unknown category '{category}', skipping")
                continue
            
            cat_config = self.category_map[category]
            
            # Check if we have Waveformer targets for this category
            wf_targets = cat_config.get("waveformer_targets", [])
            if not wf_targets:
                logger.debug(f"Category '{category}' has no Waveformer targets, using DSP fallback")
                # TODO: Implement spectral gating for categories without Waveformer targets
                continue
            
            # Get detection confidence for this category
            confidence = smoothed_scores.get(category, 0.0)
            
            # Allow per-category override of detection_threshold from configuration
            # unless we are forcing suppression (threshold < 0)
            if detection_threshold < 0:
                effective_threshold = detection_threshold
            else:
                effective_threshold = cat_config.get("detection_threshold", detection_threshold)
            
            if effective_threshold < 0 or confidence >= effective_threshold:
                if effective_threshold < 0:
                    logger.debug(f"Forcing suppression for '{category}' (Force Mode)")
                    # In force mode, assume high confidence for adaptive masking
                    confidence = max(confidence, 0.9)
                else:
                    logger.info(
                        f"Suppressing '{category}' (confidence: {confidence:.2f} >= threshold: {effective_threshold})"
                    )
                
                per_category_targets.append((category, wf_targets))
                targets_to_suppress.extend(wf_targets)
                max_detection_confidence = max(max_detection_confidence, confidence)
                
                # Check if this category has sharp transient sounds
                if cat_config.get("transient", False):
                    has_transient_category = True
            else:
                logger.debug(
                    f"Skipping '{category}' (confidence: {confidence:.2f} < threshold: {effective_threshold})"
                )

        if not targets_to_suppress and not universal_prompts:
            logger.debug("No targets detected above threshold, returning original audio")
            self._overlap_save_tail = None
            return audio

        # Step 4: Separate unwanted sounds using the appropriate foundational model
        if universal_prompts:
            if profiler:
                profiler.start('universal_separation')
            logger.info(f"Using Universal Text Prompts: {universal_prompts}")
            # Directly pass the raw waveform to AudioSep, bypassing normalizations
            # AudioSep naturally handles amplitude scales based on diffusion/CLAP embedding vectors
            unwanted_audio = self.universal_separator.separate(
                audio=audio,
                sample_rate=sample_rate,
                prompts=list(universal_prompts)
            )
            if profiler:
                profiler.end('universal_separation')
            # For universal prompts, assume high confidence
            max_detection_confidence = 0.9
        else:
            logger.debug(f"[DEBUG] SEPARATING TARGETS: {targets_to_suppress}")
            logger.info(f"Separating Waveformer targets: {targets_to_suppress}")
            
            # NORMALIZE input for Waveformer
            if profiler:
                profiler.start('input_normalization')
            max_val = np.max(np.abs(audio))
            if max_val < 1e-8:
                if profiler:
                    profiler.end('input_normalization')
                return audio
            scale_factor = 1.0 / max_val
            audio_norm = audio * scale_factor
            if profiler:
                profiler.end('input_normalization')
            
            if profiler:
                profiler.start('waveformer_separation')
            
            # Per-category separation: each category gets its own Waveformer query
            # so that loud sources (e.g. barking) don't dominate quiet targets
            # (e.g. typing) in the neural network output.
            #
            # Optimization: use separate_multi_query() to preprocess audio once
            # and batch all queries in a single forward pass on GPU.
            target_groups = [list(set(ct)) for _, ct in per_category_targets]
            for cat_name, ct in per_category_targets:
                logger.debug(f"Separating category '{cat_name}': {list(set(ct))}")

            if hasattr(self.separator, 'separate_multi_query'):
                stems = self.separator.separate_multi_query(
                    audio=audio_norm,
                    sample_rate=sample_rate,
                    target_groups=target_groups,
                )
            else:
                # Fallback for separators without batched method (e.g. test mocks)
                stems = [
                    self.separator.separate(
                        audio=audio_norm, sample_rate=sample_rate, targets=tg,
                    )
                    for tg in target_groups
                ]

            # ── Adaptive stem boosting ──
            # Waveformer under-extracts quiet targets when loud sounds dominate
            # the mix (e.g. typing at 0.05 amp alongside barking at 0.9 amp).
            # The extracted stem preserves the correct spectral *shape* but with
            # near-zero magnitude, making the downstream spectral ratio mask
            # ineffective.  We boost weak stems so the mask can do its job.
            mix_rms = np.sqrt(np.mean(audio_norm ** 2)) + 1e-8
            for i, stem in enumerate(stems):
                stem_rms = np.sqrt(np.mean(stem ** 2))
                relative_level = stem_rms / mix_rms

                if relative_level < 0.1:
                    # Stem energy is <10% of mix — likely under-extracted
                    boost = min(0.1 / (relative_level + 1e-8), 4.0)
                    stems[i] = stem * boost
                    cat_name = per_category_targets[i][0] if i < len(per_category_targets) else "?"
                    logger.debug(
                        f"Boosting weak stem '{cat_name}': "
                        f"relative_level={relative_level:.4f}, boost={boost:.2f}x"
                    )

            # Sum all per-category stems into a single unwanted signal
            unwanted_norm = stems[0]
            for stem in stems[1:]:
                min_samples = min(unwanted_norm.shape[0], stem.shape[0])
                unwanted_norm[:min_samples] = unwanted_norm[:min_samples] + stem[:min_samples]
            
            if profiler:
                profiler.end('waveformer_separation')
            
            # Denormalize
            unwanted_audio = unwanted_norm * (1.0 / scale_factor)
        
        # Step 5: Two-Stage Spectral Masking Pipeline
        # Stage 1: Primary spectral mask with adaptive floor and smoothing
        # Stage 2: Wiener post-filter on residual to catch leaked transient energy
        if profiler:
            profiler.start('spectral_masking')
            
        audio_2d = audio.reshape(-1, 1) if audio.ndim == 1 else audio
        unwanted_2d = unwanted_audio.reshape(-1, 1) if unwanted_audio.ndim == 1 else unwanted_audio
        
        min_len = min(audio_2d.shape[0], unwanted_2d.shape[0])
        mix_aligned = audio_2d[:min_len]
        unwanted_aligned = unwanted_2d[:min_len]
        
        # Start with a copy of the original to preserve any tail that Waveformer chopped
        clean_audio = audio_2d.copy()
        
        # Transient-aware STFT window selection:
        # Shorter windows capture sharp sounds (barks, impacts) better at the cost
        # of frequency resolution. Longer windows are better for tonal/stationary noise.
        if has_transient_category:
            nperseg = 512   # ~11.6ms at 44.1kHz — better for transients
        else:
            nperseg = 1024  # ~23.2ms at 44.1kHz — better for tonal sounds
        while nperseg > min_len and nperseg > 256:
            nperseg //= 2
            
        noverlap = nperseg // 2
            
        # Prepare unwanted signal to match the number of channels in the mix.
        num_channels = audio_2d.shape[1]
        unwanted_prepared = np.empty((min_len, num_channels), dtype=mix_aligned.dtype)
        # Copy available unwanted channels
        max_unwanted_ch = min(num_channels, unwanted_2d.shape[1])
        unwanted_prepared[:, :max_unwanted_ch] = unwanted_aligned[:min_len, :max_unwanted_ch]
        # For any extra channels, fall back to the first unwanted channel (previous behavior)
        if max_unwanted_ch < num_channels:
            unwanted_prepared[:, max_unwanted_ch:] = unwanted_aligned[:min_len, [0]]

        if min_len < nperseg:
            # Absolute fallback if buffer is microscopic (e.g. < 64 samples)
            # We do simple waveform subtraction as a last resort, vectorized over channels
            logger.warning(
                "Spectral masking skipped due to very short buffer (min_len=%d < nperseg=%d); "
                "falling back to time-domain subtraction. "
                "Consider using larger audio chunks to avoid potential phase artifacts.",
                min_len,
                nperseg,
            )
            clean_audio[:min_len, :num_channels] = (
                mix_aligned[:min_len, :num_channels] - (unwanted_prepared * aggressiveness)
            )
        else:
            # ── Adaptive mask floor ──
            # Always at least as aggressive as old baseline (0.95 max_ratio / 0.05 floor).
            # At high detection confidence, allow even deeper suppression (up to 0.99).
            # This ensures we never suppress LESS than before, only MORE when confident.
            max_ratio = 0.95 + 0.04 * max_detection_confidence
            mask_floor = 1.0 - max_ratio
            logger.debug(
                f"Adaptive masking: confidence={max_detection_confidence:.2f}, "
                f"aggressiveness={aggressiveness:.2f}, "
                f"mask_floor={mask_floor:.3f}, max_ratio={max_ratio:.3f}, "
                f"nperseg={nperseg}, transient={has_transient_category}"
            )
            
            # ══════════════════════════════════════════
            # STAGE 1: Wiener-Style Soft Mask (MMSE)
            # ══════════════════════════════════════════
            # Replaces the simple ratio mask (1 - unwanted/mix) which can't
            # handle T-F bins where target noise and speech coexist.
            # The Wiener mask estimates clean signal power vs noise power:
            #   clean_psd = max(|mix|² - α·|unwanted|², 0)
            #   mask = clean_psd / (clean_psd + |unwanted|² + ε)
            # In noise-only bins: clean_psd ≈ 0 → mask ≈ 0 (suppress)
            # In speech-only bins: clean_psd ≈ |mix|² → mask ≈ 1 (keep)
            # In shared bins: mask ∝ SNR (graceful proportional blend)
            # Transpose to (channels, time) for vectorized STFT processing
            mix_aligned_t = mix_aligned[:min_len, :num_channels].T
            unwanted_prepared_t = unwanted_prepared.T

            # ── Audio Padding for Edge-Agnostic STFT ──
            # By default, STFT/iSTFT windowing causes the signal to fade to zero at the
            # very beginning and end of the buffer. To get a fully reconstructed
            # signal across the entire chunk, we pad the audio with reflected samples,
            # process, and then discard the padding.
            # Reflect padding requires pad_width < signal length along the padded axis.
            # Clamp pad_len so that it never equals or exceeds min_len.
            pad_len = min(nperseg, max(0, min_len - 1))
            mix_padded = np.pad(mix_aligned_t, ((0, 0), (pad_len, pad_len)), mode='reflect')
            unwanted_padded = np.pad(unwanted_prepared_t, ((0, 0), (pad_len, pad_len)), mode='reflect')

            # Use pre-computed STFT window from cache
            stft_window = self._stft_windows.get(nperseg, signal.get_window('hann', nperseg))
            
            f, t_frames, Zxx_mix = signal.stft(
                mix_padded, fs=sample_rate, window=stft_window,
                nperseg=nperseg, noverlap=noverlap
            )
            _, _, Zxx_unwanted = signal.stft(
                unwanted_padded, fs=sample_rate, window=stft_window,
                nperseg=nperseg, noverlap=noverlap
            )
            
            # Compute magnitudes
            mag_mix = np.abs(Zxx_mix)
            mag_unwanted = np.abs(Zxx_unwanted)
            
            # Wiener-style MMSE mask (Aggressive)
            eps = 1e-8
            noise_psd = mag_unwanted ** 2
            # Use 2.0x over-subtraction to ensure deep suppression in noise-heavy bins
            clean_psd = np.maximum(mag_mix ** 2 - 2.0 * (aggressiveness * mag_unwanted) ** 2, 0.0)
            mask = clean_psd / (clean_psd + noise_psd + eps)
            mask = np.clip(mask, mask_floor, 1.0)
            
            # ── Spectral mask smoothing ──
            # Apply a small median filter (3×3 in freq×time) to eliminate isolated
            # spectral holes that cause chirp/musical-noise artifacts.
            for ch in range(mask.shape[0]):
                mask[ch] = scipy.ndimage.median_filter(mask[ch], size=(3, 3), mode='reflect')
            
            # Apply Stage 1 mask to original complex STFT (preserves phase)
            Zxx_stage1 = Zxx_mix * mask
            
            # ══════════════════════════════════════════
            # STAGE 2: Targeted Residual Cleanup
            # ══════════════════════════════════════════
            # Only targets T-F bins where Stage 1 already identified heavy noise
            # (mask < 0.5). This avoids touching speech-dominant bins entirely,
            # preventing the garbled output that a full Wiener filter would cause
            # when the separator's unwanted stem contains leaked speech.
            noise_heavy_bins = mask < 0.7  # bins where Stage 1 found strong noise
            
            if np.any(noise_heavy_bins):
                mag_stage1 = np.abs(Zxx_stage1)
                
                # Residual noise estimate: energy that Stage 1 SHOULD have removed
                # but couldn't due to the mask floor.  Use (1 - mask) * unwanted
                # as the noise that was supposed to be subtracted.
                mag_residual = mag_unwanted * (1.0 - mask)
                
                # Gentle Wiener gain — only in noise-heavy bins
                wiener_alpha = 0.5 * aggressiveness  # conservative alpha
                signal_psd = mag_stage1 ** 2
                residual_psd = mag_residual ** 2
                gain = signal_psd / (signal_psd + wiener_alpha * residual_psd + eps)
                gain = np.clip(gain, mask_floor, 1.0)
                
                # Apply only to noise-heavy bins; leave speech bins untouched
                wiener_gain = np.where(noise_heavy_bins, gain, 1.0)
                Zxx_clean = Zxx_stage1 * wiener_gain
            else:
                Zxx_clean = Zxx_stage1
            
            # Inverse STFT to get clean waveform for all channels
            _, clean_multi_padded_t = signal.istft(
                Zxx_clean, fs=sample_rate, window=stft_window, noverlap=noverlap
            )
            
            # Discard the padding to get the fully-reconstructed chunk
            # The start/end fades are now outside the [pad_len : pad_len+min_len] range
            clean_multi_t = clean_multi_padded_t[:, pad_len : pad_len + min_len]
            
            # Transpose back to (time, channels)
            clean_multi = clean_multi_t.T
            out_len = clean_multi.shape[0]
            
            # ── Overlap-save blending ──
            # Blend the start of this chunk with the saved tail from the
            # previous suppress() call using a raised-cosine (Hann) window.
            # This eliminates phase discontinuities at chunk boundaries.
            blend_len = nperseg
            if self._overlap_save_tail is not None:
                prev_tail = self._overlap_save_tail
                actual_blend = min(blend_len, out_len, prev_tail.shape[0])
                if actual_blend > 0 and prev_tail.shape[1] >= num_channels:
                    # Robust Linear Crossfade: Blend start of this chunk with the 
                    # tail of the previous one. This compensates for the iSTFT's
                    # windowing effects and ensures boundary smoothness.
                    fade_in = np.linspace(0.0, 1.0, actual_blend)[:, np.newaxis]
                    fade_out = 1.0 - fade_in
                    clean_multi[:actual_blend, :num_channels] = (
                        clean_multi[:actual_blend, :num_channels] * fade_in +
                        prev_tail[-actual_blend:, :num_channels] * fade_out
                    )
            
            # Save the tail for the NEXT call
            if out_len > blend_len:
                self._overlap_save_tail = clean_multi[out_len - blend_len:out_len, :num_channels].copy()
            else:
                self._overlap_save_tail = clean_multi[:out_len, :num_channels].copy()
            
            clean_audio[:out_len, :num_channels] = clean_multi[:out_len, :num_channels]
            
        if profiler:
            profiler.end('spectral_masking')
        
        # Restore original shape
        if audio.ndim == 1:
            clean_audio = clean_audio.flatten()

        return clean_audio

    def detect_categories(
        self,
        audio: np.ndarray,
        sample_rate: int,
        threshold: float = 0.3,
    ) -> Dict[str, float]:
        """
        Detect semantic categories in audio without suppression.
        
        Useful for UI display or auto-profile selection.
        
        Args:
            audio: Input audio
            sample_rate: Sample rate
            threshold: Minimum confidence to include in results
        
        Returns:
            Dictionary of {category: confidence} for detected sounds
        """
        detections = self.detector.classify(audio, sample_rate)
        smoothed = detections["smoothed"]
        
        return {
            cat: conf
            for cat, conf in smoothed.items()
            if conf >= threshold
        }

    def _load_mapping(self, path: Path) -> Dict[str, dict]:
        """Load YAMNet-to-Waveformer mapping configuration."""
        if not path.exists():
            raise FileNotFoundError(f"Mapping file not found: {path}")
        
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        categories = data.get("categories", {})
        logger.info(f"Loaded {len(categories)} category mappings from {path}")
        
        return categories


__all__ = ["SemanticSuppressor"]
