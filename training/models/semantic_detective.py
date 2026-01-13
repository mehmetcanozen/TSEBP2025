"""
YAMNet-based semantic sound detector with temporal smoothing and hysteresis.

Responsibilities:
- Load YAMNet from TensorFlow Hub.
- Map 521 AudioSet classes to a small set of semantic categories.
- Apply temporal smoothing (2-of-3 buffer), Schmitt trigger hysteresis, and optional
  median filtering to prevent UI flicker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import yaml
from scipy import signal as scipy_signal

logger = logging.getLogger(__name__)

YAMNET_SAMPLE_RATE = 16000
DEFAULT_CLASS_MAP_PATH = Path("training/configs/yamnet_class_map.yaml")
DEFAULT_MODEL_HANDLE = "https://tfhub.dev/google/yamnet/1"


# ------------------------------ smoothing helpers ---------------------------- #
class ConfidenceBuffer:
    """
    Rolling 2-of-3 voting buffer to stabilize transient detections.

    Prevents false positives from single-frame spikes by requiring
    detection in at least 2 of the last N frames.

    Args:
        window_size: Number of frames to consider (default 3).
        threshold: Confidence threshold for a "hit" (default 0.5).
    """

    def __init__(self, window_size: int = 3, threshold: float = 0.5) -> None:
        self.window_size = window_size
        self.threshold = threshold
        self.history: Dict[str, List[bool]] = {}

    def update(self, detections: Mapping[str, float]) -> Dict[str, bool]:
        stable: Dict[str, bool] = {}
        for category, confidence in detections.items():
            if category not in self.history:
                self.history[category] = []
            self.history[category].append(confidence > self.threshold)
            if len(self.history[category]) > self.window_size:
                self.history[category].pop(0)
            hits = sum(self.history[category])
            stable[category] = hits >= 2
        return stable


class SchmittTrigger:
    """
    Hysteresis thresholds to avoid rapid toggling near decision boundary.

    Once a category turns ON (confidence > on_threshold), it stays ON until
    confidence drops below off_threshold. This prevents UI flicker when
    confidence hovers around a single threshold.

    Args:
        on_threshold: Confidence required to activate (default 0.70).
        off_threshold: Confidence must drop below this to deactivate (default 0.40).
    """

    def __init__(self, on_threshold: float = 0.70, off_threshold: float = 0.40) -> None:
        self.on_threshold = on_threshold
        self.off_threshold = off_threshold
        self.active: Dict[str, bool] = {}

    def update(self, category: str, confidence: float) -> bool:
        currently_on = self.active.get(category, False)
        if currently_on:
            if confidence < self.off_threshold:
                self.active[category] = False
        else:
            if confidence > self.on_threshold:
                self.active[category] = True
        return self.active.get(category, False)


class MedianSmoother:
    """
    Median filter over recent frames for extra stability.

    More robust to outliers than mean averaging. Use when classification
    shows occasional spikes that pass through the confidence buffer.

    Args:
        window_size: Number of frames for median calculation (default 3).
    """

    def __init__(self, window_size: int = 3) -> None:
        self.window_size = window_size
        self.history: Dict[str, List[float]] = {}

    def smooth(self, detections: Mapping[str, float]) -> Dict[str, float]:
        smoothed: Dict[str, float] = {}
        for category, confidence in detections.items():
            if category not in self.history:
                self.history[category] = []
            self.history[category].append(confidence)
            if len(self.history[category]) > self.window_size:
                self.history[category].pop(0)
            smoothed[category] = float(np.median(self.history[category]))
        return smoothed


class AdaptiveDutyCycle:
    """
    Battery-aware interval selection for detection cadence.

    Reduces detection frequency when battery is low to extend battery life.
    At 20% battery, detection CPU is reduced by ~80% (3s -> 15s interval).

    Args:
        normal: Interval when battery >50% (default 3.0s).
        saving: Interval when battery 20-50% (default 8.0s).
        critical: Interval when battery <20% (default 15.0s).
    """

    def __init__(self, normal: float = 3.0, saving: float = 8.0, critical: float = 15.0) -> None:
        self.normal = normal
        self.saving = saving
        self.critical = critical

    def get_interval(self, battery_percent: int) -> float:
        if battery_percent > 50:
            return self.normal
        if battery_percent > 20:
            return self.saving
        return self.critical


# ------------------------------ main detector -------------------------------- #
@dataclass
class CategoryConfig:
    indices: Sequence[int]
    priority: str = "medium"
    color: str = "#FFFFFF"
    safety_override: bool = False


class SemanticDetective:
    """
    Wraps YAMNet inference and applies semantic mapping + smoothing.

    Typical use:
        detective = SemanticDetective()
        result = detective.classify(audio_chunk, sample_rate=48000)
    """

    def __init__(
        self,
        class_map_path: Path = DEFAULT_CLASS_MAP_PATH,
        model_handle: str = DEFAULT_MODEL_HANDLE,
        enable_median: bool = False,
    ) -> None:
        self.class_map_path = class_map_path
        self.model_handle = model_handle
        self.enable_median = enable_median

        self.model = hub.load(self.model_handle)
        self.categories = self._load_class_map(class_map_path)

        self.conf_buffer = ConfidenceBuffer()
        self.schmitt = SchmittTrigger()
        self.median = MedianSmoother() if enable_median else None

    # ------------------------------ public API -------------------------------- #
    def classify(self, audio: np.ndarray, sample_rate: int) -> Dict[str, Dict[str, float]]:
        """
        Run YAMNet classification on a ~3 second mono buffer.

        Returns a dictionary with raw scores, smoothed scores, stable flags, and
        hysteresis states suitable for UI display and automation logic.
        """
        waveform = self._prepare_audio(audio, sample_rate)
        scores, _, _ = self.model(waveform)
        mean_scores = tf.reduce_mean(scores, axis=0)  # (521,)
        mapped = self._map_to_categories(mean_scores)

        smoothed = self.median.smooth(mapped) if self.median else mapped
        stable = self.conf_buffer.update(smoothed)
        states = {cat: self.schmitt.update(cat, smoothed[cat]) for cat in smoothed}

        return {
            "raw": mapped,
            "smoothed": smoothed,
            "stable": stable,
            "states": states,
        }

    def get_top_detections(self, scores: Mapping[str, float], n: int = 3) -> List[Tuple[str, float]]:
        """Return top-N categories sorted by confidence."""
        sorted_pairs = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return sorted_pairs[:n]

    def check_safety_override(self, states: Mapping[str, bool]) -> bool:
        """Return True if any safety-critical category is active."""
        for category, cfg in self.categories.items():
            if cfg.safety_override and states.get(category):
                return True
        return False

    # ------------------------------ internal helpers -------------------------- #
    def _prepare_audio(self, audio: np.ndarray, sample_rate: int) -> tf.Tensor:
        """Convert audio to mono float32 tensor at 16 kHz expected by YAMNet."""
        if audio.size == 0:
            raise ValueError("Audio buffer is empty.")

        tensor = tf.convert_to_tensor(audio, dtype=tf.float32)
        if tensor.ndim == 2:
            tensor = tf.reduce_mean(tensor, axis=1)  # average channels
        elif tensor.ndim != 1:
            raise ValueError("Audio must be 1D or 2D (samples[, channels]).")

        if sample_rate != YAMNET_SAMPLE_RATE:
            num_samples = int(tensor.shape[0])
            target_samples = int(round(num_samples * YAMNET_SAMPLE_RATE / sample_rate))
            if target_samples == 0:
                raise ValueError(f"Audio too short to resample from {sample_rate} to {YAMNET_SAMPLE_RATE} Hz.")
            resampled = scipy_signal.resample(tensor.numpy(), target_samples)
            tensor = tf.convert_to_tensor(resampled, dtype=tf.float32)

        return tensor  # (T,) - YAMNet expects 1D waveform

    def _map_to_categories(self, yamnet_scores: tf.Tensor) -> Dict[str, float]:
        """Aggregate YAMNet 521-class scores into our semantic categories."""
        outputs: Dict[str, float] = {}
        for category, cfg in self.categories.items():
            idx_tensor = tf.constant(list(cfg.indices), dtype=tf.int32)
            selected = tf.gather(yamnet_scores, idx_tensor)
            outputs[category] = float(tf.reduce_mean(selected).numpy())
        return outputs

    def _load_class_map(self, path: Path) -> Dict[str, CategoryConfig]:
        if not path.exists():
            raise FileNotFoundError(f"Class map not found at {path}")
        with path.open("r") as f:
            data = yaml.safe_load(f) or {}
        categories = data.get("categories", {})
        parsed: Dict[str, CategoryConfig] = {}
        for name, cfg in categories.items():
            parsed[name] = CategoryConfig(
                indices=cfg.get("indices", []),
                priority=cfg.get("priority", "medium"),
                color=cfg.get("color", "#FFFFFF"),
                safety_override=cfg.get("safety_override", False),
            )
        return parsed


__all__ = [
    "SemanticDetective",
    "ConfidenceBuffer",
    "SchmittTrigger",
    "MedianSmoother",
    "AdaptiveDutyCycle",
    "CategoryConfig",
    "YAMNET_SAMPLE_RATE",
]
