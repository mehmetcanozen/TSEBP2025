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
from typing import Dict, List, Mapping, Sequence, Tuple, Union

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import torch
import torchaudio
import yaml

from ai.ai_runtime.utils.paths import get_config_path, get_models_checkpoints_path

logger = logging.getLogger(__name__)

YAMNET_SAMPLE_RATE = 16000
DEFAULT_CLASS_MAP_PATH = get_config_path("yamnet_class_map.yaml")
DEFAULT_MODEL_HANDLE = "https://tfhub.dev/google/yamnet/1"


class ConfidenceBuffer:
    """
    Rolling majority voting buffer to stabilize transient detections.

    Prevents false positives from single-frame spikes by requiring
    detection in at least a majority of the last N frames
    (2-of-3 behavior when window_size=3).
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
            stable[category] = hits >= (self.window_size + 1) // 2
        return stable


class SchmittTrigger:
    """
    Hysteresis thresholds to avoid rapid toggling near decision boundary.
    """

    def __init__(self, on_threshold: float = 0.70, off_threshold: float = 0.40) -> None:
        if on_threshold <= off_threshold:
            raise ValueError(
                f"on_threshold ({on_threshold}) must be greater than off_threshold ({off_threshold})"
            )
        self.on_threshold = on_threshold
        self.off_threshold = off_threshold
        self.active: Dict[str, bool] = {}

    def update(self, category: str, confidence: float) -> bool:
        currently_on = self.active.get(category, False)
        if currently_on:
            if confidence < self.off_threshold:
                self.active[category] = False
        elif confidence > self.on_threshold:
            self.active[category] = True
        return self.active.get(category, False)


class MedianSmoother:
    """Median filter over recent frames for extra stability."""

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
    """Battery-aware interval selection for detection cadence."""

    def __init__(self, normal: float = 3.0, saving: float = 8.0, critical: float = 15.0) -> None:
        self.normal = normal
        self.saving = saving
        self.critical = critical

    def get_interval(self, battery_percent: int) -> float:
        battery_percent = max(0, min(100, battery_percent))
        if battery_percent >= 50:
            return self.normal
        if battery_percent >= 20:
            return self.saving
        return self.critical


@dataclass
class CategoryConfig:
    indices: Sequence[int]
    priority: str = "medium"
    color: str = "#FFFFFF"
    reduce_type: str = "max"


class SemanticDetective:
    """Wraps YAMNet inference and applies semantic mapping + smoothing."""

    def __init__(
        self,
        class_map_path: Path = DEFAULT_CLASS_MAP_PATH,
        model_handle: str = DEFAULT_MODEL_HANDLE,
        enable_median: bool = False,
    ) -> None:
        self.class_map_path = class_map_path
        self.model_handle = model_handle
        self.enable_median = enable_median

        local_yamnet = get_models_checkpoints_path() / "yamnet_1"
        if local_yamnet.exists() and (local_yamnet / "saved_model.pb").exists():
            logger.info("Loading YAMNet from local directory: %s", local_yamnet)
            self.model = hub.load(str(local_yamnet))
        else:
            logger.info("Loading YAMNet from %s...", self.model_handle)
            self.model = hub.load(self.model_handle)
        self.categories = self._load_class_map(class_map_path)

        self.conf_buffer = ConfidenceBuffer()
        self.schmitt = SchmittTrigger()
        self.median = MedianSmoother() if enable_median else None
        self._resampler_cache = {}

    def classify(self, audio: np.ndarray, sample_rate: int) -> Dict[str, Mapping[str, Union[float, bool]]]:
        waveform = self._prepare_audio(audio, sample_rate)
        scores, _, _ = self.model(waveform)
        max_scores = tf.reduce_max(scores, axis=0)
        mapped = self._map_to_categories(max_scores)

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
        sorted_pairs = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return sorted_pairs[:n]

    def _prepare_audio(self, audio: np.ndarray, sample_rate: int) -> tf.Tensor:
        if audio.size == 0:
            raise ValueError("Audio buffer is empty.")

        if audio.ndim == 2:
            audio_mono = np.mean(audio, axis=1)
        elif audio.ndim == 1:
            audio_mono = audio
        else:
            raise ValueError("Audio must be 1D or 2D (samples[, channels]).")

        if sample_rate != YAMNET_SAMPLE_RATE:
            if sample_rate not in self._resampler_cache:
                self._resampler_cache[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate,
                    new_freq=YAMNET_SAMPLE_RATE,
                )
            torch_audio = torch.from_numpy(audio_mono).to(torch.float32)
            torch_resampled = self._resampler_cache[sample_rate](torch_audio)
            audio_mono = torch_resampled.numpy()

        return tf.convert_to_tensor(audio_mono, dtype=tf.float32)

    def _map_to_categories(self, yamnet_scores: tf.Tensor) -> Dict[str, float]:
        scores_np = yamnet_scores.numpy()
        outputs: Dict[str, float] = {}
        for category, cfg in self.categories.items():
            if not cfg.indices:
                outputs[category] = 0.0
                continue
            selected = scores_np[self._index_arrays[category]]
            if cfg.reduce_type == "mean":
                outputs[category] = float(np.mean(selected))
            else:
                outputs[category] = float(np.max(selected))
        return outputs

    def _load_class_map(self, path: Path) -> Dict[str, CategoryConfig]:
        if not path.exists():
            raise FileNotFoundError(f"Class map not found at {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        categories = data.get("categories", {})
        parsed: Dict[str, CategoryConfig] = {}
        self._index_arrays: Dict[str, np.ndarray] = {}
        for name, cfg in categories.items():
            indices = cfg.get("indices", [])
            if not all(0 <= i <= 520 for i in indices):
                raise ValueError(f"Category '{name}' contains invalid YAMNet indices (must be 0-520).")
            parsed[name] = CategoryConfig(
                indices=indices,
                priority=cfg.get("priority", "medium"),
                color=cfg.get("color", "#FFFFFF"),
                reduce_type=cfg.get("reduce_type", "max"),
            )
            self._index_arrays[name] = np.array(indices, dtype=np.intp)
        return parsed


__all__ = [
    "AdaptiveDutyCycle",
    "CategoryConfig",
    "ConfidenceBuffer",
    "MedianSmoother",
    "SchmittTrigger",
    "SemanticDetective",
    "YAMNET_SAMPLE_RATE",
]
