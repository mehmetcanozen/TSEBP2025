"""
Batch Audio Processor - Offline Semantic Noise Suppression

Process audio files offline with semantic-aware noise suppression.
Useful for cleaning recorded audio, podcasts, or conference recordings.

Usage:
    python -m ai.ai_runtime.batch.batch_processor --input noisy.wav --suppress typing,wind --output clean.wav
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
import soundfile as sf
from tqdm import tqdm

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.utils.codecsep import (
    add_codecsep_runtime_arguments,
    build_codecsep_call_kwargs_from_args,
    build_suppressor_kwargs_from_args,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process audio files with semantic noise suppression."""

    def __init__(self, suppressor: Optional[SemanticSuppressor] = None):
        self.suppressor = suppressor or SemanticSuppressor()

    def _should_process_stereo_channels_independently(
        self,
        *,
        suppress_all: bool,
        universal_prompts: Optional[List[str]],
        codecsep_stereo_mode: str,
    ) -> bool:
        backend = getattr(self.suppressor, "separator_backend", "waveformer")
        if suppress_all:
            return True
        if universal_prompts and backend != "codecsep":
            return True
        return backend == "codecsep" and codecsep_stereo_mode == "per_channel"

    def _uses_overlap_add_chunking(
        self,
        *,
        suppress_all: bool,
        universal_prompts: Optional[List[str]],
    ) -> bool:
        if suppress_all:
            return False
        backend = getattr(self.suppressor, "separator_backend", "waveformer")
        if universal_prompts and backend != "codecsep":
            return False
        return backend in {"codecsep", "audiosep_hive15cat", "codecsep_dnrv2_15cat"}

    def _suppress_mono_chunk(
        self,
        chunk: np.ndarray,
        *,
        sample_rate: int,
        suppress_categories: List[str],
        detection_threshold: float,
        aggressiveness: float,
        suppress_all: bool,
        universal_prompts: Optional[List[str]],
        audiosep_hive15cat_model_path: Optional[str],
        audiosep_hive15cat_device: Optional[str],
        audiosep_hive15cat_realtime_hop_seconds: float,
        codecsep_dnrv2_15cat_model_path: Optional[str],
        codecsep_dnrv2_15cat_runtime: str,
        codecsep_dnrv2_15cat_device: Optional[str],
        codecsep_dnrv2_15cat_realtime_hop_seconds: float,
        codecsep_prompt_overrides: Optional[dict[str, list[str]]],
        codecsep_negative_prompts: Optional[list[str]],
        codecsep_preserve_prompts: Optional[list[str]],
        codecsep_mode: str,
        codecsep_query_strategy: str,
        codecsep_multistep_steps: int,
        codecsep_fixed_merge_policy: str,
        codecsep_product_categories: Optional[list[str]],
        codecsep_hive_class_ids: Optional[list[str]],
        return_details: bool = False,
    ) -> tuple[np.ndarray, Optional[np.ndarray]]:
        result = self.suppressor.suppress(
            audio=chunk,
            sample_rate=sample_rate,
            suppress_categories=suppress_categories,
            detection_threshold=detection_threshold,
            aggressiveness=aggressiveness,
            suppress_all=suppress_all,
            universal_prompts=universal_prompts or [],
            audiosep_hive15cat_model_path=audiosep_hive15cat_model_path,
            audiosep_hive15cat_device=audiosep_hive15cat_device,
            audiosep_hive15cat_realtime_hop_seconds=audiosep_hive15cat_realtime_hop_seconds,
            codecsep_dnrv2_15cat_model_path=codecsep_dnrv2_15cat_model_path,
            codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
            codecsep_dnrv2_15cat_device=codecsep_dnrv2_15cat_device,
            codecsep_dnrv2_15cat_realtime_hop_seconds=codecsep_dnrv2_15cat_realtime_hop_seconds,
            codecsep_prompt_overrides=codecsep_prompt_overrides,
            codecsep_negative_prompts=codecsep_negative_prompts,
            codecsep_preserve_prompts=codecsep_preserve_prompts,
            codecsep_mode=codecsep_mode,
            codecsep_query_strategy=codecsep_query_strategy,
            codecsep_multistep_steps=codecsep_multistep_steps,
            codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
            codecsep_product_categories=codecsep_product_categories,
            codecsep_hive_class_ids=codecsep_hive_class_ids,
            return_details=return_details,
        )
        if return_details:
            backend = getattr(self.suppressor, "separator_backend", "waveformer")
            clean_audio = np.asarray(result["clean_audio"], dtype=chunk.dtype)
            removed_audio = np.asarray(result["removed_audio"], dtype=chunk.dtype)
            if backend in {"audiosep_hive15cat", "codecsep_dnrv2_15cat"}:
                removed_audio = np.asarray(chunk - clean_audio, dtype=chunk.dtype)
            return (
                clean_audio,
                removed_audio,
            )
        return np.asarray(result, dtype=chunk.dtype), None

    @staticmethod
    def _project_mono_removed_to_stereo(
        chunk: np.ndarray,
        removed_mono: np.ndarray,
    ) -> np.ndarray:
        stereo = np.asarray(chunk, dtype=np.float32)
        target = np.asarray(removed_mono, dtype=np.float32).reshape(-1, 1)
        channels = stereo.shape[1]
        energy = np.abs(stereo)
        denom = energy.sum(axis=1, keepdims=True)
        weights = np.divide(
            energy,
            denom,
            out=np.full_like(stereo, 1.0 / max(1, channels)),
            where=denom > 1e-8,
        )
        return (target * weights * channels).astype(stereo.dtype, copy=False)

    def _process_chunk(
        self,
        chunk: np.ndarray,
        *,
        sample_rate: int,
        suppress_categories: List[str],
        detection_threshold: float,
        aggressiveness: float,
        suppress_all: bool,
        universal_prompts: Optional[List[str]],
        audiosep_hive15cat_model_path: Optional[str],
        audiosep_hive15cat_device: Optional[str],
        audiosep_hive15cat_realtime_hop_seconds: float,
        codecsep_dnrv2_15cat_model_path: Optional[str],
        codecsep_dnrv2_15cat_runtime: str,
        codecsep_dnrv2_15cat_device: Optional[str],
        codecsep_dnrv2_15cat_realtime_hop_seconds: float,
        codecsep_prompt_overrides: Optional[dict[str, list[str]]],
        codecsep_negative_prompts: Optional[list[str]],
        codecsep_preserve_prompts: Optional[list[str]],
        codecsep_mode: str,
        codecsep_query_strategy: str,
        codecsep_multistep_steps: int,
        codecsep_stereo_mode: str,
        codecsep_fixed_merge_policy: str,
        codecsep_product_categories: Optional[list[str]],
        codecsep_hive_class_ids: Optional[list[str]],
        output_noise: bool,
    ) -> tuple[np.ndarray, Optional[np.ndarray]]:
        if chunk.ndim == 2:
            if self._should_process_stereo_channels_independently(
                suppress_all=suppress_all,
                universal_prompts=universal_prompts,
                codecsep_stereo_mode=codecsep_stereo_mode,
            ):
                backend = getattr(self.suppressor, "separator_backend", "waveformer")
                logger.info(
                    "Processing stereo chunk per-channel for %s debug/high-cost mode",
                    backend,
                )
                clean_channels = []
                noise_channels = []
                for channel_index in range(chunk.shape[1]):
                    clean_channel, noise_channel = self._suppress_mono_chunk(
                        chunk[:, channel_index],
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                        aggressiveness=aggressiveness,
                        suppress_all=suppress_all,
                        universal_prompts=universal_prompts,
                        audiosep_hive15cat_model_path=audiosep_hive15cat_model_path,
                        audiosep_hive15cat_device=audiosep_hive15cat_device,
                        audiosep_hive15cat_realtime_hop_seconds=audiosep_hive15cat_realtime_hop_seconds,
                        codecsep_dnrv2_15cat_model_path=codecsep_dnrv2_15cat_model_path,
                        codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
                        codecsep_dnrv2_15cat_device=codecsep_dnrv2_15cat_device,
                        codecsep_dnrv2_15cat_realtime_hop_seconds=codecsep_dnrv2_15cat_realtime_hop_seconds,
                        codecsep_prompt_overrides=codecsep_prompt_overrides,
                        codecsep_negative_prompts=codecsep_negative_prompts,
                        codecsep_preserve_prompts=codecsep_preserve_prompts,
                        codecsep_mode=codecsep_mode,
                        codecsep_query_strategy=codecsep_query_strategy,
                        codecsep_multistep_steps=codecsep_multistep_steps,
                        codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
                        codecsep_product_categories=codecsep_product_categories,
                        codecsep_hive_class_ids=codecsep_hive_class_ids,
                        return_details=output_noise,
                    )
                    clean_channels.append(np.asarray(clean_channel, dtype=chunk.dtype))
                    if output_noise:
                        noise_channels.append(np.asarray(noise_channel, dtype=chunk.dtype))
                return (
                    np.column_stack(clean_channels),
                    np.column_stack(noise_channels) if output_noise else None,
                )

            backend = getattr(self.suppressor, "separator_backend", "waveformer")
            logger.info(
                "Processing stereo chunk with shared mono %s inference for faster runtime suppression",
                backend,
            )
            mono_chunk = chunk.mean(axis=1)
            capture_removed = output_noise or (
                getattr(self.suppressor, "separator_backend", "waveformer")
                in {"codecsep", "audiosep_hive15cat", "codecsep_dnrv2_15cat"}
            )
            clean_mono, removed_mono = self._suppress_mono_chunk(
                mono_chunk,
                sample_rate=sample_rate,
                suppress_categories=suppress_categories,
                detection_threshold=detection_threshold,
                aggressiveness=aggressiveness,
                suppress_all=suppress_all,
                universal_prompts=universal_prompts,
                audiosep_hive15cat_model_path=audiosep_hive15cat_model_path,
                audiosep_hive15cat_device=audiosep_hive15cat_device,
                audiosep_hive15cat_realtime_hop_seconds=audiosep_hive15cat_realtime_hop_seconds,
                codecsep_dnrv2_15cat_model_path=codecsep_dnrv2_15cat_model_path,
                codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
                codecsep_dnrv2_15cat_device=codecsep_dnrv2_15cat_device,
                codecsep_dnrv2_15cat_realtime_hop_seconds=codecsep_dnrv2_15cat_realtime_hop_seconds,
                codecsep_prompt_overrides=codecsep_prompt_overrides,
                codecsep_negative_prompts=codecsep_negative_prompts,
                codecsep_preserve_prompts=codecsep_preserve_prompts,
                codecsep_mode=codecsep_mode,
                codecsep_query_strategy=codecsep_query_strategy,
                codecsep_multistep_steps=codecsep_multistep_steps,
                codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
                codecsep_product_categories=codecsep_product_categories,
                codecsep_hive_class_ids=codecsep_hive_class_ids,
                return_details=capture_removed,
            )
            if (
                getattr(self.suppressor, "separator_backend", "waveformer")
                in {"codecsep", "audiosep_hive15cat", "codecsep_dnrv2_15cat"}
                and removed_mono is not None
            ):
                removed_stereo = self._project_mono_removed_to_stereo(chunk, removed_mono)
                clean_stereo = chunk - removed_stereo
                return (
                    clean_stereo.astype(chunk.dtype, copy=False),
                    removed_stereo.astype(chunk.dtype, copy=False) if output_noise else None,
                )
            eps = 1e-4
            ratio = np.ones_like(mono_chunk, dtype=mono_chunk.dtype)
            np.divide(clean_mono, mono_chunk, out=ratio, where=np.abs(mono_chunk) > eps)
            ratio = np.clip(ratio, 0.0, 10.0)
            clean_stereo = chunk * ratio[:, np.newaxis]
            return clean_stereo, (chunk - clean_stereo) if output_noise else None

        return self._suppress_mono_chunk(
            chunk,
            sample_rate=sample_rate,
            suppress_categories=suppress_categories,
            detection_threshold=detection_threshold,
            aggressiveness=aggressiveness,
            suppress_all=suppress_all,
            universal_prompts=universal_prompts,
            audiosep_hive15cat_model_path=audiosep_hive15cat_model_path,
            audiosep_hive15cat_device=audiosep_hive15cat_device,
            audiosep_hive15cat_realtime_hop_seconds=audiosep_hive15cat_realtime_hop_seconds,
            codecsep_dnrv2_15cat_model_path=codecsep_dnrv2_15cat_model_path,
            codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
            codecsep_dnrv2_15cat_device=codecsep_dnrv2_15cat_device,
            codecsep_dnrv2_15cat_realtime_hop_seconds=codecsep_dnrv2_15cat_realtime_hop_seconds,
            codecsep_prompt_overrides=codecsep_prompt_overrides,
            codecsep_negative_prompts=codecsep_negative_prompts,
            codecsep_preserve_prompts=codecsep_preserve_prompts,
            codecsep_mode=codecsep_mode,
            codecsep_query_strategy=codecsep_query_strategy,
            codecsep_multistep_steps=codecsep_multistep_steps,
            codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
            codecsep_product_categories=codecsep_product_categories,
            codecsep_hive_class_ids=codecsep_hive_class_ids,
            return_details=output_noise,
        )

    @staticmethod
    def _codecsep_overlap_samples(sample_rate: int, chunk_size: int) -> int:
        return max(0, min(chunk_size // 10, int(sample_rate * 0.25)))

    def _outer_overlap_samples(
        self,
        sample_rate: int,
        chunk_size: int,
        *,
        codecsep_dnrv2_15cat_runtime: str = "onnx",
    ) -> int:
        backend = getattr(self.suppressor, "separator_backend", "waveformer")
        if backend == "audiosep_hive15cat":
            return max(0, min(chunk_size // 2, int(sample_rate * 1.0)))
        if backend == "codecsep_dnrv2_15cat":
            if str(codecsep_dnrv2_15cat_runtime).strip().casefold() == "executorch":
                return 0
            return max(0, min(chunk_size // 2, int(sample_rate * 0.5)))
        return self._codecsep_overlap_samples(sample_rate, chunk_size)

    @staticmethod
    def _build_overlap_window(
        length: int,
        *,
        overlap_samples: int,
        fade_in: bool,
        fade_out: bool,
    ) -> np.ndarray:
        window = np.ones(length, dtype=np.float32)
        overlap = min(overlap_samples, length)
        if overlap <= 0:
            return window

        ramp = np.linspace(0.0, 1.0, overlap, endpoint=False, dtype=np.float32)
        if fade_in:
            window[:overlap] = ramp
        if fade_out:
            window[-overlap:] = np.minimum(window[-overlap:], 1.0 - ramp)
        return window

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        suppress_categories: List[str],
        chunk_size_seconds: float = 10.0,
        detection_threshold: float = 0.5,
        aggressiveness: float = 1.5,
        suppress_all: bool = False,
        universal_prompts: List[str] = None,
        output_noise: bool = False,
        audiosep_hive15cat_model_path: Optional[str] = None,
        audiosep_hive15cat_device: Optional[str] = None,
        audiosep_hive15cat_realtime_hop_seconds: float = 1.0,
        codecsep_dnrv2_15cat_model_path: Optional[str] = None,
        codecsep_dnrv2_15cat_runtime: str = "onnx",
        codecsep_dnrv2_15cat_device: Optional[str] = None,
        codecsep_dnrv2_15cat_realtime_hop_seconds: float = 0.5,
        codecsep_prompt_overrides: Optional[dict[str, list[str]]] = None,
        codecsep_negative_prompts: Optional[list[str]] = None,
        codecsep_preserve_prompts: Optional[list[str]] = None,
        codecsep_mode: str = "fixed_category",
        codecsep_query_strategy: str = "single_pass",
        codecsep_multistep_steps: int = 0,
        codecsep_stereo_mode: str = "mono_shared",
        codecsep_fixed_merge_policy: str = "wiener_mask",
        codecsep_product_categories: Optional[list[str]] = None,
        codecsep_hive_class_ids: Optional[list[str]] = None,
    ) -> dict:
        logger.info("Processing: %s", input_path)
        if suppress_categories:
            logger.info("Suppressing categories: %s", ", ".join(suppress_categories))
        if codecsep_product_categories:
            logger.info("CodecSep fixed product targets: %s", ", ".join(codecsep_product_categories))
        if codecsep_hive_class_ids:
            logger.info(
                "CodecSep fixed class-id targets: %s",
                ", ".join(str(value) for value in codecsep_hive_class_ids),
            )

        audio, sample_rate = sf.read(input_path, dtype="float32")
        logger.info("Loaded audio: %s, %s Hz", audio.shape, sample_rate)
        if hasattr(self.suppressor, "reset_runtime_state"):
            self.suppressor.reset_runtime_state()

        backend = getattr(self.suppressor, "separator_backend", "waveformer")
        effective_chunk_size_seconds = float(chunk_size_seconds)
        if (
            backend == "codecsep_dnrv2_15cat"
            and str(codecsep_dnrv2_15cat_runtime).strip().casefold() == "executorch"
            and effective_chunk_size_seconds > 2.0
        ):
            logger.info(
                "CodecSepDNRv2_15Cat ExecuTorch uses 2.0s outer chunks on desktop "
                "to avoid long first-chunk stalls."
            )
            effective_chunk_size_seconds = 2.0

        chunk_size = int(effective_chunk_size_seconds * sample_rate)
        use_overlap_add = self._uses_overlap_add_chunking(
            suppress_all=suppress_all,
            universal_prompts=universal_prompts,
        )

        if use_overlap_add and len(audio) > chunk_size:
            overlap_samples = self._outer_overlap_samples(
                sample_rate,
                chunk_size,
                codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
            )
            step_size = max(1, chunk_size - overlap_samples)
            num_chunks = (len(audio) + step_size - 1) // step_size
            logger.info(
                "%s offline processing enabled overlap-add chunking (chunk=%.2fs, overlap=%.2fs)",
                backend,
                chunk_size / sample_rate,
                overlap_samples / sample_rate,
            )

            cleaned_audio = np.zeros_like(audio, dtype=np.float32)
            removed_audio_accum = np.zeros_like(audio, dtype=np.float32) if output_noise else None
            weight_sum = np.zeros(
                len(audio) if audio.ndim == 1 else (len(audio), 1),
                dtype=np.float32,
            )

            with tqdm(total=num_chunks, desc="Processing chunks") as pbar:
                chunk_index = 0
                for start in range(0, len(audio), step_size):
                    end = min(start + chunk_size, len(audio))
                    chunk = audio[start:end]
                    clean_chunk, noise_chunk = self._process_chunk(
                        chunk,
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                        aggressiveness=aggressiveness,
                    suppress_all=suppress_all,
                    universal_prompts=universal_prompts,
                    audiosep_hive15cat_model_path=audiosep_hive15cat_model_path,
                    audiosep_hive15cat_device=audiosep_hive15cat_device,
                    audiosep_hive15cat_realtime_hop_seconds=audiosep_hive15cat_realtime_hop_seconds,
                    codecsep_dnrv2_15cat_model_path=codecsep_dnrv2_15cat_model_path,
                    codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
                    codecsep_dnrv2_15cat_device=codecsep_dnrv2_15cat_device,
                    codecsep_dnrv2_15cat_realtime_hop_seconds=codecsep_dnrv2_15cat_realtime_hop_seconds,
                    codecsep_prompt_overrides=codecsep_prompt_overrides,
                    codecsep_negative_prompts=codecsep_negative_prompts,
                    codecsep_preserve_prompts=codecsep_preserve_prompts,
                    codecsep_mode=codecsep_mode,
                        codecsep_query_strategy=codecsep_query_strategy,
                        codecsep_multistep_steps=codecsep_multistep_steps,
                        codecsep_stereo_mode=codecsep_stereo_mode,
                        codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
                        codecsep_product_categories=codecsep_product_categories,
                        codecsep_hive_class_ids=codecsep_hive_class_ids,
                        output_noise=output_noise,
                    )
                    clean_chunk = np.asarray(clean_chunk, dtype=np.float32)

                    window = self._build_overlap_window(
                        len(chunk),
                        overlap_samples=overlap_samples,
                        fade_in=start > 0,
                        fade_out=end < len(audio),
                    )
                    window_view = window if clean_chunk.ndim == 1 else window[:, np.newaxis]
                    cleaned_audio[start:end] += clean_chunk * window_view
                    if output_noise and removed_audio_accum is not None:
                        exact_noise = (
                            np.asarray(noise_chunk, dtype=np.float32)
                            if noise_chunk is not None
                            else np.asarray(chunk - clean_chunk, dtype=np.float32)
                        )
                        removed_audio_accum[start:end] += exact_noise * window_view
                    weight_sum[start:end] += (
                        window if clean_chunk.ndim == 1 else window[:, np.newaxis]
                    )
                    chunk_index += 1
                    pbar.update(1)

            cleaned_audio = cleaned_audio / np.maximum(weight_sum, 1e-8)
            noise_audio = (
                removed_audio_accum / np.maximum(weight_sum, 1e-8)
                if output_noise and removed_audio_accum is not None
                else None
            )
        else:
            num_chunks = (len(audio) + chunk_size - 1) // chunk_size
            cleaned_chunks = []
            noise_chunks = []

            with tqdm(total=num_chunks, desc="Processing chunks") as pbar:
                for i in range(0, len(audio), chunk_size):
                    chunk = audio[i : i + chunk_size]
                    clean_chunk, noise_chunk = self._process_chunk(
                        chunk,
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                        aggressiveness=aggressiveness,
                suppress_all=suppress_all,
                universal_prompts=universal_prompts,
                audiosep_hive15cat_model_path=audiosep_hive15cat_model_path,
                audiosep_hive15cat_device=audiosep_hive15cat_device,
                audiosep_hive15cat_realtime_hop_seconds=audiosep_hive15cat_realtime_hop_seconds,
                codecsep_dnrv2_15cat_model_path=codecsep_dnrv2_15cat_model_path,
                codecsep_dnrv2_15cat_runtime=codecsep_dnrv2_15cat_runtime,
                codecsep_dnrv2_15cat_device=codecsep_dnrv2_15cat_device,
                codecsep_dnrv2_15cat_realtime_hop_seconds=codecsep_dnrv2_15cat_realtime_hop_seconds,
                codecsep_prompt_overrides=codecsep_prompt_overrides,
                codecsep_negative_prompts=codecsep_negative_prompts,
                codecsep_preserve_prompts=codecsep_preserve_prompts,
                codecsep_mode=codecsep_mode,
                        codecsep_query_strategy=codecsep_query_strategy,
                        codecsep_multistep_steps=codecsep_multistep_steps,
                        codecsep_stereo_mode=codecsep_stereo_mode,
                        codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
                        codecsep_product_categories=codecsep_product_categories,
                        codecsep_hive_class_ids=codecsep_hive_class_ids,
                        output_noise=output_noise,
                    )
                    cleaned_chunks.append(clean_chunk)
                    if output_noise:
                        noise_chunks.append(noise_chunk if noise_chunk is not None else (chunk - clean_chunk))
                    pbar.update(1)

            cleaned_audio = np.concatenate(cleaned_chunks, axis=0)
            noise_audio = np.concatenate(noise_chunks, axis=0) if output_noise else None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, cleaned_audio, sample_rate)
        logger.info("Saved cleaned audio: %s", output_path)

        original_rms = np.sqrt(np.mean(audio**2))
        cleaned_rms = np.sqrt(np.mean(cleaned_audio**2))
        return {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "sample_rate": sample_rate,
            "duration_seconds": len(audio) / sample_rate,
            "original_rms": float(original_rms),
            "cleaned_rms": float(cleaned_rms),
            "rms_reduction_db": float(20 * np.log10(cleaned_rms / (original_rms + 1e-8))),
            "suppressed_categories": suppress_categories,
            "noise_audio": noise_audio,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch audio noise suppression")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input audio file (WAV, FLAC, etc.)")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output file path")
    parser.add_argument(
        "--suppress",
        "-s",
        type=str,
        required=False,
        help=(
            "Comma-separated list of categories to suppress (e.g., typing,wind,traffic). "
            "Optional if using --suppress-all, --universal, --codecsep-product-category, "
            "or --codecsep-hive-class-id instead."
        ),
    )
    parser.add_argument("--threshold", "-t", type=float, default=0.5, help="Detection confidence threshold (0.0-1.0)")
    parser.add_argument("--aggressiveness", "-a", type=float, default=1.5, help="Suppression aggressiveness (1.0-2.0)")
    parser.add_argument(
        "--suppress-all",
        action="store_true",
        help="Use universal speech enhancement (DeepFilterNet) instead of semantic extraction",
    )
    parser.add_argument(
        "--universal",
        "-u",
        type=str,
        default=None,
        help="Phase 3: Open-vocabulary text prompts for exact sound extraction (e.g., 'typing, dog barking, wind')",
    )
    parser.add_argument("--chunk-size", type=float, default=10.0, help="Process audio in chunks of N seconds")
    parser.add_argument("--output-noise", action="store_true", help="Save extracted noise to a separate file")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging")
    add_codecsep_runtime_arguments(
        parser,
        default_mode="fixed_category",
        default_query_strategy="single_pass",
        default_multistep_steps=0,
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    has_fixed_codecsep_targets = bool(args.codecsep_product_category or args.codecsep_hive_class_id)
    if not any([args.suppress, args.suppress_all, args.universal, has_fixed_codecsep_targets]):
        parser.print_help()
        print(
            "\nERROR: You must specify at least one suppression mode: "
            "--suppress, --suppress-all, --universal, --codecsep-product-category, "
            "or --codecsep-hive-class-id"
        )
        sys.exit(1)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    suppress_categories = [cat.strip() for cat in args.suppress.split(",")] if args.suppress else []
    universal_prompts = [p.strip() for p in args.universal.split(",")] if args.universal else []
    codecsep_kwargs = build_codecsep_call_kwargs_from_args(args)

    logger.info(
        "Initializing suppression engine (backend=%s)...",
        getattr(args, "separator_backend", "waveformer"),
    )
    suppressor = SemanticSuppressor(**build_suppressor_kwargs_from_args(args))
    processor = BatchProcessor(suppressor=suppressor)
    stats = processor.process_file(
        input_path=args.input,
        output_path=args.output,
        suppress_categories=suppress_categories,
        chunk_size_seconds=args.chunk_size,
        detection_threshold=args.threshold,
        aggressiveness=args.aggressiveness,
        suppress_all=args.suppress_all,
        universal_prompts=universal_prompts,
        output_noise=args.output_noise,
        **codecsep_kwargs,
    )

    print("\n=== Processing Complete ===")
    print(f"Input: {stats['input_file']}")
    print(f"Output: {stats['output_file']}")
    if args.output_noise:
        noise_path = str(args.output).replace(".wav", "_noise.wav")
        sf.write(noise_path, stats["noise_audio"], stats["sample_rate"])
        print(f"Noise Output: {noise_path}")
    print(f"Duration: {stats['duration_seconds']:.2f}s")
    print(f"RMS Reduction: {stats['rms_reduction_db']:.2f} dB")
    print(f"Suppressed: {', '.join(stats['suppressed_categories'])}")


if __name__ == "__main__":
    main()
