"""Stateful Waveformer ONNX runner used for desktop-export validation.

The desktop runtime consumes a streaming ONNX graph rather than the legacy
PyTorch separator. This module mirrors that contract in Python so export audits
and comparison runs exercise the same tensor surface as the Tauri app.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from ai.ai_runtime.utils.paths import get_waveformer_model_path


DEFAULT_MODEL_PACKAGE = get_waveformer_model_path() / "model_package.json"


@dataclass(frozen=True)
class WaveformerOnnxPackage:
    package_path: Path
    model_path: Path
    metadata_paths: tuple[Path, ...]
    sample_rate: int
    chunk_samples: int
    mix_channels: int
    categories: tuple[str, ...]
    state_tensors: dict[str, tuple[int, ...]]


class WaveformerOnnxStream:
    """Small stateful adapter for the bundled Waveformer desktop ONNX export."""

    input_names = ("mixture", "label_vector", "enc_buf", "dec_buf", "out_buf")
    output_names = ("target_chunk", "enc_buf_out", "dec_buf_out", "out_buf_out")

    def __init__(
        self,
        model_package_path: str | Path = DEFAULT_MODEL_PACKAGE,
        providers: Iterable[str] | None = None,
        platform: str = "desktop",
        package: WaveformerOnnxPackage | None = None,
    ) -> None:
        self.package = package or load_package(model_package_path, platform=platform)
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - exercised by environment
            raise ImportError("onnxruntime is required for Waveformer ONNX validation.") from exc

        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        requested_providers = list(providers or ["CPUExecutionProvider"])
        self.session = ort.InferenceSession(
            str(self.package.model_path),
            sess_options=session_options,
            providers=requested_providers,
        )
        self.active_providers = tuple(self.session.get_providers())

    @property
    def categories(self) -> tuple[str, ...]:
        return self.package.categories

    def category_index(self, category: str) -> int:
        normalized = category.strip().casefold().replace(" ", "_").replace("-", "_")
        aliases = {
            "pets": "dog",
            "dog_barking": "dog",
            "barking": "dog",
            "typing": "computer_typing",
            "keyboard_typing": "computer_typing",
            "door_knocking": "door_knock",
            "bird_singing": "birds_chirping",
            "birds": "birds_chirping",
            "alarm": "alarm_clock",
        }
        normalized = aliases.get(normalized, normalized)
        try:
            return self.package.categories.index(normalized)
        except ValueError as exc:
            raise ValueError(
                f"unknown Waveformer ONNX category '{category}'. "
                f"Known ids: {', '.join(self.package.categories)}"
            ) from exc

    def new_state(self) -> dict[str, np.ndarray]:
        return {
            name: np.zeros(shape, dtype=np.float32)
            for name, shape in self.package.state_tensors.items()
        }

    def audit_contract(self, check_onnx: bool = True) -> dict[str, Any]:
        errors: list[str] = []
        actual_inputs = {
            item.name: {
                "shape": [int(dim) if isinstance(dim, int) else dim for dim in item.shape],
                "dtype": item.type,
            }
            for item in self.session.get_inputs()
        }
        actual_outputs = [item.name for item in self.session.get_outputs()]
        expected_inputs = self.expected_input_contract()
        expected_outputs = list(self.output_names)

        for name, expected in expected_inputs.items():
            actual = actual_inputs.get(name)
            if actual is None:
                errors.append(f"missing input '{name}'")
                continue
            if _shape_values(actual["shape"]) != expected["shape"]:
                errors.append(
                    f"input '{name}' shape mismatch: expected {expected['shape']} got {actual['shape']}"
                )

        for name in expected_outputs:
            if name not in actual_outputs:
                errors.append(f"missing output '{name}'")

        onnx_check = {"available": False, "ok": None, "error": None, "opsets": []}
        if check_onnx:
            try:
                import onnx

                model = onnx.load(str(self.package.model_path))
                onnx.checker.check_model(model)
                onnx_check = {
                    "available": True,
                    "ok": True,
                    "error": None,
                    "opsets": [
                        {"domain": item.domain or "ai.onnx", "version": int(item.version)}
                        for item in model.opset_import
                    ],
                }
            except Exception as exc:  # pragma: no cover - depends on optional package
                onnx_check = {
                    "available": True,
                    "ok": False,
                    "error": repr(exc),
                    "opsets": [],
                }
                errors.append(f"onnx checker failed: {exc!r}")

        return {
            "model_path": str(self.package.model_path),
            "metadata_paths": [str(path) for path in self.package.metadata_paths],
            "providers": list(self.active_providers),
            "sample_rate": self.package.sample_rate,
            "chunk_samples": self.package.chunk_samples,
            "chunk_ms": self.package.chunk_samples / self.package.sample_rate * 1000.0,
            "mix_channels": self.package.mix_channels,
            "category_count": len(self.package.categories),
            "expected_inputs": expected_inputs,
            "actual_inputs": actual_inputs,
            "expected_outputs": expected_outputs,
            "actual_outputs": actual_outputs,
            "onnx_check": onnx_check,
            "ok": not errors,
            "errors": errors,
        }

    def expected_input_contract(self) -> dict[str, dict[str, Any]]:
        return {
            "mixture": {
                "shape": [1, self.package.mix_channels, self.package.chunk_samples],
                "dtype": "float32",
            },
            "label_vector": {"shape": [1, len(self.package.categories)], "dtype": "float32"},
            "enc_buf": {
                "shape": list(self.package.state_tensors["enc_buf"]),
                "dtype": "float32",
            },
            "dec_buf": {
                "shape": list(self.package.state_tensors["dec_buf"]),
                "dtype": "float32",
            },
            "out_buf": {
                "shape": list(self.package.state_tensors["out_buf"]),
                "dtype": "float32",
            },
        }

    def run_chunk(
        self,
        chunk: np.ndarray,
        category_index: int,
        state: dict[str, np.ndarray],
    ) -> np.ndarray:
        mono = np.asarray(chunk, dtype=np.float32).reshape(-1)
        valid_length = min(int(mono.shape[0]), self.package.chunk_samples)
        padded = np.zeros((self.package.chunk_samples,), dtype=np.float32)
        if valid_length:
            padded[:valid_length] = mono[:valid_length]

        mixture = np.tile(padded[None, None, :], (1, self.package.mix_channels, 1))
        label = np.zeros((1, len(self.package.categories)), dtype=np.float32)
        label[0, category_index] = 1.0

        outputs = self.session.run(
            list(self.output_names),
            {
                "mixture": mixture,
                "label_vector": label,
                "enc_buf": state["enc_buf"],
                "dec_buf": state["dec_buf"],
                "out_buf": state["out_buf"],
            },
        )
        state["enc_buf"] = np.asarray(outputs[1], dtype=np.float32)
        state["dec_buf"] = np.asarray(outputs[2], dtype=np.float32)
        state["out_buf"] = np.asarray(outputs[3], dtype=np.float32)

        target = np.asarray(outputs[0], dtype=np.float32).reshape(
            self.package.mix_channels,
            self.package.chunk_samples,
        )
        return target[:, :valid_length].mean(axis=0)

    def suppress(
        self,
        audio: np.ndarray,
        sample_rate: int,
        categories: Iterable[str],
        aggressiveness: float = 1.0,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        mono = _mono(np.asarray(audio, dtype=np.float32))
        if mono.size == 0:
            return mono, {"real_time_factor": 0.0, "processing_seconds": 0.0}

        peak = max(float(np.max(np.abs(mono))), 1.0)
        clean = _resample_linear(mono / peak, sample_rate, self.package.sample_rate)
        start = time.perf_counter()

        category_ids = list(categories)
        for category_id in category_ids:
            category_index = self.category_index(category_id)
            state = self.new_state()
            scale = float(np.clip(aggressiveness, 0.5, 2.0))
            out = np.zeros_like(clean)
            cursor = 0
            while cursor < max(int(clean.shape[0]), 1):
                end = min(cursor + self.package.chunk_samples, int(clean.shape[0]))
                target = self.run_chunk(clean[cursor:end], category_index, state)
                out[cursor:end] = np.clip(clean[cursor:end] - scale * target, -1.0, 1.0)
                if end >= clean.shape[0]:
                    break
                cursor = end
            clean = out

        processing_seconds = time.perf_counter() - start
        clean = _resample_linear(clean, self.package.sample_rate, sample_rate)
        clean = _fit_length(clean, mono.shape[0])
        clean = np.nan_to_num(clean * peak, copy=False).astype(np.float32)
        clean = np.clip(clean, -1.0, 1.0)
        duration_seconds = mono.shape[0] / max(float(sample_rate), 1.0)
        return clean, {
            "processing_seconds": processing_seconds,
            "duration_seconds": duration_seconds,
            "real_time_factor": processing_seconds / max(duration_seconds, 1.0e-12),
            "categories": category_ids,
            "mode": "offline_resampled_stream",
        }

    def suppress_live_chunks(
        self,
        audio: np.ndarray,
        sample_rate: int,
        categories: Iterable[str],
        aggressiveness: float = 1.0,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        mono = _mono(np.asarray(audio, dtype=np.float32))
        if mono.size == 0:
            return mono, {"real_time_factor": 0.0, "processing_seconds": 0.0}

        category_ids = list(categories)
        category_indices = [self.category_index(category_id) for category_id in category_ids]
        states = [self.new_state() for _ in category_indices]
        scale = float(np.clip(aggressiveness, 0.5, 2.0))
        hop_samples = max(
            1,
            int(round(sample_rate * self.package.chunk_samples / self.package.sample_rate)),
        )
        clean = np.zeros_like(mono, dtype=np.float32)
        start_time = time.perf_counter()
        cursor = 0

        while cursor < mono.shape[0]:
            end = min(cursor + hop_samples, mono.shape[0])
            chunk = mono[cursor:end]
            peak = max(float(np.max(np.abs(chunk))) if chunk.size else 0.0, 1.0)
            chunk_clean = _sinc_resample_to_length(
                np.clip(chunk / peak, -1.0, 1.0),
                self.package.chunk_samples,
            )

            for category_index, state in zip(category_indices, states):
                target = self.run_chunk(chunk_clean, category_index, state)
                chunk_clean = np.clip(chunk_clean - scale * target, -1.0, 1.0)

            restored = _sinc_resample_to_length(chunk_clean, chunk.shape[0])
            restored = np.nan_to_num(restored * peak, copy=False).astype(np.float32)
            clean[cursor:end] = np.clip(restored, -1.0, 1.0)
            cursor = end

        processing_seconds = time.perf_counter() - start_time
        duration_seconds = mono.shape[0] / max(float(sample_rate), 1.0)
        return clean, {
            "processing_seconds": processing_seconds,
            "duration_seconds": duration_seconds,
            "real_time_factor": processing_seconds / max(duration_seconds, 1.0e-12),
            "categories": category_ids,
            "mode": "android_live_chunk_sim",
            "native_hop_samples": hop_samples,
        }

    def smoke_two_step(self, category: str = "dog") -> dict[str, Any]:
        state = self.new_state()
        category_index = self.category_index(category)
        first = np.zeros((self.package.chunk_samples,), dtype=np.float32)
        second = np.zeros((self.package.chunk_samples,), dtype=np.float32)
        second[0] = 0.25
        out_first = self.run_chunk(first, category_index, state)
        state_after_first = {key: value.copy() for key, value in state.items()}
        out_second = self.run_chunk(second, category_index, state)
        state_delta = {
            key: float(np.max(np.abs(state[key] - state_after_first[key])))
            for key in state
        }
        return {
            "category": category,
            "target_chunk_shape": list(out_second.shape),
            "first_finite": bool(np.all(np.isfinite(out_first))),
            "second_finite": bool(np.all(np.isfinite(out_second))),
            "state_delta_max": max(state_delta.values()) if state_delta else 0.0,
            "state_delta_by_tensor": state_delta,
            "ok": bool(np.all(np.isfinite(out_first)) and np.all(np.isfinite(out_second))),
        }


def load_package(
    model_package_path: str | Path = DEFAULT_MODEL_PACKAGE,
    platform: str = "desktop",
) -> WaveformerOnnxPackage:
    package_path = Path(model_package_path).resolve()
    package = json.loads(package_path.read_text(encoding="utf-8"))
    root = package_path.parent
    selected_platform = package["platforms"][platform]
    categories = tuple(item["id"] for item in package["categories"])
    state_tensors = {
        name: tuple(int(value) for value in shape)
        for name, shape in selected_platform["state_tensors"].items()
    }
    metadata_paths = tuple(
        (root / item).resolve()
        for item in selected_platform.get("metadata_artifacts", [])
    )
    return WaveformerOnnxPackage(
        package_path=package_path,
        model_path=(root / selected_platform["artifact"]).resolve(),
        metadata_paths=metadata_paths,
        sample_rate=int(selected_platform["sample_rate"]),
        chunk_samples=int(selected_platform["chunk_samples"]),
        mix_channels=int(selected_platform.get("mix_channels", 1)),
        categories=categories,
        state_tensors=state_tensors,
    )


def load_android_bundle(bundle_dir: str | Path) -> WaveformerOnnxPackage:
    bundle_path = Path(bundle_dir).resolve()
    manifest_path = bundle_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_artifact = next(
        (
            item
            for item in manifest.get("artifacts", [])
            if item.get("role") == "model" and item.get("format") in {"onnx", "ort"}
        ),
        None,
    )
    if model_artifact is None:
        raise ValueError(f"No ONNX/ORT model artifact was found in Android bundle {bundle_path}")

    categories = tuple(item["id"] for item in manifest["categories"])
    state_tensors = {
        name: tuple(int(value) for value in shape)
        for name, shape in manifest["state_tensors"].items()
    }
    metadata_paths = tuple(
        (bundle_path / item["filename"]).resolve()
        for item in manifest.get("artifacts", [])
        if item.get("role") == "metadata"
    )
    return WaveformerOnnxPackage(
        package_path=manifest_path,
        model_path=(bundle_path / model_artifact["filename"]).resolve(),
        metadata_paths=metadata_paths,
        sample_rate=int(manifest["sample_rate"]),
        chunk_samples=int(manifest["chunk_samples"]),
        mix_channels=int(manifest.get("mix_channels", 1)),
        categories=categories,
        state_tensors=state_tensors,
    )


def suppress_file(
    input_path: str | Path,
    output_path: str | Path,
    categories: Iterable[str],
    aggressiveness: float = 1.0,
    model_package_path: str | Path = DEFAULT_MODEL_PACKAGE,
    noise_path: str | Path | None = None,
    package: WaveformerOnnxPackage | None = None,
    mode: str = "offline",
) -> dict[str, Any]:
    import soundfile as sf

    audio, sample_rate = sf.read(input_path, dtype="float32")
    runner = WaveformerOnnxStream(model_package_path, package=package)
    if mode == "android_live":
        cleaned_mono, stats = runner.suppress_live_chunks(
            audio,
            sample_rate,
            categories,
            aggressiveness,
        )
    elif mode == "offline":
        cleaned_mono, stats = runner.suppress(audio, sample_rate, categories, aggressiveness)
    else:
        raise ValueError(f"Unknown Waveformer suppression mode: {mode}")
    original_mono = _mono(np.asarray(audio, dtype=np.float32))
    residual = _fit_length(original_mono, cleaned_mono.shape[0]) - cleaned_mono
    cleaned = _project_residual_back(audio, residual)

    sf.write(output_path, cleaned, sample_rate)
    if noise_path is not None:
        sf.write(noise_path, residual.astype(np.float32), sample_rate)

    stats.update(
        {
            "sample_rate": int(sample_rate),
            "duration_seconds": float(original_mono.shape[0] / max(float(sample_rate), 1.0)),
            "rms_reduction_db": _db_ratio(_rms(original_mono), _rms(cleaned_mono)),
            "noise_audio": residual.astype(np.float32),
        }
    )
    return stats


def _mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio.astype(np.float32)
    return np.mean(audio, axis=1).astype(np.float32)


def _fit_length(audio: np.ndarray, length: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.shape[0] == length:
        return audio
    if audio.shape[0] > length:
        return audio[:length]
    if audio.size == 0:
        return np.zeros((length,), dtype=np.float32)
    return np.pad(audio, (0, length - audio.shape[0]), mode="edge").astype(np.float32)


def _resample_linear(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0 or source_rate == target_rate:
        return audio.copy()
    target_len = max(1, int(round(audio.shape[0] * target_rate / source_rate)))
    source_positions = np.arange(audio.shape[0], dtype=np.float64)
    target_positions = np.linspace(0, audio.shape[0] - 1, target_len, dtype=np.float64)
    return np.interp(target_positions, source_positions, audio).astype(np.float32)


def _sinc_resample_to_length(audio: np.ndarray, target_length: int, radius: int = 8) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if target_length <= 0:
        return np.zeros((0,), dtype=np.float32)
    if audio.size == 0:
        return np.zeros((target_length,), dtype=np.float32)
    if audio.size == target_length:
        return audio.copy()

    safe_radius = max(2, int(radius))
    scale = audio.size / float(target_length)
    cutoff = min(1.0, target_length / float(audio.size))
    positions = (np.arange(target_length, dtype=np.float64) + 0.5) * scale - 0.5
    centers = np.floor(positions).astype(np.int64)
    offsets = np.arange(-safe_radius + 1, safe_radius + 1, dtype=np.int64)
    taps = centers[:, None] + offsets[None, :]
    distances = positions[:, None] - taps.astype(np.float64)
    window_distances = np.abs(distances) / float(safe_radius)
    mask = window_distances < 1.0

    sinc_args = distances * cutoff
    sinc = np.ones_like(sinc_args)
    nonzero = np.abs(sinc_args) >= 1.0e-8
    sinc[nonzero] = np.sin(np.pi * sinc_args[nonzero]) / (np.pi * sinc_args[nonzero])
    window = 0.5 + 0.5 * np.cos(np.pi * window_distances)
    weights = np.where(mask, cutoff * sinc * window, 0.0)
    samples = audio[np.clip(taps, 0, audio.size - 1)]
    weighted = np.sum(samples * weights, axis=1)
    weight_sum = np.sum(weights, axis=1)
    output = np.divide(
        weighted,
        weight_sum,
        out=np.zeros_like(weighted),
        where=np.abs(weight_sum) > 1.0e-8,
    )
    return output.astype(np.float32)


def _project_residual_back(original: np.ndarray, residual_mono: np.ndarray) -> np.ndarray:
    original = np.asarray(original, dtype=np.float32)
    if original.ndim == 1:
        return np.clip(original - _fit_length(residual_mono, original.shape[0]), -1.0, 1.0)
    residual = _fit_length(residual_mono, original.shape[0])[:, None]
    return np.clip(original - residual, -1.0, 1.0).astype(np.float32)


def _rms(audio: np.ndarray) -> float:
    audio = np.asarray(audio, dtype=np.float64)
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _db_ratio(before: float, after: float) -> float:
    if not math.isfinite(before) or not math.isfinite(after):
        return 0.0
    return float(20.0 * math.log10((before + 1.0e-12) / (after + 1.0e-12)))


def _shape_values(values: Iterable[Any]) -> list[Any]:
    shaped: list[Any] = []
    for value in values:
        shaped.append(int(value) if isinstance(value, int) else value)
    return shaped


__all__ = [
    "DEFAULT_MODEL_PACKAGE",
    "WaveformerOnnxPackage",
    "WaveformerOnnxStream",
    "load_android_bundle",
    "load_package",
    "suppress_file",
]
