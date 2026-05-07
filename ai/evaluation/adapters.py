"""Evaluation model adapters."""

from __future__ import annotations

import importlib
import importlib.util
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from ai.evaluation.contracts import AdapterResult, EvalCase, EvaluationSettings, ModelEvalSpec


def _mono(audio: np.ndarray) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        return array
    return np.mean(array, axis=1).astype(np.float32, copy=False)


def _write_audio(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0), int(sample_rate))


def _align_length(audio: np.ndarray, length: int) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float32)
    if len(array) >= length:
        return array[:length]
    return np.pad(array, (0, length - len(array)))


def _build_clean_from_removed(
    mixture: np.ndarray,
    removed: np.ndarray,
    *,
    aggressiveness: float,
) -> tuple[np.ndarray, np.ndarray]:
    mixture_mono = _mono(mixture)
    removed_mono = _align_length(_mono(removed), len(mixture_mono))
    clean_mono = mixture_mono - float(aggressiveness) * removed_mono
    return clean_mono.astype(np.float32, copy=False), removed_mono.astype(np.float32, copy=False)


class ModelAdapter(ABC):
    """Base class for model adapters."""

    def __init__(self, spec: ModelEvalSpec, settings: EvaluationSettings) -> None:
        self.spec = spec
        self.settings = settings

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Load model resources once per worker."""

    @abstractmethod
    def process(self, case: EvalCase, output_dir: Path, repeat_index: int) -> AdapterResult:
        """Process one case and write clean/removed audio."""

    def close(self) -> None:
        """Release model resources."""


class UnsupportedAdapter(ModelAdapter):
    def load(self) -> dict[str, Any]:
        raise RuntimeError(self.spec.unsupported_reason or "Model is not runnable.")

    def process(self, case: EvalCase, output_dir: Path, repeat_index: int) -> AdapterResult:
        raise RuntimeError(self.spec.unsupported_reason or "Model is not runnable.")


class WaveformerOnnxAdapter(ModelAdapter):
    def load(self) -> dict[str, Any]:
        from ai.ai_runtime.separation.waveformer_onnx_stream import WaveformerOnnxStream
        from ai.ai_runtime.utils.paths import get_waveformer_model_package_path

        self.runner = WaveformerOnnxStream(get_waveformer_model_package_path())
        return {"adapter": "waveformer_onnx"}

    def process(self, case: EvalCase, output_dir: Path, repeat_index: int) -> AdapterResult:
        target = case.target_for_surface(self.spec.target_surface)
        mixture, sample_rate = sf.read(case.input_path, dtype="float32")
        mixture_mono = _mono(mixture)
        clean, runtime_stats = self.runner.suppress(
            mixture,
            int(sample_rate),
            [target],
            aggressiveness=float(self.settings.aggressiveness),
        )
        clean = _align_length(clean, len(mixture_mono))
        removed = mixture_mono - clean
        clean_path = output_dir / "clean.wav"
        removed_path = output_dir / "removed.wav"
        _write_audio(clean_path, clean, int(sample_rate))
        _write_audio(removed_path, removed, int(sample_rate))
        return AdapterResult(
            clean_path=clean_path,
            removed_path=removed_path,
            sample_rate=int(sample_rate),
            duration_seconds=float(len(mixture_mono) / max(float(sample_rate), 1.0)),
            metadata={"target": target, **runtime_stats},
        )


class SemanticBatchAdapter(ModelAdapter):
    def load(self) -> dict[str, Any]:
        from ai.ai_runtime.batch.batch_processor import BatchProcessor
        from ai.ai_runtime.suppression import SemanticSuppressor

        options = dict(self.spec.adapter_options)
        suppressor_kwargs = {
            "separator_backend": options.get("separator_backend", "waveformer"),
        }
        if options.get("codecsep_dnrv2_15cat_runtime"):
            suppressor_kwargs["codecsep_dnrv2_15cat_runtime"] = options[
                "codecsep_dnrv2_15cat_runtime"
            ]
        self.process_kwargs = {}
        for key in ("codecsep_mode", "codecsep_dnrv2_15cat_runtime"):
            if key in options:
                self.process_kwargs[key] = options[key]
        self.processor = BatchProcessor(suppressor=SemanticSuppressor(**suppressor_kwargs))
        return {"adapter": "semantic_batch", **suppressor_kwargs}

    def process(self, case: EvalCase, output_dir: Path, repeat_index: int) -> AdapterResult:
        target = case.target_for_surface(self.spec.target_surface)
        clean_path = output_dir / "clean.wav"
        removed_path = output_dir / "removed.wav"
        suppress_categories: list[str] = []
        audiosep_prompts: list[str] = []
        if self.spec.target_surface == "audiosep_prompt":
            audiosep_prompts = [target]
        else:
            suppress_categories = [target]

        stats = self.processor.process_file(
            input_path=case.input_path,
            output_path=clean_path,
            suppress_categories=suppress_categories,
            chunk_size_seconds=float(self.settings.chunk_size_seconds),
            detection_threshold=float(self.settings.threshold),
            aggressiveness=float(self.settings.aggressiveness),
            universal_prompts=audiosep_prompts,
            output_noise=True,
            **self.process_kwargs,
        )
        sample_rate = int(stats["sample_rate"])
        if stats.get("noise_audio") is not None:
            _write_audio(removed_path, np.asarray(stats["noise_audio"], dtype=np.float32), sample_rate)
        else:
            clean_audio, _ = sf.read(clean_path, dtype="float32")
            original, _ = sf.read(case.input_path, dtype="float32")
            removed = _mono(original)[: len(_mono(clean_audio))] - _mono(clean_audio)
            _write_audio(removed_path, removed, sample_rate)
        return AdapterResult(
            clean_path=clean_path,
            removed_path=removed_path,
            sample_rate=sample_rate,
            duration_seconds=float(stats["duration_seconds"]),
            metadata={"target": target, **{k: v for k, v in stats.items() if k != "noise_audio"}},
        )


class AudioSepSourceAdapter(ModelAdapter):
    def load(self) -> dict[str, Any]:
        import torch

        source_dir = Path(self.spec.adapter_options["source_dir"])
        if str(source_dir) not in sys.path:
            sys.path.insert(0, str(source_dir))
        pipeline = importlib.import_module("pipeline")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.torch = torch
        self.model = pipeline.build_audiosep(
            config_yaml=str(self.spec.adapter_options["config_path"]),
            checkpoint_path=str(self.spec.adapter_options["checkpoint_path"]),
            device=self.device,
        )
        return {"adapter": "audiosep_source", "device": str(self.device)}

    def process(self, case: EvalCase, output_dir: Path, repeat_index: int) -> AdapterResult:
        import librosa

        prompt = case.target_for_surface(self.spec.target_surface)
        mixture, sample_rate = librosa.load(str(case.input_path), sr=32000, mono=True)
        mixture = np.asarray(mixture, dtype=np.float32)
        with self.torch.no_grad():
            conditions = self.model.query_encoder.get_query_embed(
                modality="text",
                text=[prompt],
                device=self.device,
            )
            tensor = self.torch.tensor(mixture, dtype=self.torch.float32)[None, None, :].to(self.device)
            output = self.model.ss_model({"mixture": tensor, "condition": conditions})["waveform"]
            removed = output.squeeze().detach().cpu().numpy().astype(np.float32)
        clean, removed = _build_clean_from_removed(
            mixture,
            removed,
            aggressiveness=float(self.settings.aggressiveness),
        )
        clean_path = output_dir / "clean.wav"
        removed_path = output_dir / "removed.wav"
        _write_audio(clean_path, clean, 32000)
        _write_audio(removed_path, removed, 32000)
        return AdapterResult(
            clean_path=clean_path,
            removed_path=removed_path,
            sample_rate=32000,
            duration_seconds=float(len(mixture) / 32000.0),
            metadata={"target": prompt, "adapter": "audiosep_source"},
        )


class ClapSepSourceAdapter(ModelAdapter):
    MODEL_CONFIG = {
        "lan_embed_dim": 1024,
        "depths": [1, 1, 1, 1],
        "embed_dim": 128,
        "encoder_embed_dim": 128,
        "phase": False,
        "spec_factor": 8,
        "d_attn": 640,
        "n_masker_layer": 3,
        "conv": False,
    }

    def load(self) -> dict[str, Any]:
        import torch

        package_dir = Path(self.spec.adapter_options["package_dir"])
        if str(package_dir) not in sys.path:
            sys.path.insert(0, str(package_dir))
        from model.CLAPSep import CLAPSep

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch = torch
        self.model = CLAPSep(
            self.MODEL_CONFIG,
            str(self.spec.adapter_options["clap_checkpoint_path"]),
        ).to(self.device)
        checkpoint = torch.load(
            str(self.spec.adapter_options["checkpoint_path"]),
            map_location=self.device,
        )
        self.model.load_state_dict(checkpoint, strict=False)
        self.model.eval()
        return {"adapter": "clapsep_source", "device": self.device}

    def process(self, case: EvalCase, output_dir: Path, repeat_index: int) -> AdapterResult:
        import librosa

        prompt = case.target_for_surface(self.spec.target_surface)
        mixture, _ = librosa.load(str(case.input_path), sr=32000, mono=True)
        mixture = np.asarray(mixture, dtype=np.float32)
        with self.torch.no_grad():
            embed_pos = self.model.clap_model.get_text_embedding([prompt], use_tensor=True).to(
                self.device
            )
            embed_neg = self.torch.zeros_like(embed_pos)
            pad = (320000 - (len(mixture) % 320000)) if len(mixture) % 320000 != 0 else 0
            padded = self.torch.tensor(np.pad(mixture, (0, pad)), dtype=self.torch.float32).to(
                self.device
            )
            max_value = self.torch.max(self.torch.abs(padded))
            if float(max_value.detach().cpu()) > 1.0:
                padded = padded * (0.9 / max_value)
            chunks = self.torch.chunk(padded, dim=0, chunks=max(1, len(padded) // 320000))
            separated = [
                self.model.inference_from_data(chunk.unsqueeze(0), embed_pos, embed_neg)
                for chunk in chunks
            ]
            removed = self.torch.concat(separated, dim=1).squeeze().detach().cpu().numpy()
        removed = np.asarray(removed[: len(mixture)], dtype=np.float32)
        clean, removed = _build_clean_from_removed(
            mixture,
            removed,
            aggressiveness=float(self.settings.aggressiveness),
        )
        clean_path = output_dir / "clean.wav"
        removed_path = output_dir / "removed.wav"
        _write_audio(clean_path, clean, 32000)
        _write_audio(removed_path, removed, 32000)
        return AdapterResult(
            clean_path=clean_path,
            removed_path=removed_path,
            sample_rate=32000,
            duration_seconds=float(len(mixture) / 32000.0),
            metadata={"target": prompt, "adapter": "clapsep_source"},
        )


def build_adapter(spec: ModelEvalSpec, settings: EvaluationSettings) -> ModelAdapter:
    """Construct the adapter for a model spec."""

    kind = spec.adapter_kind
    if kind == "waveformer_onnx":
        return WaveformerOnnxAdapter(spec, settings)
    if kind == "semantic_batch":
        return SemanticBatchAdapter(spec, settings)
    if kind == "audiosep_source":
        return AudioSepSourceAdapter(spec, settings)
    if kind == "clapsep_source":
        return ClapSepSourceAdapter(spec, settings)
    return UnsupportedAdapter(spec, settings)
