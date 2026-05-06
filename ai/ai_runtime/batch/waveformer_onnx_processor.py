"""Batch-style adapter for the packaged Waveformer ONNX runtime."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ai.ai_runtime.separation.waveformer_onnx_stream import WaveformerOnnxStream
from ai.ai_runtime.utils.paths import get_waveformer_model_package_path


def _rms(audio: np.ndarray) -> float:
    array = np.asarray(audio, dtype=np.float64)
    if array.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(array))))


def _db_ratio(numerator: float, denominator: float) -> float:
    if numerator <= 0.0 and denominator <= 0.0:
        return 0.0
    return float(20.0 * math.log10((numerator + 1.0e-12) / (denominator + 1.0e-12)))


def _mono(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float64)
    if array.ndim == 1:
        return array
    return np.mean(array, axis=1)


def _project_residual_back(original: np.ndarray, residual_mono: np.ndarray) -> np.ndarray:
    original = np.asarray(original, dtype=np.float32)
    residual = np.asarray(residual_mono, dtype=np.float32)
    length = min(original.shape[0], residual.shape[0])
    cleaned = original.copy()
    if original.ndim == 1:
        cleaned[:length] = cleaned[:length] - residual[:length]
    else:
        cleaned[:length, :] = cleaned[:length, :] - residual[:length, None]
    return np.clip(cleaned, -1.0, 1.0)


class WaveformerOnnxBatchProcessor:
    """BatchProcessor-shaped wrapper around the desktop Waveformer ONNX graph."""

    def __init__(self) -> None:
        self.runner = WaveformerOnnxStream(get_waveformer_model_package_path())

    def process_file(
        self,
        *,
        input_path: Path,
        output_path: Path,
        suppress_categories: list[str],
        chunk_size_seconds: float,
        detection_threshold: float,
        aggressiveness: float,
        universal_prompts: list[str],
        output_noise: bool,
        **_: Any,
    ) -> dict[str, Any]:
        del chunk_size_seconds, detection_threshold, universal_prompts
        targets = suppress_categories or ["dog"]
        audio, sample_rate = sf.read(input_path, dtype="float32")
        cleaned_mono, runtime_stats = self.runner.suppress(
            audio,
            int(sample_rate),
            targets,
            aggressiveness=aggressiveness,
        )
        original_mono = _mono(np.asarray(audio, dtype=np.float32))
        residual = original_mono[: cleaned_mono.shape[0]] - cleaned_mono
        cleaned = _project_residual_back(np.asarray(audio, dtype=np.float32), residual)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, cleaned, int(sample_rate))

        stats = {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "sample_rate": int(sample_rate),
            "duration_seconds": float(original_mono.shape[0] / max(float(sample_rate), 1.0)),
            "rms_reduction_db": _db_ratio(_rms(original_mono), _rms(cleaned_mono)),
            "noise_audio": residual.astype(np.float32) if output_noise else None,
            "suppressed_categories": list(targets),
        }
        stats.update(runtime_stats)
        return stats
