"""
Export CodecSepDNRv2_15Cat to ExecuTorch from the already-frozen checkpoint.

This path avoids the prompt-teacher / CLAP stack entirely and only needs the
class-id frozen checkpoint written by the full freeze step.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import logging
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
import yaml
from torch import nn

from ai.ai_runtime.separation.codecsep.model import CodecSep
from ai.ai_runtime.utils.paths import (
    get_codecsep_dnrv2_15cat_executorch_path,
    get_codecsep_dnrv2_15cat_model_path,
)

logger = logging.getLogger(__name__)

EXECUTORCH_PARITY_LABELS = ("speech", "dog barking")


@dataclass(frozen=True)
class FrozenCategorySpec:
    class_id: int
    id: str
    label: str
    prompts: tuple[str, ...]


@dataclass(frozen=True)
class PackageSpec:
    sample_rate: int
    segment_seconds: float
    segment_samples: int
    overlap_seconds: float
    null_class_id: int
    categories: tuple[FrozenCategorySpec, ...]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_yaml(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def load_package_spec(freeze_spec_path: Path) -> PackageSpec:
    payload = _load_yaml(freeze_spec_path)
    sample_rate = int(payload.get("sample_rate", 16_000))
    segment_seconds = float(payload.get("segment_seconds", 2.0))
    categories_payload = list(payload.get("categories") or [])
    categories: list[FrozenCategorySpec] = []
    for class_id, entry in enumerate(categories_payload):
        prompts = tuple(
            str(item).strip()
            for item in list(entry.get("prompts") or [])
            if str(item).strip()
        )
        categories.append(
            FrozenCategorySpec(
                class_id=class_id,
                id=str(entry["id"]),
                label=str(entry.get("label", entry["id"])),
                prompts=prompts,
            )
        )
    return PackageSpec(
        sample_rate=sample_rate,
        segment_seconds=segment_seconds,
        segment_samples=int(sample_rate * segment_seconds),
        overlap_seconds=float(payload.get("overlap_seconds", 0.5)),
        null_class_id=int(payload.get("null_class_id", 15)),
        categories=tuple(categories),
    )


def _instantiate_model(
    model_class,
    *,
    sample_rate: int,
    model_kwargs: Mapping[str, object],
):
    candidate_kwargs = {
        "sample_rate": sample_rate,
        "latent_dim": model_kwargs.get("latent_dim"),
        "tracks": model_kwargs.get("tracks"),
        "mode": model_kwargs.get("mode"),
        "residual_mode": model_kwargs.get("residual_mode"),
        "enc_params": model_kwargs.get("enc_params"),
        "dec_params": model_kwargs.get("dec_params"),
        "transformer_params": model_kwargs.get("transformer_params"),
        "separator_params": model_kwargs.get("separator_params"),
        "film_clip": model_kwargs.get("film_clip"),
        "normalize_prompt_embeddings": model_kwargs.get("normalize_prompt_embeddings"),
        "prompt_embed_eps": model_kwargs.get("prompt_embed_eps"),
        "enable_semantic_finite_checks": model_kwargs.get("enable_semantic_finite_checks"),
        "conditioning": model_kwargs.get("conditioning"),
        "num_classes": model_kwargs.get("num_classes"),
        "clap": model_kwargs.get("clap"),
        "pretrain": model_kwargs.get("pretrain"),
    }

    signature = inspect.signature(model_class)
    supports_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if supports_var_kwargs:
        filtered_kwargs = {
            key: value for key, value in candidate_kwargs.items() if value is not None
        }
    else:
        supported_names = set(signature.parameters.keys())
        filtered_kwargs = {
            key: value
            for key, value in candidate_kwargs.items()
            if key in supported_names and value is not None
        }
    return model_class(**filtered_kwargs)


def _bake_weight_norm_parametrizations(model: nn.Module) -> int:
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


def load_frozen_model(
    frozen_checkpoint_path: Path,
    *,
    sample_rate: int,
) -> tuple[CodecSep, dict[str, Any]]:
    payload = torch.load(frozen_checkpoint_path, map_location="cpu", weights_only=False)
    metadata = dict(payload.get("metadata") or {})
    model_kwargs = dict(metadata.get("kwargs") or {})
    if not model_kwargs:
        raise RuntimeError(
            f"Frozen checkpoint metadata is missing model kwargs: {frozen_checkpoint_path}"
        )

    model = _instantiate_model(
        CodecSep,
        sample_rate=sample_rate,
        model_kwargs=model_kwargs,
    )
    result = model.load_state_dict(payload["state_dict"], strict=False)
    missing_keys = list(getattr(result, "missing_keys", []))
    unexpected_keys = list(getattr(result, "unexpected_keys", []))
    if missing_keys or unexpected_keys:
        raise RuntimeError(
            "Frozen checkpoint load left unresolved weights: "
            f"missing={missing_keys} unexpected={unexpected_keys}"
        )
    baked_weight_norm_count = _bake_weight_norm_parametrizations(model)
    if baked_weight_norm_count:
        logger.info(
            "Baked %d weight-norm parametrizations into static weights for export.",
            baked_weight_norm_count,
        )
    return model.eval().cpu(), metadata


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


def _seeded_example_audio(segment_samples: int) -> torch.Tensor:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(7)
    return torch.randn((1, 1, segment_samples), generator=generator, dtype=torch.float32)


def _summarize_diffs(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    diff = np.asarray(reference, dtype=np.float32) - np.asarray(candidate, dtype=np.float32)
    return {
        "shape": list(reference.shape),
        "mean_abs_error": float(np.mean(np.abs(diff))),
        "max_abs_error": float(np.max(np.abs(diff))),
        "allclose": bool(np.allclose(reference, candidate, atol=1.0e-4, rtol=1.0e-4)),
    }


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
    segment_samples: int,
    null_class_id: int,
) -> tuple[str, str | None]:
    from torch.export import export
    from executorch.exir import to_edge, to_edge_transform_and_lower

    example_inputs = (
        torch.zeros((1, 1, segment_samples), dtype=torch.float32),
        torch.zeros((1, null_class_id), dtype=torch.float32),
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
        except Exception as exc:
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
    *,
    segment_samples: int,
    null_class_id: int,
    labels: Sequence[str] = EXECUTORCH_PARITY_LABELS,
) -> dict[str, Any]:
    from executorch.extension.pybindings import portable_lib

    example_audio = _seeded_example_audio(segment_samples)
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
        label_vector = torch.zeros((1, null_class_id), dtype=torch.float32)
        label_vector[0, category_idx] = 1.0
        with torch.no_grad():
            reference = wrapper(example_audio, label_vector).cpu().numpy()
        outputs = module.run_method("forward", (example_audio, label_vector))
        candidate = _coerce_executorch_output(outputs[0])
        parity[label] = _summarize_diffs(reference, candidate)
    return parity


def build_export_sidecar(
    *,
    source_checkpoint: Path,
    output_path: Path,
    package_spec: PackageSpec,
    verification: Mapping[str, Any] | None = None,
    backend: str,
    requested_backend: str,
    warning: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "format": "executorch",
        "backend": backend,
        "requested_backend": requested_backend,
        "source_checkpoint": str(source_checkpoint.resolve()),
        "output": str(output_path.resolve()),
        "sample_rate": package_spec.sample_rate,
        "segment_seconds": package_spec.segment_seconds,
        "segment_samples": package_spec.segment_samples,
        "overlap_seconds": package_spec.overlap_seconds,
        "labels": [category.label for category in package_spec.categories],
        "inputs": [
            {
                "name": "mixture",
                "shape": [1, 1, package_spec.segment_samples],
                "dtype": "torch.float32",
            },
            {
                "name": "label_vector",
                "shape": [1, package_spec.null_class_id],
                "dtype": "torch.float32",
            },
        ],
        "outputs": [
            {
                "name": "target_audio",
                "shape": [1, 1, package_spec.segment_samples],
                "dtype": "torch.float32",
            }
        ],
    }
    if verification is not None:
        payload["verification"] = dict(verification)
    if warning:
        payload["warning"] = warning
    return payload


def update_freeze_manifest(
    manifest_path: Path,
    *,
    status: str,
    warning: str | None,
) -> None:
    if not manifest_path.exists():
        return
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["executorch_status"] = status
    payload["executorch_warning"] = warning
    payload["updated_at"] = utc_now_iso()
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    default_package_dir = get_codecsep_dnrv2_15cat_model_path()
    default_pte_path = get_codecsep_dnrv2_15cat_executorch_path()

    parser = argparse.ArgumentParser(
        description="Export CodecSepDNRv2_15Cat ExecuTorch from the frozen checkpoint only.",
    )
    parser.add_argument(
        "--package-dir",
        default=str(default_package_dir),
        help="Package directory containing the frozen checkpoint and freeze spec.",
    )
    parser.add_argument(
        "--frozen-checkpoint",
        default=None,
        help="Path to codecsep_dnrv2_15cat_frozen.pt. Defaults to <package-dir>/codecsep_dnrv2_15cat_frozen.pt.",
    )
    parser.add_argument(
        "--freeze-spec",
        default=None,
        help="Path to freeze_spec_15.yaml. Defaults to <package-dir>/freeze_spec_15.yaml.",
    )
    parser.add_argument(
        "--executorch-output",
        default=str(default_pte_path),
        help="Destination .pte path.",
    )
    parser.add_argument(
        "--prefer-xnnpack",
        action="store_true",
        help=(
            "Attempt XNNPACK lowering first, then fall back to portable export. "
            "Windows desktop exports auto-enable this when XNNPACK is available."
        ),
    )
    parser.add_argument(
        "--skip-parity",
        action="store_true",
        help="Skip Python runtime parity verification after writing the .pte file.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_arg_parser().parse_args()

    package_dir = Path(args.package_dir).resolve()
    frozen_checkpoint_path = Path(args.frozen_checkpoint).resolve() if args.frozen_checkpoint else package_dir / "codecsep_dnrv2_15cat_frozen.pt"
    freeze_spec_path = Path(args.freeze_spec).resolve() if args.freeze_spec else package_dir / "freeze_spec_15.yaml"
    executorch_path = Path(args.executorch_output).resolve()
    sidecar_path = executorch_path.with_suffix(".pte.json")
    manifest_path = package_dir / "freeze_manifest.json"

    package_spec = load_package_spec(freeze_spec_path)
    model, metadata = load_frozen_model(
        frozen_checkpoint_path,
        sample_rate=package_spec.sample_rate,
    )

    logger.info("Loaded frozen CodecSep checkpoint: %s", frozen_checkpoint_path)
    wrapper = ExecuTorchCategoryExportWrapper(
        model,
        null_class_id=package_spec.null_class_id,
    ).eval()
    executorch_path.parent.mkdir(parents=True, exist_ok=True)

    prefer_xnnpack = bool(args.prefer_xnnpack)
    if not prefer_xnnpack and _should_prefer_xnnpack_by_default():
        prefer_xnnpack = True
        logger.info("Auto-enabled XNNPACK lowering for Windows desktop ExecuTorch export.")

    backend = "portable"
    warning: str | None = None
    status = "generated"
    try:
        backend, warning = export_executorch_model(
            wrapper,
            executorch_path,
            prefer_xnnpack=prefer_xnnpack,
            segment_samples=package_spec.segment_samples,
            null_class_id=package_spec.null_class_id,
        )
        verification = None
        if not args.skip_parity:
            verification = compute_executorch_parity(
                wrapper,
                executorch_path,
                package_spec.categories,
                segment_samples=package_spec.segment_samples,
                null_class_id=package_spec.null_class_id,
            )
        sidecar_payload = build_export_sidecar(
            source_checkpoint=frozen_checkpoint_path,
            output_path=executorch_path,
            package_spec=package_spec,
            verification=verification,
            backend=backend,
            requested_backend="xnnpack" if prefer_xnnpack else "portable",
            warning=warning,
        )
        sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")
    except Exception as exc:
        status = "skipped_missing_or_failed"
        warning = f"{type(exc).__name__}: {exc}"
        sidecar_payload = build_export_sidecar(
            source_checkpoint=frozen_checkpoint_path,
            output_path=executorch_path,
            package_spec=package_spec,
            verification=None,
            backend=backend,
            requested_backend="xnnpack" if prefer_xnnpack else "portable",
            warning=warning,
        )
        sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")
        update_freeze_manifest(
            manifest_path,
            status=status,
            warning=warning,
        )
        raise

    update_freeze_manifest(
        manifest_path,
        status=status,
        warning=warning,
    )
    logger.info("Wrote ExecuTorch package: %s", executorch_path)


if __name__ == "__main__":
    main()
