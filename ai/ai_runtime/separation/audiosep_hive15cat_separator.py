"""
ONNX wrapper for the exact-15 AudioSepHive15Cat separator.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np
import yaml
from scipy import signal as scipy_signal

from ai.ai_runtime.utils import audio_utils
from ai.ai_runtime.utils.paths import (
    get_audiosep_hive15cat_categories_path,
    get_audiosep_hive15cat_model_path,
    get_audiosep_hive15cat_onnx_path,
)

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 32000
SEGMENT_SECONDS = 5.0
SEGMENT_SAMPLES = int(TARGET_SAMPLE_RATE * SEGMENT_SECONDS)
OVERLAP_SECONDS = 1.0
OVERLAP_SAMPLES = int(TARGET_SAMPLE_RATE * OVERLAP_SECONDS)


class AudioSepHive15CatSeparator:
    """Inference wrapper for the exact-15 fixed-category AudioSep ONNX export."""

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        categories_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
    ) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError(
                "onnxruntime is required for AudioSepHive15Cat ONNX inference. "
                "Install with: pip install onnxruntime"
            ) from exc

        model_candidate = Path(model_path) if model_path else get_audiosep_hive15cat_onnx_path()
        if model_candidate.is_dir():
            self.model_dir = model_candidate
            self.model_path = model_candidate / "frozensep_hive_15cat.onnx"
        else:
            self.model_path = model_candidate
            self.model_dir = model_candidate.parent if model_candidate.parent else get_audiosep_hive15cat_model_path()

        if not self.model_path.exists():
            raise FileNotFoundError(f"AudioSepHive15Cat ONNX model not found: {self.model_path}")

        self.categories_yaml_path = (
            Path(categories_path) if categories_path else get_audiosep_hive15cat_categories_path()
        )
        self.categories_txt_path = self.model_dir / "categories_15.txt"
        metadata, self.categories = self._load_categories()
        self._category_lookup = {
            str(label).strip().casefold(): index
            for index, label in enumerate(self.categories)
        }

        self.sample_rate = int(metadata.get("sample_rate", TARGET_SAMPLE_RATE) or TARGET_SAMPLE_RATE)
        self.segment_seconds = float(metadata.get("segment_seconds", SEGMENT_SECONDS) or SEGMENT_SECONDS)
        self.segment_samples = max(1, int(round(self.sample_rate * self.segment_seconds)))
        self.overlap_samples = min(
            int(round(self.sample_rate * OVERLAP_SECONDS)),
            max(0, self.segment_samples - 1),
        )

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4
        providers = self._resolve_providers(ort, device)
        self._session = ort.InferenceSession(
            str(self.model_path),
            sess_options=sess_options,
            providers=providers,
        )
        logger.info(
            "AudioSepHive15Cat ONNX initialized from %s with providers: %s",
            self.model_path,
            self._session.get_providers(),
        )

    @staticmethod
    def _resolve_providers(ort, device: Optional[str]) -> list[str]:
        available = set(ort.get_available_providers())
        requested = (device or "").strip().casefold()
        providers: list[str] = []
        if requested.startswith("cuda"):
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
        else:
            if "TensorrtExecutionProvider" in available:
                providers.append("TensorrtExecutionProvider")
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        return [provider for provider in providers if provider in available]

    def _load_categories(self) -> tuple[dict, list[str]]:
        metadata: dict = {}
        categories_from_yaml: list[str] = []
        if self.categories_yaml_path.exists():
            with self.categories_yaml_path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
            metadata = dict(payload)
            categories_from_yaml = [
                str(value).strip()
                for value in list(payload.get("categories") or [])
                if str(value).strip()
            ]

        categories_from_txt: list[str] = []
        if self.categories_txt_path.exists():
            categories_from_txt = [
                line.strip()
                for line in self.categories_txt_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        categories = categories_from_yaml or categories_from_txt
        if not categories:
            raise FileNotFoundError(
                "AudioSepHive15Cat categories are missing. Expected categories_15.yaml or categories_15.txt."
            )
        if categories_from_yaml and categories_from_txt and categories_from_yaml != categories_from_txt:
            raise ValueError(
                "AudioSepHive15Cat category catalogs disagree between YAML and TXT assets."
            )
        return metadata, categories

    def resolve_category(self, category: str) -> int:
        key = str(category).strip().casefold()
        if key not in self._category_lookup:
            raise ValueError(
                f"Unknown AudioSepHive15Cat category '{category}'. "
                f"Valid: {', '.join(self.categories)}"
            )
        return int(self._category_lookup[key])

    def resolve_categories(
        self,
        categories: Union[str, Sequence[str]],
    ) -> list[tuple[str, int]]:
        if isinstance(categories, str):
            values = [categories]
        else:
            values = list(categories)
        resolved: list[tuple[str, int]] = []
        seen: set[int] = set()
        for category in values:
            category_index = self.resolve_category(category)
            if category_index in seen:
                continue
            seen.add(category_index)
            resolved.append((self.categories[category_index], category_index))
        return resolved

    @staticmethod
    def _normalize_audio_shape(audio: np.ndarray) -> tuple[np.ndarray, dict[str, int | bool | float]]:
        array = np.asarray(audio, dtype=np.float32)
        if array.ndim == 1:
            mono = array
            metadata = {
                "original_length": int(array.shape[0]),
                "channel_count": 1,
                "channel_first": False,
            }
        elif array.ndim == 2:
            channel_first = array.shape[0] <= 8 and array.shape[0] < array.shape[1]
            time_major = array.transpose(1, 0) if channel_first else array
            mono = np.mean(time_major, axis=1, dtype=np.float32)
            metadata = {
                "original_length": int(time_major.shape[0]),
                "channel_count": int(time_major.shape[1]),
                "channel_first": bool(channel_first),
            }
        else:
            raise ValueError(f"Expected 1D or 2D audio input, got {array.ndim}D")

        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        metadata["scale"] = max(1.0, peak)
        return mono.astype(np.float32, copy=False), metadata

    @staticmethod
    def _restore_shape(
        mono_audio: np.ndarray,
        metadata: dict[str, int | bool | float],
    ) -> np.ndarray:
        scaled = np.asarray(mono_audio, dtype=np.float32) * float(metadata["scale"])
        target_length = int(metadata["original_length"])
        scaled = audio_utils.enforce_length(scaled, target_length)
        channel_count = int(metadata["channel_count"])
        if channel_count <= 1:
            return scaled.astype(np.float32, copy=False)

        repeated = np.repeat(scaled[:, np.newaxis], channel_count, axis=1)
        if bool(metadata["channel_first"]):
            return repeated.transpose(1, 0).astype(np.float32, copy=False)
        return repeated.astype(np.float32, copy=False)

    @staticmethod
    def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        if source_rate == target_rate:
            return np.asarray(audio, dtype=np.float32)
        factor = math.gcd(int(source_rate), int(target_rate))
        up = target_rate // factor
        down = source_rate // factor
        return scipy_signal.resample_poly(
            np.asarray(audio, dtype=np.float32),
            up,
            down,
        ).astype(np.float32, copy=False)

    def _run_window(self, chunk: np.ndarray, category_idx: int) -> np.ndarray:
        valid_length = int(chunk.shape[0])
        if valid_length < self.segment_samples:
            padded = np.zeros(self.segment_samples, dtype=np.float32)
            padded[:valid_length] = chunk
        else:
            padded = np.asarray(chunk[: self.segment_samples], dtype=np.float32)

        outputs = self._session.run(
            None,
            {
                "mixture": padded.reshape(1, 1, -1).astype(np.float32, copy=False),
                "category_idx": np.asarray([category_idx], dtype=np.int64),
            },
        )
        separated = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        return separated[:valid_length]

    def _build_overlap_window(
        self,
        length: int,
        *,
        fade_in: bool,
        fade_out: bool,
    ) -> np.ndarray:
        window = np.ones(length, dtype=np.float32)
        overlap = min(length, self.overlap_samples)
        if overlap <= 0:
            return window

        ramp = np.linspace(0.0, 1.0, overlap, endpoint=False, dtype=np.float32)
        if fade_in:
            window[:overlap] = ramp
        if fade_out:
            window[-overlap:] = np.minimum(window[-overlap:], 1.0 - ramp)
        return window

    def _separate_resampled_category(
        self,
        audio: np.ndarray,
        category_idx: int,
    ) -> np.ndarray:
        if audio.size == 0:
            return np.zeros_like(audio, dtype=np.float32)
        if audio.shape[0] <= self.segment_samples:
            return self._run_window(audio, category_idx)

        step = max(1, self.segment_samples - self.overlap_samples)
        separated = np.zeros_like(audio, dtype=np.float32)
        weight_sum = np.zeros_like(audio, dtype=np.float32)

        for start in range(0, audio.shape[0], step):
            end = min(start + self.segment_samples, audio.shape[0])
            chunk = audio[start:end]
            if chunk.size == 0:
                continue
            chunk_output = self._run_window(chunk, category_idx)
            window = self._build_overlap_window(
                len(chunk_output),
                fade_in=start > 0,
                fade_out=end < audio.shape[0],
            )
            separated[start:end] += chunk_output * window
            weight_sum[start:end] += window
            if end >= audio.shape[0]:
                break

        return separated / np.maximum(weight_sum, 1.0e-8)

    def separate(
        self,
        audio: np.ndarray,
        sample_rate: int,
        categories: Union[str, Sequence[str]],
    ) -> np.ndarray:
        resolved = self.resolve_categories(categories)
        mono_audio, metadata = self._normalize_audio_shape(audio)
        scaled_mono = np.clip(
            mono_audio / float(metadata["scale"]),
            -1.0,
            1.0,
        ).astype(np.float32, copy=False)

        resampled = self._resample(scaled_mono, sample_rate, self.sample_rate)
        separated_resampled = np.zeros_like(resampled, dtype=np.float32)
        for _, category_idx in resolved:
            separated_resampled += self._separate_resampled_category(resampled, category_idx)

        separated = self._resample(separated_resampled, self.sample_rate, sample_rate)
        separated = audio_utils.enforce_length(separated, int(metadata["original_length"]))
        return self._restore_shape(separated, metadata)


__all__ = [
    "AudioSepHive15CatSeparator",
    "OVERLAP_SAMPLES",
    "SEGMENT_SAMPLES",
    "TARGET_SAMPLE_RATE",
]
