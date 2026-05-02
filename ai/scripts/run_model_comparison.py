"""Run final-pitch audio suppression comparisons across available runtimes.

The script reads audio files from ``ai/data/audio/raw`` by default, writes cleaned
outputs under ``ai/data/audio/processed/final_pitch_comparison_*``, and records
per-run speed, size, and signal-change metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.ai_runtime.batch.batch_processor import BatchProcessor
from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.separation.waveformer_onnx_stream import WaveformerOnnxStream
from ai.ai_runtime.utils.paths import (
    get_audiosep_hive15cat_onnx_path,
    get_codecsep_dnrv2_15cat_executorch_path,
    get_codecsep_dnrv2_15cat_onnx_path,
    get_data_audio_path,
    get_waveformer_desktop_onnx_path,
    get_waveformer_checkpoint_path,
    get_waveformer_config_path,
    get_waveformer_model_path,
    get_waveformer_model_package_path,
    iter_existing_codecsep_checkpoints,
)


LOGGER = logging.getLogger("final_pitch_comparison")
AUDIO_EXTENSIONS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}


EXACT15_TARGETS = (
    "speech",
    "music",
    "dog barking",
    "car engine",
    "footsteps",
    "rain",
    "wind",
    "keyboard typing",
    "phone ringing",
    "crowd noise",
    "bird singing",
    "water flowing",
    "door knocking",
    "alarm",
    "background noise",
)


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    backend: str
    target_surface: str
    runtime: str = "python"
    suppressor_kwargs: dict[str, Any] = field(default_factory=dict)
    process_kwargs: dict[str, Any] = field(default_factory=dict)
    artifact_paths: tuple[Path, ...] = ()
    notes: str = ""
    runnable: bool = True


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
        target = suppress_categories[0] if suppress_categories else "dog"
        audio, sample_rate = sf.read(input_path, dtype="float32")
        cleaned_mono, runtime_stats = self.runner.suppress(
            audio,
            int(sample_rate),
            [target],
            aggressiveness=aggressiveness,
        )
        original_mono = _mono(np.asarray(audio, dtype=np.float32))
        residual = original_mono[: cleaned_mono.shape[0]] - cleaned_mono
        cleaned = _project_residual_back(np.asarray(audio, dtype=np.float32), residual)
        sf.write(output_path, cleaned, int(sample_rate))

        stats = {
            "sample_rate": int(sample_rate),
            "duration_seconds": float(original_mono.shape[0] / max(float(sample_rate), 1.0)),
            "rms_reduction_db": _db_ratio(_rms(original_mono), _rms(cleaned_mono)),
            "noise_audio": residual.astype(np.float32) if output_noise else None,
        }
        stats.update(runtime_stats)
        return stats


def _model_specs() -> dict[str, ModelSpec]:
    waveformer_onnx = get_waveformer_desktop_onnx_path()
    waveformer_pte = (
        get_waveformer_model_path()
        / "WFExports"
        / "executorch_recommended_100ms"
        / "semantic_hearing_100ms_portable.pte"
    )
    audiosep_hive_pte = PROJECT_ROOT / "ai" / "models" / "AudioSepHive15Cat" / "frozensep_hive_15cat.pte"
    clapsep_onnx = PROJECT_ROOT / "ai" / "models" / "ClapSepHive15Cat" / "frozensep_clapsep_15cat.onnx"

    specs = [
        ModelSpec(
            model_id="waveformer",
            display_name="Waveformer PyTorch runtime",
            backend="waveformer",
            target_surface="legacy",
            suppressor_kwargs={"separator_backend": "waveformer"},
            artifact_paths=(get_waveformer_config_path(), get_waveformer_checkpoint_path()),
            notes="Default desktop separator; YAMNet-category to Waveformer-target routing.",
        ),
        ModelSpec(
            model_id="pure_audiosep",
            display_name="Pure AudioSep text-query runtime",
            backend="waveformer",
            target_surface="universal",
            suppressor_kwargs={"separator_backend": "waveformer"},
            artifact_paths=(
                PROJECT_ROOT / "ai" / "models" / "AudioSep" / "checkpoint" / "audiosep_base_4M_steps.ckpt",
            ),
            notes="Open-vocabulary AudioSep path through SemanticSuppressor universal prompts.",
        ),
        ModelSpec(
            model_id="audiosep_hive15cat_onnx",
            display_name="AudioSep-Hive exact-15 ONNX",
            backend="audiosep_hive15cat",
            target_surface="exact15",
            runtime="onnx",
            suppressor_kwargs={"separator_backend": "audiosep_hive15cat"},
            artifact_paths=(get_audiosep_hive15cat_onnx_path(),),
            notes="Fixed 15-category AudioSep-Hive export with precomputed category embeddings.",
        ),
        ModelSpec(
            model_id="codecsep_normal_compat",
            display_name="CodecSep prompt-compatible checkpoint",
            backend="codecsep",
            target_surface="legacy",
            suppressor_kwargs={"separator_backend": "codecsep"},
            process_kwargs={"codecsep_mode": "compat"},
            artifact_paths=tuple(iter_existing_codecsep_checkpoints()),
            notes="Legacy/prompt-compatible CodecSep path; availability depends on local checkpoint assets.",
        ),
        ModelSpec(
            model_id="codecsep_dnrv2_15cat_onnx",
            display_name="CodecSep DNRv2 exact-15 ONNX",
            backend="codecsep_dnrv2_15cat",
            target_surface="exact15",
            runtime="onnx",
            suppressor_kwargs={
                "separator_backend": "codecsep_dnrv2_15cat",
                "codecsep_dnrv2_15cat_runtime": "onnx",
            },
            process_kwargs={"codecsep_dnrv2_15cat_runtime": "onnx"},
            artifact_paths=(get_codecsep_dnrv2_15cat_onnx_path(),),
            notes="Frozen class/category runtime using ONNX Runtime and category_idx input.",
        ),
        ModelSpec(
            model_id="codecsep_dnrv2_15cat_executorch",
            display_name="CodecSep DNRv2 exact-15 ExecuTorch",
            backend="codecsep_dnrv2_15cat",
            target_surface="exact15",
            runtime="executorch",
            suppressor_kwargs={
                "separator_backend": "codecsep_dnrv2_15cat",
                "codecsep_dnrv2_15cat_runtime": "executorch",
            },
            process_kwargs={"codecsep_dnrv2_15cat_runtime": "executorch"},
            artifact_paths=(get_codecsep_dnrv2_15cat_executorch_path(),),
            notes="Frozen class/category runtime using ExecuTorch label_vector input.",
        ),
        ModelSpec(
            model_id="waveformer_onnx_export",
            display_name="Waveformer 100 ms ONNX export",
            backend="waveformer",
            target_surface="waveformer20",
            runtime="onnx",
            artifact_paths=(waveformer_onnx,),
            notes="Desktop-equivalent stateful ONNX target extractor with residual subtraction.",
            runnable=True,
        ),
        ModelSpec(
            model_id="waveformer_executorch_export",
            display_name="Waveformer 100 ms ExecuTorch export",
            backend="waveformer",
            target_surface="legacy",
            runtime="executorch",
            artifact_paths=(waveformer_pte,),
            notes="Exported streaming artifact exists, but ai_runtime has no Python batch adapter for it yet.",
            runnable=False,
        ),
        ModelSpec(
            model_id="audiosep_hive15cat_executorch",
            display_name="AudioSep-Hive exact-15 ExecuTorch",
            backend="audiosep_hive15cat",
            target_surface="exact15",
            runtime="executorch",
            artifact_paths=(audiosep_hive_pte,),
            notes="Declared for comparison tracking; no local PTE artifact/runtime wrapper was found.",
            runnable=False,
        ),
        ModelSpec(
            model_id="clapsep_hive15cat_onnx",
            display_name="CLAPSep-Hive exact-15 ONNX",
            backend="clapsep_hive15cat",
            target_surface="exact15",
            runtime="onnx",
            artifact_paths=(clapsep_onnx,),
            notes="Artifact exists from FrozenSep, but ai_runtime has no CLAPSep batch adapter yet.",
            runnable=False,
        ),
    ]
    return {spec.model_id: spec for spec in specs}


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return slug.strip("_") or "target"


def _rms(audio: np.ndarray) -> float:
    array = np.asarray(audio, dtype=np.float64)
    if array.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(array))))


def _peak(audio: np.ndarray) -> float:
    array = np.asarray(audio, dtype=np.float64)
    if array.size == 0:
        return 0.0
    return float(np.max(np.abs(array)))


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
    if original.ndim == 1:
        length = min(original.shape[0], residual.shape[0])
        cleaned = original.copy()
        cleaned[:length] = cleaned[:length] - residual[:length]
        return np.clip(cleaned, -1.0, 1.0)
    length = min(original.shape[0], residual.shape[0])
    cleaned = original.copy()
    cleaned[:length, :] = cleaned[:length, :] - residual[:length, None]
    return np.clip(cleaned, -1.0, 1.0)


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    a_mono = _mono(a)
    b_mono = _mono(b)
    length = min(a_mono.shape[0], b_mono.shape[0])
    if length < 2:
        return None
    a_vec = a_mono[:length]
    b_vec = b_mono[:length]
    if float(np.std(a_vec)) < 1.0e-12 or float(np.std(b_vec)) < 1.0e-12:
        return None
    return float(np.corrcoef(a_vec, b_vec)[0, 1])


def _artifact_size_bytes(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        if path.is_file():
            total += path.stat().st_size
    return total


def _artifact_status(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
        }
        for path in paths
    ]


def _input_files(input_dir: Path, max_files: int | None) -> list[Path]:
    files = [
        path
        for path in sorted(input_dir.iterdir())
        if path.is_file() and path.suffix.casefold() in AUDIO_EXTENSIONS
    ]
    if max_files is not None:
        return files[: max(0, max_files)]
    return files


def _infer_exact15_target(path: Path) -> str:
    name = path.stem.casefold()
    if "keyboard" in name or "typing" in name:
        return "keyboard typing"
    if "bark" in name or "dog" in name:
        return "dog barking"
    if "siren" in name or "alarm" in name:
        return "alarm"
    if "boat" in name or "car" in name or "engine" in name:
        return "car engine"
    if "office" in name:
        return "background noise"
    if "music" in name:
        return "music"
    if "speech" in name:
        return "speech"
    return "background noise"


def _infer_legacy_target(path: Path) -> str:
    name = path.stem.casefold()
    if "keyboard" in name or "typing" in name:
        return "typing"
    if "bark" in name or "dog" in name or "cat" in name:
        return "pets"
    if "phone" in name:
        return "phone"
    if "boat" in name or "car" in name or "traffic" in name or "engine" in name:
        return "traffic"
    if "music" in name:
        return "music"
    if "siren" in name or "alarm" in name:
        return "alarm"
    if "office" in name:
        return "typing"
    if "speech" in name:
        return "speech"
    return "misc"


def _infer_waveformer20_target(path: Path) -> str:
    name = path.stem.casefold()
    if "keyboard" in name or "typing" in name:
        return "computer_typing"
    if "bark" in name or "dog" in name:
        return "dog"
    if "cat" in name:
        return "cat"
    if "siren" in name:
        return "siren"
    if "alarm" in name:
        return "alarm_clock"
    if "bird" in name:
        return "birds_chirping"
    if "music" in name:
        return "music"
    if "speech" in name:
        return "speech"
    return "dog"


def _target_for_file(spec: ModelSpec, path: Path, args: argparse.Namespace) -> str:
    if args.target:
        return args.target
    if spec.target_surface == "legacy" and args.legacy_target:
        return args.legacy_target
    if spec.target_surface == "waveformer20" and args.legacy_target:
        return args.legacy_target
    if spec.target_surface == "exact15" and args.exact15_target:
        return args.exact15_target
    if spec.target_surface == "universal":
        return args.universal_prompt or _infer_exact15_target(path)
    if spec.target_surface == "legacy":
        return _infer_legacy_target(path)
    if spec.target_surface == "waveformer20":
        return _infer_waveformer20_target(path)
    return _infer_exact15_target(path)


def _build_processor(spec: ModelSpec) -> BatchProcessor | WaveformerOnnxBatchProcessor:
    if spec.model_id == "waveformer_onnx_export":
        return WaveformerOnnxBatchProcessor()
    suppressor = SemanticSuppressor(**spec.suppressor_kwargs)
    return BatchProcessor(suppressor=suppressor)


def _run_one(
    *,
    processor: BatchProcessor,
    spec: ModelSpec,
    input_path: Path,
    output_path: Path,
    noise_path: Path,
    target: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    suppress_categories = [] if spec.target_surface == "universal" else [target]
    universal_prompts = [target] if spec.target_surface == "universal" else []
    process_kwargs = dict(spec.process_kwargs)
    start = time.perf_counter()
    stats = processor.process_file(
        input_path=input_path,
        output_path=output_path,
        suppress_categories=suppress_categories,
        chunk_size_seconds=args.chunk_size,
        detection_threshold=args.threshold,
        aggressiveness=args.aggressiveness,
        universal_prompts=universal_prompts,
        output_noise=True,
        **process_kwargs,
    )
    processing_seconds = time.perf_counter() - start

    if stats.get("noise_audio") is not None:
        sf.write(noise_path, stats["noise_audio"], int(stats["sample_rate"]))
    else:
        noise_path = Path("")

    original_audio, _ = sf.read(input_path, dtype="float32")
    cleaned_audio, _ = sf.read(output_path, dtype="float32")
    length = min(original_audio.shape[0], cleaned_audio.shape[0])
    original_aligned = np.asarray(original_audio[:length], dtype=np.float32)
    cleaned_aligned = np.asarray(cleaned_audio[:length], dtype=np.float32)
    residual = original_aligned - cleaned_aligned

    original_rms = _rms(original_aligned)
    cleaned_rms = _rms(cleaned_aligned)
    residual_rms = _rms(residual)
    duration_seconds = float(stats["duration_seconds"])

    return {
        "status": "ok",
        "model_id": spec.model_id,
        "display_name": spec.display_name,
        "backend": spec.backend,
        "runtime": spec.runtime,
        "input_file": str(input_path),
        "target": target,
        "target_surface": spec.target_surface,
        "output_file": str(output_path),
        "noise_file": str(noise_path) if str(noise_path) else "",
        "sample_rate": int(stats["sample_rate"]),
        "duration_seconds": duration_seconds,
        "processing_seconds": processing_seconds,
        "real_time_factor": processing_seconds / max(duration_seconds, 1.0e-12),
        "original_rms": original_rms,
        "cleaned_rms": cleaned_rms,
        "residual_rms": residual_rms,
        "rms_reduction_db": float(stats["rms_reduction_db"]),
        "residual_to_original_db": _db_ratio(residual_rms, original_rms),
        "original_peak": _peak(original_aligned),
        "cleaned_peak": _peak(cleaned_aligned),
        "residual_peak": _peak(residual),
        "clip_fraction_cleaned": float(np.mean(np.abs(cleaned_aligned) >= 0.999))
        if cleaned_aligned.size
        else 0.0,
        "original_cleaned_correlation": _correlation(original_aligned, cleaned_aligned),
        "artifact_size_bytes": _artifact_size_bytes(spec.artifact_paths),
        "notes": spec.notes,
        "error": "",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "status",
        "model_id",
        "display_name",
        "backend",
        "runtime",
        "input_file",
        "target",
        "target_surface",
        "output_file",
        "noise_file",
        "sample_rate",
        "duration_seconds",
        "processing_seconds",
        "real_time_factor",
        "original_rms",
        "cleaned_rms",
        "residual_rms",
        "rms_reduction_db",
        "residual_to_original_db",
        "original_peak",
        "cleaned_peak",
        "residual_peak",
        "clip_fraction_cleaned",
        "original_cleaned_correlation",
        "artifact_size_bytes",
        "notes",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _selected_specs(args: argparse.Namespace, specs: dict[str, ModelSpec]) -> list[ModelSpec]:
    if args.models == ["auto"]:
        names = [
            "waveformer",
            "audiosep_hive15cat_onnx",
            "codecsep_dnrv2_15cat_onnx",
            "codecsep_dnrv2_15cat_executorch",
        ]
    elif args.models == ["exact15"]:
        names = [
            "audiosep_hive15cat_onnx",
            "codecsep_dnrv2_15cat_onnx",
            "codecsep_dnrv2_15cat_executorch",
        ]
    elif args.models == ["all"]:
        names = list(specs)
    else:
        names = args.models

    selected: list[ModelSpec] = []
    for name in names:
        if name not in specs:
            raise SystemExit(
                f"Unknown model '{name}'. Use --list-models to inspect available ids.",
            )
        spec = specs[name]
        if spec.runnable or args.include_unsupported:
            selected.append(spec)
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run final-pitch model comparisons on local raw audio files.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=get_data_audio_path("raw"),
        help="Directory containing input audio files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Parent output folder. Defaults to ai/data/audio/processed/final_pitch_comparison_<timestamp>.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["auto"],
        help="Model ids to run, or 'auto'/'exact15'/'all'. Use --list-models for ids.",
    )
    parser.add_argument("--max-files", type=int, default=None, help="Limit number of input files.")
    parser.add_argument("--chunk-size", type=float, default=10.0, help="Batch chunk size in seconds.")
    parser.add_argument("--threshold", type=float, default=0.5, help="Detection threshold.")
    parser.add_argument("--aggressiveness", type=float, default=1.5, help="Suppression strength.")
    parser.add_argument("--target", default=None, help="Override target for every model.")
    parser.add_argument("--legacy-target", default=None, help="Override Waveformer/legacy CodecSep target.")
    parser.add_argument("--exact15-target", choices=EXACT15_TARGETS, default=None, help="Override exact-15 target.")
    parser.add_argument("--universal-prompt", default=None, help="Override pure AudioSep text prompt.")
    parser.add_argument("--dry-run", action="store_true", help="Plan runs without loading models.")
    parser.add_argument("--list-models", action="store_true", help="Print model registry JSON and exit.")
    parser.add_argument(
        "--include-unsupported",
        action="store_true",
        help="Include non-runnable/export-only models as skipped rows.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first model/file failure.")
    parser.add_argument(
        "--continue-failed-model",
        action="store_true",
        help="Keep trying later input files after a model fails on one file.",
    )
    parser.add_argument(
        "--tracebacks",
        action="store_true",
        help="Print full exception tracebacks instead of concise errors.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    return parser


def _log_failure(message: str, exc: Exception, args: argparse.Namespace, *values: object) -> None:
    if args.tracebacks or args.debug:
        LOGGER.exception(message, *values)
    else:
        LOGGER.error("%s: %r", message % values if values else message, exc)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    specs = _model_specs()
    if args.list_models:
        print(
            json.dumps(
                {
                    key: {
                        "display_name": spec.display_name,
                        "backend": spec.backend,
                        "runtime": spec.runtime,
                        "target_surface": spec.target_surface,
                        "runnable": spec.runnable,
                        "artifact_status": _artifact_status(spec.artifact_paths),
                        "notes": spec.notes,
                    }
                    for key, spec in specs.items()
                },
                indent=2,
            ),
        )
        return 0

    input_files = _input_files(args.input_dir, args.max_files)
    if not input_files:
        raise SystemExit(f"No audio files found in {args.input_dir}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_root = args.output_root or (
        get_data_audio_path("processed") / f"final_pitch_comparison_{timestamp}"
    )
    output_root.mkdir(parents=True, exist_ok=True)

    selected = _selected_specs(args, specs)
    rows: list[dict[str, Any]] = []
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir": str(args.input_dir),
        "output_root": str(output_root),
        "models": {},
        "input_files": [str(path) for path in input_files],
        "dry_run": bool(args.dry_run),
    }

    for spec in selected:
        manifest["models"][spec.model_id] = {
            "display_name": spec.display_name,
            "backend": spec.backend,
            "runtime": spec.runtime,
            "target_surface": spec.target_surface,
            "runnable": spec.runnable,
            "artifact_status": _artifact_status(spec.artifact_paths),
            "notes": spec.notes,
        }

    if args.dry_run:
        for spec in selected:
            for input_path in input_files:
                rows.append(
                    {
                        "status": "planned" if spec.runnable else "unsupported",
                        "model_id": spec.model_id,
                        "display_name": spec.display_name,
                        "backend": spec.backend,
                        "runtime": spec.runtime,
                        "input_file": str(input_path),
                        "target": _target_for_file(spec, input_path, args),
                        "target_surface": spec.target_surface,
                        "artifact_size_bytes": _artifact_size_bytes(spec.artifact_paths),
                        "notes": spec.notes,
                        "error": "" if spec.runnable else "No batch adapter in ai_runtime.",
                    },
                )
    else:
        for spec in selected:
            if not spec.runnable:
                for input_path in input_files:
                    rows.append(
                        {
                            "status": "unsupported",
                            "model_id": spec.model_id,
                            "display_name": spec.display_name,
                            "backend": spec.backend,
                            "runtime": spec.runtime,
                            "input_file": str(input_path),
                            "target": _target_for_file(spec, input_path, args),
                            "target_surface": spec.target_surface,
                            "artifact_size_bytes": _artifact_size_bytes(spec.artifact_paths),
                            "notes": spec.notes,
                            "error": "No batch adapter in ai_runtime.",
                        },
                    )
                continue

            LOGGER.info("Loading %s", spec.model_id)
            try:
                processor = _build_processor(spec)
            except Exception as exc:
                _log_failure("Failed to initialize %s", exc, args, spec.model_id)
                for input_path in input_files:
                    rows.append(
                        {
                            "status": "failed_init",
                            "model_id": spec.model_id,
                            "display_name": spec.display_name,
                            "backend": spec.backend,
                            "runtime": spec.runtime,
                            "input_file": str(input_path),
                            "target": _target_for_file(spec, input_path, args),
                            "target_surface": spec.target_surface,
                            "artifact_size_bytes": _artifact_size_bytes(spec.artifact_paths),
                            "notes": spec.notes,
                            "error": repr(exc),
                        },
                    )
                if args.fail_fast:
                    break
                continue

            for index, input_path in enumerate(input_files):
                target = _target_for_file(spec, input_path, args)
                model_output_dir = output_root / spec.model_id
                model_output_dir.mkdir(parents=True, exist_ok=True)
                suffix = _slug(target)
                output_path = model_output_dir / f"{input_path.stem}__{suffix}__clean.wav"
                noise_path = model_output_dir / f"{input_path.stem}__{suffix}__noise.wav"

                LOGGER.info("%s -> %s target=%s", spec.model_id, input_path.name, target)
                try:
                    rows.append(
                        _run_one(
                            processor=processor,
                            spec=spec,
                            input_path=input_path,
                            output_path=output_path,
                            noise_path=noise_path,
                            target=target,
                            args=args,
                        ),
                    )
                except Exception as exc:
                    _log_failure("Failed %s on %s", exc, args, spec.model_id, input_path.name)
                    rows.append(
                        {
                            "status": "failed_run",
                            "model_id": spec.model_id,
                            "display_name": spec.display_name,
                            "backend": spec.backend,
                            "runtime": spec.runtime,
                            "input_file": str(input_path),
                            "target": target,
                            "target_surface": spec.target_surface,
                            "output_file": str(output_path),
                            "noise_file": str(noise_path),
                            "artifact_size_bytes": _artifact_size_bytes(spec.artifact_paths),
                            "notes": spec.notes,
                            "error": repr(exc),
                        },
                    )
                    if args.fail_fast:
                        break
                    if not args.continue_failed_model:
                        for skipped_path in input_files[index + 1 :]:
                            skipped_target = _target_for_file(spec, skipped_path, args)
                            skipped_suffix = _slug(skipped_target)
                            rows.append(
                                {
                                    "status": "skipped_after_model_failure",
                                    "model_id": spec.model_id,
                                    "display_name": spec.display_name,
                                    "backend": spec.backend,
                                    "runtime": spec.runtime,
                                    "input_file": str(skipped_path),
                                    "target": skipped_target,
                                    "target_surface": spec.target_surface,
                                    "output_file": str(
                                        model_output_dir
                                        / f"{skipped_path.stem}__{skipped_suffix}__clean.wav"
                                    ),
                                    "noise_file": str(
                                        model_output_dir
                                        / f"{skipped_path.stem}__{skipped_suffix}__noise.wav"
                                    ),
                                    "artifact_size_bytes": _artifact_size_bytes(spec.artifact_paths),
                                    "notes": spec.notes,
                                    "error": (
                                        "Skipped because this model already failed in this run: "
                                        f"{repr(exc)}"
                                    ),
                                },
                            )
                        LOGGER.warning(
                            "Skipping remaining files for %s after first failure. "
                            "Use --continue-failed-model to keep trying each file.",
                            spec.model_id,
                        )
                        break
            if args.fail_fast and rows and rows[-1]["status"].startswith("failed"):
                break

    manifest["rows"] = rows
    _write_csv(output_root / "comparison_summary.csv", rows)
    (output_root / "comparison_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote comparison outputs to: {output_root}")
    print(f"Rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
