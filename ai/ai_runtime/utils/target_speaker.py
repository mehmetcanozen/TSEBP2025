"""CLI helpers for selected-speaker suppression.

Kept separate from CodecSep helpers so model-specific ownership stays clear.
"""

from __future__ import annotations

import argparse
from typing import Any

DEFAULT_TARGET_SPEAKER_ENGINE = "tsextract_onnx"
TARGET_SPEAKER_ENGINE_ALIASES = {
    "clearvoice": "clearvoice",
    "quality": "clearvoice",
    "native": "clearvoice",
    "extract": "clearvoice",
    "clearvoice_bundle": "clearvoice_bundle",
    "clearvoice-bundle": "clearvoice_bundle",
    "clearvoice_export": "clearvoice_bundle",
    "clearvoice-export": "clearvoice_bundle",
    "native_bundle": "clearvoice_bundle",
    "native-bundle": "clearvoice_bundle",
    "tsextract": "tsextract",
    "tsextractt": "tsextract",
    "tsexcalibur": "tsextract",
    "fast": "tsextract",
    "tsextract_onnx": "tsextract_onnx",
    "tsextract-onnx": "tsextract_onnx",
    "tsexcalibur_onnx": "tsextract_onnx",
    "tsexcalibur-onnx": "tsextract_onnx",
    "onnx": "tsextract_onnx",
}
TARGET_SPEAKER_ENGINE_CHOICES = tuple(TARGET_SPEAKER_ENGINE_ALIASES.keys())


def normalize_target_speaker_engine(value: str | None) -> str:
    """Normalize public target-speaker engine aliases."""
    normalized = str(value or DEFAULT_TARGET_SPEAKER_ENGINE).strip().casefold()
    if normalized not in TARGET_SPEAKER_ENGINE_ALIASES:
        raise ValueError(
            "target_speaker_engine must be one of: "
            f"{', '.join(TARGET_SPEAKER_ENGINE_CHOICES)}"
        )
    return TARGET_SPEAKER_ENGINE_ALIASES[normalized]


def add_target_speaker_runtime_arguments(
    parser: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    """Add target-speaker suppression arguments to a parser."""
    parser.add_argument(
        "--target-speaker-reference",
        type=str,
        default=None,
        help="Reference WAV/FLAC clip for selected-speaker suppression.",
    )
    parser.add_argument(
        "--target-speaker-model-dir",
        type=str,
        default=None,
        help=(
            "Target-speaker model directory override. Defaults to ai/models/SpeakerSeperator. "
            "The default tsextract_onnx engine uses the packaged ONNX from "
            "ai/models/Exports/TargetSpeakerWindows. For --target-speaker-engine "
            "clearvoice_bundle, point this at the packaged clearvoice_native folder."
        ),
    )
    parser.add_argument(
        "--target-speaker-checkpoint",
        type=str,
        default=None,
        help=(
            "Optional TSExcalibur checkpoint path override. For "
            "--target-speaker-engine tsextract_onnx, this can override the packaged .onnx file."
        ),
    )
    parser.add_argument(
        "--target-speaker-device",
        type=str,
        default=None,
        help="Optional target-speaker execution hint, e.g. cpu, cuda, or cuda:0.",
    )
    parser.add_argument(
        "--target-speaker-engine",
        type=str,
        choices=TARGET_SPEAKER_ENGINE_CHOICES,
        default=DEFAULT_TARGET_SPEAKER_ENGINE,
        help=(
            "Selected-speaker extractor: tsextract_onnx uses the packaged fixed-window "
            "ONNX artifact and is the default; clearvoice uses the native slower/high-quality "
            "separate+match pipeline; clearvoice_bundle uses the packaged native bundle; "
            "tsextract uses the PyTorch TSExcalibur target extractor."
        ),
    )
    parser.add_argument(
        "--target-speaker-reconstruction",
        type=str,
        choices=["direct_subtract", "spectral_mask"],
        default="direct_subtract",
        help=(
            "How selected-speaker suppression builds cleaned audio: direct_subtract "
            "preserves the extractor stem, spectral_mask uses it only as a masking guide."
        ),
    )
    parser.add_argument(
        "--target-speaker-scale",
        type=float,
        default=1.0,
        help="Gain applied to the extracted selected-speaker stem before removal.",
    )
    return parser


def build_target_speaker_suppressor_kwargs_from_args(args: Any) -> dict[str, Any]:
    """Extract SemanticSuppressor construction kwargs for selected-speaker mode."""
    return {
        "target_speaker_model_dir": getattr(args, "target_speaker_model_dir", None),
        "target_speaker_checkpoint_path": getattr(args, "target_speaker_checkpoint", None),
        "target_speaker_device": getattr(args, "target_speaker_device", None),
        "target_speaker_engine": normalize_target_speaker_engine(
            getattr(args, "target_speaker_engine", DEFAULT_TARGET_SPEAKER_ENGINE),
        ),
    }


def build_target_speaker_call_kwargs_from_args(args: Any) -> dict[str, Any]:
    """Extract per-call controls for selected-speaker suppression."""
    return {
        "target_speaker_reference_path": getattr(args, "target_speaker_reference", None),
        "target_speaker_model_dir": getattr(args, "target_speaker_model_dir", None),
        "target_speaker_checkpoint_path": getattr(args, "target_speaker_checkpoint", None),
        "target_speaker_device": getattr(args, "target_speaker_device", None),
        "target_speaker_engine": normalize_target_speaker_engine(
            getattr(args, "target_speaker_engine", DEFAULT_TARGET_SPEAKER_ENGINE),
        ),
        "target_speaker_reconstruction": getattr(
            args,
            "target_speaker_reconstruction",
            "direct_subtract",
        ),
        "target_speaker_scale": float(getattr(args, "target_speaker_scale", 1.0) or 1.0),
    }


__all__ = [
    "DEFAULT_TARGET_SPEAKER_ENGINE",
    "TARGET_SPEAKER_ENGINE_ALIASES",
    "TARGET_SPEAKER_ENGINE_CHOICES",
    "add_target_speaker_runtime_arguments",
    "build_target_speaker_call_kwargs_from_args",
    "build_target_speaker_suppressor_kwargs_from_args",
    "normalize_target_speaker_engine",
]
