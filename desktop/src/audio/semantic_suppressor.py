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
        safety_check: bool = True,
        aggressiveness: float = 1.0,
        suppress_all: bool = False,
        universal_prompts: Sequence[str] = (),
    ) -> np.ndarray:
        """
        Suppress specified semantic categories from audio.
        
        Args:
            audio: Input audio (mono/stereo), shape (samples,) or (samples, channels)
            sample_rate: Sample rate of input audio
            suppress_categories: List of categories to suppress (e.g., ["typing", "wind"])
            detection_threshold: Confidence threshold for detection (0.0-1.0)
            safety_check: If True, override suppression for critical sounds (sirens, alarms)
            aggressiveness: Multiplier for subtraction (1.0 = normal, >1.0 = aggressive)
            suppress_all: If True, bypass categories and use generalized speech enhancement
            universal_prompts: If provided, bypasses YAMNet/Waveformer and uses literal text prompts (Phase 3)
        
        Returns:
            Clean audio with suppressed sounds removed, same shape as input
        """
        
        if suppress_all:
            # Safety override check still applies in suppress_all mode
            if safety_check:
                safe_detections = self.detector.classify(audio, sample_rate)
                if self.detector.check_safety_override(safe_detections["states"]):
                    logger.warning("SAFETY OVERRIDE: Critical sound detected (siren/alarm), bypassing suppression")
                    return audio
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

        # Step 2: Safety override check
        if not universal_prompts and safety_check and self.detector.check_safety_override(detections["states"]):
            logger.warning("SAFETY OVERRIDE: Critical sound detected (siren/alarm), bypassing suppression")
            return audio

        # Step 3: Build list of Waveformer targets to suppress
        targets_to_suppress = []
        logger.debug(f"[DEBUG] Processing {len(suppress_categories)} categories: {suppress_categories}")
        for category in suppress_categories:
            if category not in self.category_map:
                logger.debug(f"[DEBUG] Category '{category}' NOT in mapping!")
                logger.warning(f"Unknown category '{category}', skipping")
                continue
            
            cat_config = self.category_map[category]
            
            # Safety check: never suppress critical sounds
            if cat_config.get("safety_override", False):
                logger.warning(f"Cannot suppress '{category}' - safety critical sound")
                continue
            
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
                else:
                    logger.info(
                        f"Suppressing '{category}' (confidence: {confidence:.2f} >= threshold: {effective_threshold})"
                    )
                
                targets_to_suppress.extend(wf_targets)
            else:
                logger.debug(
                    f"Skipping '{category}' (confidence: {confidence:.2f} < threshold: {effective_threshold})"
                )

        if not targets_to_suppress and not universal_prompts:
            logger.debug("No targets detected above threshold, returning original audio")
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
            unwanted_norm = self.separator.separate(
                audio=audio_norm,
                sample_rate=sample_rate,
                targets=list(set(targets_to_suppress))
            )
            if profiler:
                profiler.end('waveformer_separation')
            
            # Denormalize
            unwanted_audio = unwanted_norm * (1.0 / scale_factor)
        
        # Step 5: Inverse separation via Spectral (STFT) Masking
        # This replaces the flawed time-domain subtraction (Mix - Unwanted)
        if profiler:
            profiler.start('spectral_masking')
            
        audio_2d = audio.reshape(-1, 1) if audio.ndim == 1 else audio
        unwanted_2d = unwanted_audio.reshape(-1, 1) if unwanted_audio.ndim == 1 else unwanted_audio
        
        min_len = min(audio_2d.shape[0], unwanted_2d.shape[0])
        mix_aligned = audio_2d[:min_len]
        unwanted_aligned = unwanted_2d[:min_len]
        
        # Start with a copy of the original to preserve any tail that Waveformer chopped
        clean_audio = audio_2d.copy()
        
        # STFT parameters optimized for speech/audio latency
        # nperseg should be a power of 2, typically 1024 or 512.
        # If the input is smaller than 512, we adjust it down, but keeping it power of 2
        nperseg = 1024
        while nperseg > min_len and nperseg > 256:
            nperseg //= 2
            
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
            # 1. Compute STFT of Mixture and Unwanted (vectorized over channels)
            # Transpose to (channels, time) for vectorized STFT processing
            mix_aligned_t = mix_aligned[:min_len, :num_channels].T
            unwanted_prepared_t = unwanted_prepared.T

            f, t, Zxx_mix = signal.stft(mix_aligned_t, fs=sample_rate, nperseg=nperseg)
            _, _, Zxx_unwanted = signal.stft(unwanted_prepared_t, fs=sample_rate, nperseg=nperseg)
            
            # 2. Compute Magnitudes
            mag_mix = np.abs(Zxx_mix)
            mag_unwanted = np.abs(Zxx_unwanted)
            
            # 3. Compute Spectral Ratio Mask
            eps = 1e-8
            ratio = (mag_unwanted * aggressiveness) / (mag_mix + eps)
            
            # Soft mask: 1.0 (keep) down to 0.0 (remove)
            mask = np.clip(1.0 - ratio, 0.0, 1.0)
            
            # 4. Apply Mask to Original Complex STFT (Preserves Phase)
            Zxx_clean = Zxx_mix * mask
            
            # 5. Inverse STFT to get clean waveform for all channels
            # ISTFT expects (..., freq, time)
            _, clean_multi_t = signal.istft(Zxx_clean, fs=sample_rate)
            
            # Transpose back to (time, channels)
            clean_multi = clean_multi_t.T
            out_len = min(min_len, clean_multi.shape[0])
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
