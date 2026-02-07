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
import yaml

from training.models.semantic_detective import SemanticDetective
from training.models.audio_mixer import WaveformerSeparator

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
    ) -> None:
        """
        Initialize semantic suppressor.
        
        Args:
            mapping_path: Path to yamnet_to_waveformer.yaml mapping config
            detector: Optional pre-initialized SemanticDetective instance
            separator: Optional pre-initialized WaveformerSeparator instance
        """
        self.mapping_path = mapping_path
        self.category_map = self._load_mapping(mapping_path)
        
        # Lazy initialization of heavy models
        self._detector = detector
        self._separator = separator

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

    def suppress(
        self,
        audio: np.ndarray,
        sample_rate: int,
        suppress_categories: Sequence[str],
        detection_threshold: float = 0.5,
        safety_check: bool = True,
        aggressiveness: float = 1.0,
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
        
        Returns:
            Clean audio with suppressed sounds removed, same shape as input
        """
        if len(suppress_categories) == 0:
            # Passthrough mode - no suppression needed
            logger.debug("No suppression categories specified, returning original audio")
            return audio

        # Step 1: Detect sounds in the audio
        if profiler:
            profiler.start('yamnet_detection')
        detections = self.detector.classify(audio, sample_rate)
        smoothed_scores = detections["smoothed"]
        if profiler:
            profiler.end('yamnet_detection')
        
        logger.debug(f"Detections: {smoothed_scores}")

        # Step 2: Safety override check
        if safety_check and self.detector.check_safety_override(detections["states"]):
            logger.warning("SAFETY OVERRIDE: Critical sound detected (siren/alarm), bypassing suppression")
            return audio

        # Step 3: Build list of Waveformer targets to suppress
        targets_to_suppress = []
        for category in suppress_categories:
            if category not in self.category_map:
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

        if not targets_to_suppress:
            logger.debug("No targets detected above threshold, returning original audio")
            return audio

        # Step 4: Separate unwanted sounds using Waveformer
        logger.info(f"Separating targets: {targets_to_suppress}")
        
        # NORMALIZE input for the model (crucial for quiet mics)
        # Models are trained on normalized audio (-1 to 1). If mic is quiet, it fails.
        if profiler:
            profiler.start('input_normalization')
        max_val = np.max(np.abs(audio))
        if max_val < 1e-8:
            # Silence
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
        
        # Step 5: Inverse separation - subtract unwanted from original
        # Handle stereo/mono shape differences
        audio_2d = audio.reshape(-1, 1) if audio.ndim == 1 else audio
        
        # Ensure same length (Waveformer may return slightly different length)
        min_len = min(audio_2d.shape[0], unwanted_audio.shape[0])
        
        # Aggressive Subtraction
        # subtract (unwanted * aggressiveness)
        # We limit the subtraction to avoid exploding artifacts?
        # No, simple scaling is standard over-subtraction.
        if profiler:
            profiler.start('aggressive_subtraction')
        
        # Preserve original audio length even if Waveformer output is slightly different
        clean_audio = audio_2d.copy()
        clean_audio[:min_len] = audio_2d[:min_len] - (unwanted_audio[:min_len] * aggressiveness)
        
        if profiler:
            profiler.end('aggressive_subtraction')
        
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
