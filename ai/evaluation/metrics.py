"""Signal metrics for AI model evaluation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ai.evaluation.contracts import AdapterResult, EvalCase


EPSILON = 1.0e-9


def _mono(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        return array
    return np.mean(array, axis=1).astype(np.float32, copy=False)


def _resample_linear(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if array.size == 0 or source_rate == target_rate:
        return array.copy()
    target_len = max(1, int(round(array.shape[0] * target_rate / float(source_rate))))
    source_positions = np.arange(array.shape[0], dtype=np.float64)
    target_positions = np.linspace(0, array.shape[0] - 1, target_len, dtype=np.float64)
    return np.interp(target_positions, source_positions, array).astype(np.float32)


def _fit_length(audio: np.ndarray, length: int) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if array.shape[0] >= length:
        return array[:length]
    if array.size == 0:
        return np.zeros((length,), dtype=np.float32)
    return np.pad(array, (0, length - array.shape[0]), mode="constant").astype(np.float32)


def load_mono(path: Path, target_rate: int | None = None) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, dtype="float32")
    mono = _mono(audio)
    if target_rate is not None and int(sample_rate) != int(target_rate):
        mono = _resample_linear(mono, int(sample_rate), int(target_rate))
        sample_rate = int(target_rate)
    return mono.astype(np.float32, copy=False), int(sample_rate)


def rms(audio: np.ndarray) -> float:
    array = np.asarray(audio, dtype=np.float32)
    if array.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(array), dtype=np.float64)))


def dbfs(audio: np.ndarray) -> float:
    value = rms(audio)
    return float(20.0 * math.log10(max(value, EPSILON)))


def db_ratio(numerator: float, denominator: float) -> float:
    return float(20.0 * math.log10(max(numerator, EPSILON) / max(denominator, EPSILON)))


def snr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    reference = np.asarray(reference, dtype=np.float64).reshape(-1)
    estimate = _fit_length(estimate, len(reference)).astype(np.float64)
    noise = reference - estimate
    return float(10.0 * math.log10((np.sum(reference * reference) + EPSILON) / (np.sum(noise * noise) + EPSILON)))


def si_sdr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    reference = np.asarray(reference, dtype=np.float64).reshape(-1)
    estimate = _fit_length(estimate, len(reference)).astype(np.float64)
    if reference.size == 0 or estimate.size == 0:
        return float("nan")
    reference = reference - np.mean(reference)
    estimate = estimate - np.mean(estimate)
    reference_energy = float(np.sum(reference * reference)) + EPSILON
    projection = np.sum(estimate * reference) * reference / reference_energy
    noise = estimate - projection
    return float(10.0 * math.log10((np.sum(projection * projection) + EPSILON) / (np.sum(noise * noise) + EPSILON)))


def correlation(a: np.ndarray, b: np.ndarray) -> float:
    length = min(len(a), len(b))
    if length <= 1:
        return float("nan")
    a = np.asarray(a[:length], dtype=np.float64)
    b = np.asarray(b[:length], dtype=np.float64)
    if float(np.std(a)) < EPSILON or float(np.std(b)) < EPSILON:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def clipping_rate(audio: np.ndarray, threshold: float = 0.999) -> float:
    array = np.asarray(audio, dtype=np.float32)
    if array.size == 0:
        return 0.0
    return float(np.mean(np.abs(array) >= float(threshold)))


def spectral_centroid(audio: np.ndarray, sample_rate: int) -> float:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    if array.size == 0:
        return 0.0
    spectrum = np.abs(np.fft.rfft(array))
    freqs = np.fft.rfftfreq(array.shape[0], d=1.0 / max(float(sample_rate), 1.0))
    weight = float(np.sum(spectrum)) + EPSILON
    return float(np.sum(freqs * spectrum) / weight)


def optional_speech_metrics(
    clean_reference: np.ndarray,
    clean_output: np.ndarray,
    sample_rate: int,
) -> dict[str, float | str]:
    """Return PESQ/STOI when local optional packages are installed."""

    metrics: dict[str, float | str] = {}
    try:
        from pesq import pesq  # type: ignore

        mode = "wb" if sample_rate >= 16000 else "nb"
        metrics["pesq"] = float(pesq(sample_rate, clean_reference, clean_output, mode))
    except Exception as exc:  # pragma: no cover - optional local dependency
        metrics["pesq"] = float("nan")
        metrics["pesq_status"] = f"unavailable: {type(exc).__name__}"

    try:
        from pystoi import stoi  # type: ignore

        metrics["stoi"] = float(stoi(clean_reference, clean_output, sample_rate, extended=False))
    except Exception as exc:  # pragma: no cover - optional local dependency
        metrics["stoi"] = float("nan")
        metrics["stoi_status"] = f"unavailable: {type(exc).__name__}"
    return metrics


def compute_case_metrics(
    *,
    case: EvalCase,
    result: AdapterResult,
    model_id: str,
    repeat_index: int,
    end_to_end_seconds: float,
    status: str,
) -> dict[str, Any]:
    mixture, sample_rate = load_mono(case.input_path)
    clean_output, _ = load_mono(result.clean_path, sample_rate)
    removed_output, _ = load_mono(result.removed_path, sample_rate)
    length = min(len(mixture), len(clean_output), len(removed_output))
    mixture = _fit_length(mixture, length)
    clean_output = _fit_length(clean_output, length)
    removed_output = _fit_length(removed_output, length)

    duration_seconds = length / max(float(sample_rate), 1.0)
    row: dict[str, Any] = {
        "model": model_id,
        "case_id": case.case_id,
        "tier": case.tier,
        "primary_ranking": bool(case.primary_ranking),
        "repeat": int(repeat_index),
        "status": status,
        "target": result.metadata.get("target", ""),
        "duration_seconds": duration_seconds,
        "end_to_end_seconds": float(end_to_end_seconds),
        "real_time_factor": float(end_to_end_seconds / max(duration_seconds, EPSILON)),
        "output_rms_dbfs": dbfs(clean_output),
        "input_rms_dbfs": dbfs(mixture),
        "removed_rms_dbfs": dbfs(removed_output),
        "rms_reduction_db": db_ratio(rms(mixture), rms(clean_output)),
        "peak_abs": float(np.max(np.abs(clean_output))) if clean_output.size else 0.0,
        "clipping_rate": clipping_rate(clean_output),
        "removed_energy_ratio": float((rms(removed_output) ** 2) / max(rms(mixture) ** 2, EPSILON)),
        "spectral_centroid_input_hz": spectral_centroid(mixture, sample_rate),
        "spectral_centroid_output_hz": spectral_centroid(clean_output, sample_rate),
        "dnsmos_ovrl": float("nan"),
        "dnsmos_status": "not_configured",
    }
    row["spectral_centroid_delta_hz"] = (
        row["spectral_centroid_output_hz"] - row["spectral_centroid_input_hz"]
    )

    if case.clean_reference_path and case.clean_reference_path.exists():
        clean_reference, _ = load_mono(case.clean_reference_path, sample_rate)
        clean_reference = _fit_length(clean_reference, length)
        input_clean_sisdr = si_sdr_db(clean_reference, mixture)
        output_clean_sisdr = si_sdr_db(clean_reference, clean_output)
        row.update(
            {
                "input_clean_si_sdr_db": input_clean_sisdr,
                "clean_si_sdr_db": output_clean_sisdr,
                "clean_si_sdr_improvement_db": output_clean_sisdr - input_clean_sisdr,
                "clean_snr_db": snr_db(clean_reference, clean_output),
                "preservation_ratio": float(rms(clean_output) / max(rms(clean_reference), EPSILON)),
            }
        )
        if case.speech_reference:
            row.update(optional_speech_metrics(clean_reference, clean_output, sample_rate))
    else:
        row.update(
            {
                "input_clean_si_sdr_db": float("nan"),
                "clean_si_sdr_db": float("nan"),
                "clean_si_sdr_improvement_db": float("nan"),
                "clean_snr_db": float("nan"),
                "preservation_ratio": float("nan"),
            }
        )

    if case.unwanted_reference_path and case.unwanted_reference_path.exists():
        unwanted_reference, _ = load_mono(case.unwanted_reference_path, sample_rate)
        unwanted_reference = _fit_length(unwanted_reference, length)
        row.update(
            {
                "removed_unwanted_si_sdr_db": si_sdr_db(unwanted_reference, removed_output),
                "input_unwanted_si_sdr_db": si_sdr_db(unwanted_reference, mixture),
                "residual_unwanted_correlation": correlation(unwanted_reference, clean_output),
                "removed_unwanted_correlation": correlation(unwanted_reference, removed_output),
            }
        )
    else:
        row.update(
            {
                "removed_unwanted_si_sdr_db": float("nan"),
                "input_unwanted_si_sdr_db": float("nan"),
                "residual_unwanted_correlation": float("nan"),
                "removed_unwanted_correlation": float("nan"),
            }
        )

    return row
