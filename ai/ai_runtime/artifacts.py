"""Artifact diagnostics for the Python AI runtime.

The runtime intentionally keeps heavyweight model files outside Git. This module
centralizes the "is this checkout actually usable?" checks that used to be
scattered through docs and ad hoc commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ai.ai_runtime.contracts import ArtifactRole, ArtifactStatus
from ai.ai_runtime.utils.paths import (
    get_audiosep_hive15cat_onnx_path,
    get_codecsep_dnrv2_15cat_executorch_path,
    get_codecsep_dnrv2_15cat_onnx_path,
    get_model_exports_path,
    get_models_path,
    get_target_speaker_tsextract_desktop_onnx_path,
    get_target_speaker_windows_bundle_manifest_path,
    get_waveformer_android_metadata_path,
    get_waveformer_android_ort_path,
    get_waveformer_android_required_operators_path,
    get_waveformer_desktop_metadata_path,
    get_waveformer_desktop_onnx_path,
    get_waveformer_model_package_path,
    get_waveformer_source_onnx_path,
)


ARTIFACT_DOWNLOAD_URL = (
    "https://drive.google.com/file/d/1mQq1cagJf5lNTkQqo85s9qRCW1a-hN5c/view?usp=sharing"
)


def get_model_selection_path() -> Path:
    """Return the tracked model-selection manifest path."""

    return get_models_path() / "model_selection.json"


def load_model_selection() -> dict:
    """Load the tracked model-selection manifest."""

    return json.loads(get_model_selection_path().read_text(encoding="utf-8"))


def iter_artifact_checks(*, include_optional: bool = True) -> Iterable[ArtifactStatus]:
    """Yield deterministic artifact checks for product and comparison assets."""

    required: list[tuple[str, Path, str]] = [
        (
            "model_selection",
            get_model_selection_path(),
            "Tracked manifest selecting the active packaged model.",
        ),
        (
            "waveformer_package",
            get_waveformer_model_package_path(),
            "Tracked package manifest for the default Waveformer runtime.",
        ),
        (
            "waveformer_source_onnx",
            get_waveformer_source_onnx_path(),
            "Trusted Waveformer source ONNX restored from ai/models/Exports.",
        ),
        (
            "waveformer_desktop_onnx",
            get_waveformer_desktop_onnx_path(),
            "Desktop Waveformer ONNX artifact.",
        ),
        (
            "waveformer_desktop_metadata",
            get_waveformer_desktop_metadata_path(),
            "Desktop Waveformer ONNX metadata sidecar.",
        ),
        (
            "waveformer_android_ort",
            get_waveformer_android_ort_path(),
            "Android Waveformer ORT artifact.",
        ),
        (
            "waveformer_android_metadata",
            get_waveformer_android_metadata_path(),
            "Android Waveformer ORT metadata sidecar.",
        ),
        (
            "waveformer_android_required_ops",
            get_waveformer_android_required_operators_path(),
            "Android ONNX Runtime reduced-operator config.",
        ),
        (
            "target_speaker_manifest",
            get_target_speaker_windows_bundle_manifest_path(),
            "Target-speaker Windows bundle manifest.",
        ),
        (
            "target_speaker_tsextract_onnx",
            get_target_speaker_tsextract_desktop_onnx_path(),
            "TSExtract ONNX selected-speaker runtime artifact.",
        ),
        (
            "target_speaker_tsextract_external_data",
            get_target_speaker_tsextract_desktop_onnx_path().with_suffix(".onnx.data"),
            "External ONNX data sidecar required by TSExtract.",
        ),
    ]
    for key, path, notes in required:
        yield ArtifactStatus.from_path(
            key=key,
            path=path,
            role=ArtifactRole.REQUIRED,
            notes=notes,
        )

    if not include_optional:
        return

    optional: list[tuple[str, Path, str]] = [
        (
            "exports_root",
            get_model_exports_path(),
            "Ignored portable artifact root; restore this before model-heavy demos.",
        ),
        (
            "audiosep_hive15cat_onnx",
            get_audiosep_hive15cat_onnx_path(),
            "Optional exact-15 AudioSepHive comparison artifact.",
        ),
        (
            "codecsep_dnrv2_15cat_onnx",
            get_codecsep_dnrv2_15cat_onnx_path(),
            "Optional exact-15 CodecSep ONNX comparison artifact.",
        ),
        (
            "codecsep_dnrv2_15cat_executorch",
            get_codecsep_dnrv2_15cat_executorch_path(),
            "Optional exact-15 CodecSep ExecuTorch artifact.",
        ),
    ]
    for key, path, notes in optional:
        yield ArtifactStatus.from_path(
            key=key,
            path=path,
            role=ArtifactRole.OPTIONAL,
            notes=notes,
        )


def check_artifacts(*, include_optional: bool = True) -> list[ArtifactStatus]:
    """Return all artifact diagnostics."""

    return list(iter_artifact_checks(include_optional=include_optional))


def missing_required_artifacts() -> list[ArtifactStatus]:
    """Return required artifacts that are missing in the local checkout."""

    return [
        status
        for status in check_artifacts(include_optional=False)
        if status.role == ArtifactRole.REQUIRED and not status.exists
    ]
