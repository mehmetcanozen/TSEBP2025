"""
Freeze the prompt-based CodecSep checkpoint into CodecSepDNRv2_15Cat.

This script converts the prompt-conditioned CodecSep teacher into a 15-category
class-id model, writes reproducibility assets beside the frozen checkpoint, and
exports static-shape ONNX / ExecuTorch artifacts for packaged deployment.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import platform
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
import torch.nn.functional as F
import yaml
from torch import nn

from ai.ai_runtime.separation.codecsep.model import CodecSep
from ai.ai_runtime.separation.codecsep_separator import CodecSepSeparator
from ai.ai_runtime.utils.paths import (
    get_codecsep_default_run_dir,
    get_codecsep_dnrv2_15cat_categories_path,
    get_codecsep_dnrv2_15cat_embedding_init_path,
    get_codecsep_dnrv2_15cat_executorch_path,
    get_codecsep_dnrv2_15cat_freeze_manifest_path,
    get_codecsep_dnrv2_15cat_freeze_spec_path,
    get_codecsep_dnrv2_15cat_frozen_checkpoint_path,
    get_codecsep_dnrv2_15cat_model_path,
    get_codecsep_dnrv2_15cat_onnx_path,
    resolve_codecsep_checkpoint_path,
)

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

logger = logging.getLogger(__name__)

SEGMENT_SECONDS = 2.0
SAMPLE_RATE = 16_000
SEGMENT_SAMPLES = int(SAMPLE_RATE * SEGMENT_SECONDS)
OVERLAP_SECONDS = 0.5
NULL_CLASS_ID = 15
ONNX_OPSET = 17
ONNX_PARITY_LABELS = ("speech", "keyboard typing", "alarm")
EXECUTORCH_PARITY_LABELS = ("speech", "dog barking")


@dataclass(frozen=True)
class FrozenCategorySpec:
    class_id: int
    id: str
    label: str
    prompts: tuple[str, ...]


@dataclass(frozen=True)
class FreezeArtifacts:
    package_dir: Path
    categories_yaml: Path
    categories_txt: Path
    freeze_spec_yaml: Path
    embedding_init_path: Path
    freeze_manifest_path: Path
    frozen_checkpoint_path: Path
    onnx_path: Path
    onnx_sidecar_path: Path
    executorch_path: Path
    executorch_sidecar_path: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_yaml(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def resolve_artifact_paths(package_dir: Path) -> FreezeArtifacts:
    categories_yaml = get_codecsep_dnrv2_15cat_categories_path()
    return FreezeArtifacts(
        package_dir=package_dir,
        categories_yaml=categories_yaml,
        categories_txt=categories_yaml.with_suffix(".txt"),
        freeze_spec_yaml=get_codecsep_dnrv2_15cat_freeze_spec_path(),
        embedding_init_path=get_codecsep_dnrv2_15cat_embedding_init_path(),
        freeze_manifest_path=get_codecsep_dnrv2_15cat_freeze_manifest_path(),
        frozen_checkpoint_path=get_codecsep_dnrv2_15cat_frozen_checkpoint_path(),
        onnx_path=get_codecsep_dnrv2_15cat_onnx_path(),
        onnx_sidecar_path=get_codecsep_dnrv2_15cat_onnx_path().with_suffix(".onnx.json"),
        executorch_path=get_codecsep_dnrv2_15cat_executorch_path(),
        executorch_sidecar_path=get_codecsep_dnrv2_15cat_executorch_path().with_suffix(".pte.json"),
    )


def override_export_paths(
    artifacts: FreezeArtifacts,
    *,
    onnx_path: Path,
    executorch_path: Path,
) -> FreezeArtifacts:
    resolved_onnx = onnx_path.resolve()
    resolved_pte = executorch_path.resolve()
    return FreezeArtifacts(
        package_dir=artifacts.package_dir,
        categories_yaml=artifacts.categories_yaml,
        categories_txt=artifacts.categories_txt,
        freeze_spec_yaml=artifacts.freeze_spec_yaml,
        embedding_init_path=artifacts.embedding_init_path,
        freeze_manifest_path=artifacts.freeze_manifest_path,
        frozen_checkpoint_path=artifacts.frozen_checkpoint_path,
        onnx_path=resolved_onnx,
        onnx_sidecar_path=resolved_onnx.with_suffix(".onnx.json"),
        executorch_path=resolved_pte,
        executorch_sidecar_path=resolved_pte.with_suffix(".pte.json"),
    )


def load_freeze_categories(freeze_spec_path: Path) -> list[FrozenCategorySpec]:
    payload = _load_yaml(freeze_spec_path)
    categories = list(payload.get("categories") or [])
    if len(categories) != 15:
        raise RuntimeError(
            f"Expected 15 frozen categories in {freeze_spec_path}, got {len(categories)}."
        )
    resolved: list[FrozenCategorySpec] = []
    for class_id, entry in enumerate(categories):
        prompts = tuple(str(item).strip() for item in list(entry.get("prompts") or []) if str(item).strip())
        if len(prompts) < 3:
            raise RuntimeError(
                f"Frozen category '{entry.get('label', entry.get('id'))}' must define three prompts."
            )
        resolved.append(
            FrozenCategorySpec(
                class_id=class_id,
                id=str(entry["id"]),
                label=str(entry.get("label", entry["id"])),
                prompts=prompts[:3],
            )
        )
    return resolved


def read_categories_txt(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def infer_conditioning_variant(
    conditioning_cfg: Mapping[str, Any] | None,
    state_dict: Mapping[str, Any],
) -> str:
    cfg = dict(conditioning_cfg or {})
    explicit = str(cfg.get("variant", "")).strip().lower()
    if explicit:
        return explicit
    if any(str(key).startswith("film.gate") for key in state_dict):
        return "adaln_zero"
    return "film"


def infer_condition_size(
    conditioning_cfg: Mapping[str, Any] | None,
    state_dict: Mapping[str, Any],
) -> int:
    cfg = dict(conditioning_cfg or {})
    explicit = int(cfg.get("condition_size", 0) or 0)
    if explicit > 0:
        return explicit
    for key in (
        "film.beta1.weight",
        "film.gamma1.weight",
        "film.block->layers->0->beta1.weight",
        "film.block->layers->0->gamma1.weight",
    ):
        tensor = state_dict.get(key)
        if torch.is_tensor(tensor) and tensor.ndim >= 2:
            return int(tensor.shape[-1])
    raise RuntimeError("Unable to infer CodecSep conditioning size from the source checkpoint.")


def build_conditioning_cfg(
    source_conditioning_cfg: Mapping[str, Any] | None,
    state_dict: Mapping[str, Any],
    *,
    mode: str,
    num_classes: int | None = None,
) -> dict[str, Any]:
    conditioning = dict(source_conditioning_cfg or {})
    conditioning["mode"] = mode
    conditioning["variant"] = infer_conditioning_variant(conditioning, state_dict)
    conditioning["condition_size"] = infer_condition_size(conditioning, state_dict)
    if mode == "class_id":
        conditioning["num_classes"] = int(num_classes or 0)
        conditioning["zero_for_absent"] = True
        conditioning["use_zero_for_null"] = True
    else:
        conditioning.pop("num_classes", None)
    return conditioning


def build_runtime_model_kwargs(
    source_model_kwargs: Mapping[str, Any],
    state_dict: Mapping[str, Any],
    *,
    mode: str,
    num_classes: int | None = None,
) -> dict[str, Any]:
    kwargs = dict(source_model_kwargs)
    kwargs["tracks"] = ["target"]
    kwargs["mode"] = "single_target"
    kwargs["residual_mode"] = "waveform_subtract"
    kwargs["conditioning"] = build_conditioning_cfg(
        kwargs.get("conditioning"),
        state_dict,
        mode=mode,
        num_classes=num_classes,
    )
    if mode == "class_id":
        kwargs["num_classes"] = int(num_classes or 0)
    else:
        kwargs.pop("num_classes", None)
    return kwargs


def average_normalized_embeddings(embeddings: torch.Tensor, *, eps: float = 1.0e-8) -> torch.Tensor:
    normalized = F.normalize(embeddings.detach().float(), dim=-1, eps=eps)
    return normalized.mean(dim=0)


def load_source_bundle(
    source_run_dir: Path,
) -> tuple[Path, Path | None, int, dict[str, Any], dict[str, Any]]:
    resolved_checkpoint = resolve_codecsep_checkpoint_path(source_run_dir)
    if not resolved_checkpoint.exists():
        raise FileNotFoundError(f"CodecSep source checkpoint was not found: {resolved_checkpoint}")

    separator = CodecSepSeparator(checkpoint_path=source_run_dir, device="cpu")
    sample_rate, config_kwargs, _inference_cfg = separator._load_model_config(resolved_checkpoint)
    loaded = torch.load(resolved_checkpoint, map_location="cpu", weights_only=False)
    if isinstance(loaded, dict) and "state_dict" in loaded:
        state_dict = dict(loaded["state_dict"])
        metadata_kwargs = dict(((loaded.get("metadata") or {}).get("kwargs") or {}))
    else:
        state_dict = dict(loaded)
        metadata_kwargs = {}

    model_kwargs = separator._merge_model_kwargs(config_kwargs, metadata_kwargs)
    separator._ensure_clap_config(model_kwargs, state_dict)
    run_dir = separator._infer_run_dir(source_run_dir, resolved_checkpoint)
    config_path = None
    if run_dir is not None:
        for candidate in (
            run_dir / ".hydra" / "config.yaml",
            run_dir / "config" / "hydra_snapshot" / "config.yaml",
            run_dir.parent / "config" / "hydra_snapshot" / "config.yaml",
        ):
            if candidate.exists():
                config_path = candidate
                break
    return resolved_checkpoint, config_path, int(sample_rate), model_kwargs, state_dict


def instantiate_model(sample_rate: int, model_kwargs: Mapping[str, Any]) -> CodecSep:
    return CodecSepSeparator._instantiate_model(
        CodecSep,
        sample_rate=sample_rate,
        model_kwargs=model_kwargs,
    )


def bake_weight_norm_parametrizations(model: nn.Module) -> int:
    baked = 0
    parametrizations = getattr(torch.nn.utils, "parametrize", None)
    if parametrizations is None:
        return baked

    for module in model.modules():
        module_parametrizations = getattr(module, "parametrizations", None)
        if module_parametrizations is None:
            continue
        if not hasattr(module_parametrizations, "weight"):
            continue
        parametrizations.remove_parametrizations(
            module,
            "weight",
            leave_parametrized=True,
        )
        baked += 1
    return baked


def copy_compatible_weights(source_model: CodecSep, target_model: CodecSep) -> dict[str, Any]:
    source_state = source_model.state_dict()
    target_state = target_model.state_dict()
    copied: list[str] = []
    skipped: list[str] = []

    for key, target_tensor in target_state.items():
        if key == "class_embedding.weight":
            continue
        source_tensor = source_state.get(key)
        if source_tensor is None:
            skipped.append(key)
            continue
        if tuple(source_tensor.shape) != tuple(target_tensor.shape):
            skipped.append(key)
            continue
        target_state[key] = source_tensor.detach().cpu()
        copied.append(key)

    result = target_model.load_state_dict(target_state, strict=False)
    missing_keys = list(getattr(result, "missing_keys", []))
    unexpected_keys = list(getattr(result, "unexpected_keys", []))
    blocking_missing = [key for key in missing_keys if key != "class_embedding.weight"]
    if blocking_missing or unexpected_keys:
        raise RuntimeError(
            "Frozen CodecSep state transfer left unresolved weights: "
            f"missing={blocking_missing} unexpected={unexpected_keys}"
        )
    return {
        "copied_keys": copied,
        "skipped_keys": skipped,
    }


def build_embedding_matrix(
    teacher_model: CodecSep,
    categories: Sequence[FrozenCategorySpec],
    *,
    num_classes: int,
    condition_size: int,
    null_class_id: int,
) -> torch.Tensor:
    matrix = torch.zeros((num_classes, condition_size), dtype=torch.float32)
    with torch.no_grad():
        for category in categories:
            encoded = teacher_model.text_encoder.get_text_embedding(list(category.prompts), use_tensor=True)
            if encoded.ndim == 1:
                encoded = encoded.unsqueeze(0)
            averaged = average_normalized_embeddings(encoded.cpu())
            if int(averaged.shape[-1]) != condition_size:
                raise RuntimeError(
                    f"Prompt embedding size mismatch for '{category.label}': "
                    f"expected {condition_size}, got {tuple(averaged.shape)}"
                )
            matrix[category.class_id] = averaged
        matrix[null_class_id] = 0.0
    return matrix


class OnnxCategoryExportWrapper(nn.Module):
    def __init__(self, model: CodecSep) -> None:
        super().__init__()
        self.model = model

    def forward(self, mixture: torch.Tensor, category_idx: torch.Tensor) -> torch.Tensor:
        return self.model.separate_class_ids(mixture, category_idx.reshape(-1).long())


class ExecuTorchCategoryExportWrapper(nn.Module):
    def __init__(self, model: CodecSep, *, null_class_id: int) -> None:
        super().__init__()
        self.model = model
        self.null_class_id = int(null_class_id)

    def forward(self, mixture: torch.Tensor, label_vector: torch.Tensor) -> torch.Tensor:
        label_vector = label_vector.float()
        class_ids = torch.argmax(label_vector, dim=-1)
        null_mask = torch.sum(torch.abs(label_vector), dim=-1) <= 0
        null_ids = torch.full_like(class_ids, self.null_class_id)
        class_ids = torch.where(null_mask, null_ids, class_ids)
        return self.model.separate_class_ids(mixture, class_ids.long())


def resolve_category_id(categories: Sequence[FrozenCategorySpec], label: str) -> int:
    normalized = str(label).strip().casefold()
    for category in categories:
        if category.label.casefold() == normalized or category.id.casefold() == normalized:
            return category.class_id
    raise KeyError(f"Unknown frozen category label '{label}'.")


def _seeded_example_audio() -> torch.Tensor:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(7)
    return torch.randn((1, 1, SEGMENT_SAMPLES), generator=generator, dtype=torch.float32)


def _summarize_diffs(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    diff = np.asarray(reference, dtype=np.float32) - np.asarray(candidate, dtype=np.float32)
    return {
        "shape": list(reference.shape),
        "mean_abs_error": float(np.mean(np.abs(diff))),
        "max_abs_error": float(np.max(np.abs(diff))),
        "allclose": bool(np.allclose(reference, candidate, atol=1.0e-4, rtol=1.0e-4)),
    }


@contextmanager
def _disable_mha_fastpath_for_onnx_export() -> Iterable[None]:
    backends = getattr(torch, "backends", None)
    mha_backend = getattr(backends, "mha", None)
    get_enabled = getattr(mha_backend, "get_fastpath_enabled", None)
    set_enabled = getattr(mha_backend, "set_fastpath_enabled", None)
    if not callable(get_enabled) or not callable(set_enabled):
        yield
        return

    previous = bool(get_enabled())
    # Force MultiheadAttention to trace through decomposed attention ops that ONNX
    # can lower, rather than the fused aten::_native_multi_head_attention fastpath.
    set_enabled(False)
    try:
        yield
    finally:
        set_enabled(previous)


def compute_onnx_parity(
    wrapper: OnnxCategoryExportWrapper,
    onnx_path: Path,
    categories: Sequence[FrozenCategorySpec],
    labels: Sequence[str] = ONNX_PARITY_LABELS,
) -> dict[str, Any]:
    import onnxruntime as ort

    example_audio = _seeded_example_audio()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    parity: dict[str, Any] = {}

    for label in labels:
        category_idx = resolve_category_id(categories, label)
        with torch.no_grad():
            reference = wrapper(example_audio, torch.tensor([category_idx], dtype=torch.long)).cpu().numpy()
        candidate = session.run(
            None,
            {
                "mixture": example_audio.numpy(),
                "category_idx": np.asarray([category_idx], dtype=np.int64),
            },
        )[0]
        parity[label] = _summarize_diffs(reference, candidate)
    return parity


def export_onnx_model(
    wrapper: OnnxCategoryExportWrapper,
    output_path: Path,
    *,
    opset_version: int = ONNX_OPSET,
) -> None:
    import onnx

    example_audio = torch.zeros((1, 1, SEGMENT_SAMPLES), dtype=torch.float32)
    example_category = torch.zeros((1,), dtype=torch.long)
    with _disable_mha_fastpath_for_onnx_export():
        torch.onnx.export(
            wrapper,
            (example_audio, example_category),
            output_path,
            opset_version=opset_version,
            input_names=["mixture", "category_idx"],
            output_names=["target_audio"],
            dynamic_axes=None,
            do_constant_folding=True,
        )
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)


def _coerce_executorch_output(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    if hasattr(value, "numpy"):
        return np.asarray(value.numpy(), dtype=np.float32)
    return np.asarray(value, dtype=np.float32)


def _should_prefer_xnnpack_by_default() -> bool:
    if platform.system() != "Windows":
        return False
    return (
        importlib.util.find_spec(
            "executorch.backends.xnnpack.partition.xnnpack_partitioner",
        )
        is not None
    )


def export_executorch_model(
    wrapper: ExecuTorchCategoryExportWrapper,
    output_path: Path,
    *,
    prefer_xnnpack: bool,
) -> tuple[str, str | None]:
    from torch.export import export

    try:
        from executorch.exir import to_edge, to_edge_transform_and_lower
    except ImportError as exc:
        raise RuntimeError("executorch is not installed in the active environment.") from exc

    example_inputs = (
        torch.zeros((1, 1, SEGMENT_SAMPLES), dtype=torch.float32),
        torch.zeros((1, NULL_CLASS_ID), dtype=torch.float32),
    )
    exported_program = export(wrapper, example_inputs)

    warning: str | None = None
    backend = "portable"
    if prefer_xnnpack:
        try:
            from executorch.backends.xnnpack.partition.xnnpack_partitioner import (
                XnnpackFloatingPointPartitioner,
            )

            executorch_program = to_edge_transform_and_lower(
                exported_program,
                partitioner=[XnnpackFloatingPointPartitioner()],
            ).to_executorch()
            backend = "xnnpack"
        except Exception as exc:  # pragma: no cover - exercised only when executorch is installed
            warning = (
                "XNNPACK lowering failed; falling back to portable ExecuTorch. "
                f"Details: {type(exc).__name__}: {exc}"
            )
            executorch_program = to_edge(exported_program).to_executorch()
    else:
        executorch_program = to_edge(exported_program).to_executorch()

    output_path.write_bytes(executorch_program.buffer)
    return backend, warning


def compute_executorch_parity(
    wrapper: ExecuTorchCategoryExportWrapper,
    executorch_path: Path,
    categories: Sequence[FrozenCategorySpec],
    labels: Sequence[str] = EXECUTORCH_PARITY_LABELS,
) -> dict[str, Any]:
    from executorch.extension.pybindings import portable_lib

    example_audio = _seeded_example_audio()
    module = portable_lib._load_for_executorch(
        str(executorch_path),
        None,
        False,
        0,
        portable_lib.Verification.Minimal,
    )
    parity: dict[str, Any] = {}

    for label in labels:
        category_idx = resolve_category_id(categories, label)
        label_vector = torch.zeros((1, NULL_CLASS_ID), dtype=torch.float32)
        label_vector[0, category_idx] = 1.0
        with torch.no_grad():
            reference = wrapper(example_audio, label_vector).cpu().numpy()
        outputs = module.run_method("forward", (example_audio, label_vector))
        candidate = _coerce_executorch_output(outputs[0])
        parity[label] = _summarize_diffs(reference, candidate)
    return parity


def build_export_sidecar(
    *,
    format_name: str,
    backend: str,
    source_checkpoint: Path,
    output_path: Path,
    categories: Sequence[FrozenCategorySpec],
    verification: Mapping[str, Any] | None = None,
    requested_backend: str | None = None,
    warning: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "format": format_name,
        "backend": backend,
        "requested_backend": requested_backend or backend,
        "source_checkpoint": str(source_checkpoint.resolve()),
        "output": str(output_path.resolve()),
        "sample_rate": SAMPLE_RATE,
        "segment_seconds": SEGMENT_SECONDS,
        "segment_samples": SEGMENT_SAMPLES,
        "overlap_seconds": OVERLAP_SECONDS,
        "labels": [category.label for category in categories],
        "inputs": [
            {
                "name": "mixture",
                "shape": [1, 1, SEGMENT_SAMPLES],
                "dtype": "torch.float32",
            },
        ],
        "outputs": [
            {
                "name": "target_audio",
                "shape": [1, 1, SEGMENT_SAMPLES],
                "dtype": "torch.float32",
            }
        ],
    }
    if format_name == "onnx":
        payload["inputs"].append(
            {
                "name": "category_idx",
                "shape": [1],
                "dtype": "torch.int64",
            }
        )
    else:
        payload["inputs"].append(
            {
                "name": "label_vector",
                "shape": [1, NULL_CLASS_ID],
                "dtype": "torch.float32",
            }
        )
    if verification is not None:
        payload["verification"] = dict(verification)
    if warning:
        payload["warning"] = warning
    return payload


def write_repro_assets(
    artifacts: FreezeArtifacts,
    categories: Sequence[FrozenCategorySpec],
) -> None:
    yaml_payload = {
        "version": 1,
        "sample_rate": SAMPLE_RATE,
        "segment_seconds": SEGMENT_SECONDS,
        "overlap_seconds": OVERLAP_SECONDS,
        "categories": [category.label for category in categories],
    }
    artifacts.categories_yaml.write_text(
        yaml.safe_dump(yaml_payload, sort_keys=False),
        encoding="utf-8",
    )
    artifacts.categories_txt.write_text(
        "\n".join(category.label for category in categories) + "\n",
        encoding="utf-8",
    )


def build_freeze_manifest(
    *,
    source_checkpoint: Path,
    source_config: Path | None,
    teacher_model_kwargs: Mapping[str, Any],
    frozen_model_kwargs: Mapping[str, Any],
    copied_weights: Mapping[str, Any],
    categories: Sequence[FrozenCategorySpec],
    executorch_status: str,
    executorch_warning: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "model_id": "codecsep_dnrv2_15cat",
        "status": "generated",
        "source_checkpoint": str(source_checkpoint.resolve()),
        "source_config": str(source_config.resolve()) if source_config is not None else None,
        "frozen_checkpoint": "codecsep_dnrv2_15cat_frozen.pt",
        "sample_rate": SAMPLE_RATE,
        "segment_seconds": SEGMENT_SECONDS,
        "overlap_seconds": OVERLAP_SECONDS,
        "null_class_id": NULL_CLASS_ID,
        "teacher_conditioning": dict(teacher_model_kwargs.get("conditioning") or {}),
        "frozen_conditioning": dict(frozen_model_kwargs.get("conditioning") or {}),
        "copied_weight_count": len(list(copied_weights.get("copied_keys") or [])),
        "skipped_weight_count": len(list(copied_weights.get("skipped_keys") or [])),
        "executorch_status": executorch_status,
        "executorch_warning": executorch_warning,
        "categories": [
            {
                "class_id": category.class_id,
                "id": category.id,
                "label": category.label,
                "prompts": list(category.prompts),
            }
            for category in categories
        ],
        "expected_artifacts": [
            "../shared/categories_15.yaml",
            "../shared/categories_15.txt",
            "codecsep_dnrv2_15cat_frozen.pt",
            "embedding_init.pt",
            "../desktop/codecsep_dnrv2_15cat.onnx",
            "../desktop/codecsep_dnrv2_15cat.onnx.json",
            "../android/codecsep_dnrv2_15cat.pte",
            "../android/codecsep_dnrv2_15cat.pte.json",
        ],
    }


def run_export(args: argparse.Namespace) -> None:
    package_dir = Path(args.package_dir).resolve()
    package_dir.mkdir(parents=True, exist_ok=True)
    artifacts = override_export_paths(
        resolve_artifact_paths(package_dir),
        onnx_path=Path(args.onnx_output),
        executorch_path=Path(args.executorch_output),
    )
    for path in (
        artifacts.categories_yaml,
        artifacts.categories_txt,
        artifacts.freeze_spec_yaml,
        artifacts.embedding_init_path,
        artifacts.freeze_manifest_path,
        artifacts.frozen_checkpoint_path,
        artifacts.onnx_path,
        artifacts.onnx_sidecar_path,
        artifacts.executorch_path,
        artifacts.executorch_sidecar_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    categories = load_freeze_categories(artifacts.freeze_spec_yaml)
    write_repro_assets(artifacts, categories)

    source_run_dir = Path(args.source_run_dir).resolve()
    source_checkpoint, source_config, source_sample_rate, source_model_kwargs, state_dict = load_source_bundle(
        source_run_dir,
    )
    if int(source_sample_rate) != SAMPLE_RATE:
        raise RuntimeError(
            f"Expected source sample rate {SAMPLE_RATE}, got {source_sample_rate}."
        )

    teacher_model_kwargs = build_runtime_model_kwargs(
        source_model_kwargs,
        state_dict,
        mode="prompt",
    )
    frozen_model_kwargs = build_runtime_model_kwargs(
        source_model_kwargs,
        state_dict,
        mode="class_id",
        num_classes=NULL_CLASS_ID + 1,
    )

    logger.info("Instantiating prompt-conditioned CodecSep teacher...")
    teacher_model = instantiate_model(SAMPLE_RATE, teacher_model_kwargs)
    CodecSepSeparator._load_model_state_dict(teacher_model, state_dict)
    baked_teacher_weight_norm = bake_weight_norm_parametrizations(teacher_model)
    if baked_teacher_weight_norm:
        logger.info(
            "Baked %d teacher weight-norm parametrizations into static weights.",
            baked_teacher_weight_norm,
        )
    teacher_model = teacher_model.eval().cpu()

    logger.info("Instantiating class-id frozen CodecSep model...")
    frozen_model = instantiate_model(SAMPLE_RATE, frozen_model_kwargs)
    copied_weights = copy_compatible_weights(teacher_model, frozen_model)

    embedding_matrix = build_embedding_matrix(
        teacher_model,
        categories,
        num_classes=NULL_CLASS_ID + 1,
        condition_size=int(frozen_model.condition_size),
        null_class_id=NULL_CLASS_ID,
    )
    torch.save(
        {
            "version": "fixed_category_embedding_init_v1",
            "embedding": embedding_matrix,
            "labels": [category.label for category in categories],
            "null_class_id": NULL_CLASS_ID,
        },
        artifacts.embedding_init_path,
    )
    with torch.no_grad():
        assert frozen_model.class_embedding is not None
        frozen_model.class_embedding.weight.copy_(embedding_matrix)
    baked_frozen_weight_norm = bake_weight_norm_parametrizations(frozen_model)
    if baked_frozen_weight_norm:
        logger.info(
            "Baked %d frozen-model weight-norm parametrizations into static weights.",
            baked_frozen_weight_norm,
        )
    frozen_model = frozen_model.eval().cpu()

    torch.save(
        {
            "state_dict": frozen_model.state_dict(),
            "metadata": {
                "kwargs": frozen_model_kwargs,
                "freeze_spec": str(artifacts.freeze_spec_yaml.resolve()),
                "created_at": utc_now_iso(),
            },
        },
        artifacts.frozen_checkpoint_path,
    )

    onnx_wrapper = OnnxCategoryExportWrapper(frozen_model).eval()
    export_onnx_model(onnx_wrapper, artifacts.onnx_path, opset_version=args.onnx_opset)
    onnx_verification = compute_onnx_parity(onnx_wrapper, artifacts.onnx_path, categories)
    artifacts.onnx_sidecar_path.write_text(
        json.dumps(
            build_export_sidecar(
                format_name="onnx",
                backend="onnxruntime",
                source_checkpoint=source_checkpoint,
                output_path=artifacts.onnx_path,
                categories=categories,
                verification=onnx_verification,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    executorch_wrapper = ExecuTorchCategoryExportWrapper(
        frozen_model,
        null_class_id=NULL_CLASS_ID,
    ).eval()
    executorch_status = "skipped"
    executorch_warning: str | None = None
    prefer_xnnpack = bool(args.prefer_xnnpack)
    if not prefer_xnnpack and _should_prefer_xnnpack_by_default():
        prefer_xnnpack = True
        logger.info("Auto-enabled XNNPACK lowering for Windows desktop ExecuTorch export.")
    try:
        executorch_backend, executorch_warning = export_executorch_model(
            executorch_wrapper,
            artifacts.executorch_path,
            prefer_xnnpack=prefer_xnnpack,
        )
        executorch_verification = compute_executorch_parity(
            executorch_wrapper,
            artifacts.executorch_path,
            categories,
        )
        artifacts.executorch_sidecar_path.write_text(
            json.dumps(
                build_export_sidecar(
                    format_name="executorch",
                    backend=executorch_backend,
                    source_checkpoint=source_checkpoint,
                    output_path=artifacts.executorch_path,
                    categories=categories,
                    verification=executorch_verification,
                    requested_backend="xnnpack" if prefer_xnnpack else "portable",
                    warning=executorch_warning,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        executorch_status = "generated"
    except Exception as exc:
        executorch_status = "skipped_missing_or_failed"
        executorch_warning = f"{type(exc).__name__}: {exc}"
        artifacts.executorch_sidecar_path.write_text(
            json.dumps(
                build_export_sidecar(
                    format_name="executorch",
                    backend="portable",
                    source_checkpoint=source_checkpoint,
                    output_path=artifacts.executorch_path,
                    categories=categories,
                    verification=None,
                    requested_backend="xnnpack" if prefer_xnnpack else "portable",
                    warning=executorch_warning,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.warning("ExecuTorch export skipped: %s", executorch_warning)

    freeze_manifest = build_freeze_manifest(
        source_checkpoint=source_checkpoint,
        source_config=source_config,
        teacher_model_kwargs=teacher_model_kwargs,
        frozen_model_kwargs=frozen_model_kwargs,
        copied_weights=copied_weights,
        categories=categories,
        executorch_status=executorch_status,
        executorch_warning=executorch_warning,
    )
    artifacts.freeze_manifest_path.write_text(
        json.dumps(freeze_manifest, indent=2),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze prompt-conditioned CodecSep into CodecSepDNRv2_15Cat exports.",
    )
    parser.add_argument(
        "--source-run-dir",
        type=Path,
        default=get_codecsep_default_run_dir(),
        help="CodecSep run directory containing the authoritative prompt-conditioned checkpoint bundle.",
    )
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=get_codecsep_dnrv2_15cat_model_path(),
        help=(
            "CodecSepDNRv2_15Cat manifest/package directory. Generated exports are "
            "written under ai/models/Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15."
        ),
    )
    parser.add_argument(
        "--onnx-output",
        type=Path,
        default=get_codecsep_dnrv2_15cat_onnx_path(),
        help="Override the ONNX output path. The sidecar is written alongside it.",
    )
    parser.add_argument(
        "--executorch-output",
        type=Path,
        default=get_codecsep_dnrv2_15cat_executorch_path(),
        help="Override the ExecuTorch output path. The sidecar is written alongside it.",
    )
    parser.add_argument(
        "--onnx-opset",
        type=int,
        default=ONNX_OPSET,
        help="ONNX opset version for export.",
    )
    parser.add_argument(
        "--prefer-xnnpack",
        action="store_true",
        help=(
            "Attempt XNNPACK lowering for ExecuTorch before falling back to portable export. "
            "Windows desktop exports auto-enable this when XNNPACK is available."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    args.package_dir = Path(args.package_dir).resolve()
    args.package_dir.mkdir(parents=True, exist_ok=True)
    Path(args.onnx_output).resolve().parent.mkdir(parents=True, exist_ok=True)
    Path(args.executorch_output).resolve().parent.mkdir(parents=True, exist_ok=True)

    run_export(args)


if __name__ == "__main__":
    main()
