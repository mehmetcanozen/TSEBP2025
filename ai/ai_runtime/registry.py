"""Runtime backend registry for the AI CLI and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from ai.ai_runtime.contracts import BackendId, BackendInfo
from ai.ai_runtime.utils.paths import (
    get_audiosep_hive15cat_onnx_path,
    get_codecsep_dnrv2_15cat_executorch_path,
    get_codecsep_dnrv2_15cat_onnx_path,
    get_codecsep_runtime_fixed_category_mapping_path,
    get_target_speaker_tsextract_desktop_onnx_path,
    get_target_speaker_windows_bundle_manifest_path,
    get_waveformer_desktop_metadata_path,
    get_waveformer_desktop_onnx_path,
    get_waveformer_model_package_path,
)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _waveformer_categories() -> tuple[str, ...]:
    package = _load_json(get_waveformer_model_package_path())
    return tuple(str(item["id"]) for item in package.get("categories", []) if "id" in item)


def _codecsep_product_categories() -> tuple[str, ...]:
    payload = _load_json(get_codecsep_runtime_fixed_category_mapping_path())
    categories = []
    for item in payload.get("product_categories", []) or []:
        name = str(item.get("product_category", "")).strip()
        if name:
            categories.append(name)
    return tuple(categories)


def list_backends() -> tuple[BackendInfo, ...]:
    """Return deterministic backend metadata for the Python runtime surface."""

    return (
        BackendInfo(
            backend_id=BackendId.WAVEFORMER,
            display_name="Waveformer Edge 100ms",
            category_surface="waveformer20",
            runtime_kind="onnx_streaming_target_extractor",
            categories=_waveformer_categories(),
            artifact_paths=(get_waveformer_desktop_onnx_path(), get_waveformer_desktop_metadata_path()),
            notes="Default product semantic suppressor for desktop and Android.",
        ),
        BackendInfo(
            backend_id=BackendId.CODECSEP,
            display_name="CodecSep research runtime",
            category_surface="codecsep_fixed_or_prompt",
            runtime_kind="pytorch_research_separator",
            categories=_codecsep_product_categories(),
            artifact_paths=(),
            notes="Research/runtime path with fixed-category and prompt-compatible modes.",
        ),
        BackendInfo(
            backend_id=BackendId.AUDIOSEP_HIVE15CAT,
            display_name="AudioSepHive15Cat exact-15",
            category_surface="exact15",
            runtime_kind="onnx_category_separator",
            artifact_paths=(get_audiosep_hive15cat_onnx_path(),),
            notes="Optional fixed 15-category ONNX comparison backend.",
        ),
        BackendInfo(
            backend_id=BackendId.CODECSEP_DNRV2_15CAT,
            display_name="CodecSepDNRv2 exact-15",
            category_surface="exact15",
            runtime_kind="onnx_or_executorch_category_separator",
            artifact_paths=(
                get_codecsep_dnrv2_15cat_onnx_path(),
                get_codecsep_dnrv2_15cat_executorch_path(),
            ),
            notes="Optional packaged exact-15 CodecSep ONNX/ExecuTorch backend.",
        ),
        BackendInfo(
            backend_id=BackendId.TARGET_SPEAKER,
            display_name="TargetSpeakerWindows",
            category_surface="reference_speaker",
            runtime_kind="target_speaker_windows_bundle",
            artifact_paths=(
                get_target_speaker_windows_bundle_manifest_path(),
                get_target_speaker_tsextract_desktop_onnx_path(),
            ),
            notes="Selected-speaker suppression using a reference clip.",
        ),
    )


def get_backend(backend_id: str | BackendId) -> BackendInfo:
    """Return metadata for one backend id."""

    normalized = BackendId(str(backend_id))
    for info in list_backends():
        if info.backend_id == normalized:
            return info
    raise KeyError(f"Unknown backend: {backend_id}")
