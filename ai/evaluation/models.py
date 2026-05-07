"""Model registry for evaluation adapters."""

from __future__ import annotations

from pathlib import Path

from ai.ai_runtime.utils.paths import (
    get_audiosep_hive_raw_checkpoint_path,
    get_audiosep_hive_raw_clap_checkpoint_path,
    get_audiosep_hive_raw_config_path,
    get_audiosep_hive15cat_onnx_path,
    get_audiosep_open_vocab_checkpoint_path,
    get_audiosep_open_vocab_clap_checkpoint_path,
    get_audiosep_open_vocab_model_path,
    get_clapsep_research_checkpoint_path,
    get_clapsep_research_clap_checkpoint_path,
    get_clapsep_research_requirements_path,
    get_codecsep_dnrv2_15cat_executorch_path,
    get_codecsep_dnrv2_15cat_onnx_path,
    get_model_exports_path,
    get_waveformer_checkpoint_path,
    get_waveformer_config_path,
    get_waveformer_desktop_onnx_path,
    get_waveformer_model_package_path,
)
from ai.evaluation.contracts import ModelEvalSpec


MODEL_ALIASES = {
    "audiosep_hive15cat": "audiosep_hive15cat_onnx",
    "codecsep_dnrv2_15cat": "codecsep_dnrv2_15cat_onnx",
    "pure_audiosep": "audiosep_open_vocab",
}
MODEL_GROUPS = {"all", "auto", "exact15", "research", "deployable"}


def _waveformer_pte_path() -> Path:
    return (
        get_model_exports_path()
        / "Waveformer"
        / "waveformer_edge_100ms"
        / "executorch"
        / "semantic_hearing_100ms_portable.pte"
    )


def _audiosep_open_vocab_config_path() -> Path:
    return get_audiosep_open_vocab_model_path() / "config" / "audiosep_base.yaml"


def list_model_specs() -> tuple[ModelEvalSpec, ...]:
    """Return deterministic semantic evaluation model specs."""

    return (
        ModelEvalSpec(
            model_id="waveformer_onnx_export",
            display_name="Waveformer 100 ms ONNX export",
            adapter_kind="waveformer_onnx",
            target_surface="waveformer20",
            runtime="onnx",
            artifact_paths=(get_waveformer_desktop_onnx_path(), get_waveformer_model_package_path()),
            notes="Default product-equivalent packaged Waveformer ONNX path.",
        ),
        ModelEvalSpec(
            model_id="waveformer",
            display_name="Waveformer PyTorch runtime",
            adapter_kind="semantic_batch",
            target_surface="legacy",
            runtime="pytorch",
            artifact_paths=(get_waveformer_config_path(), get_waveformer_checkpoint_path()),
            adapter_options={"separator_backend": "waveformer"},
            notes="Legacy Python Waveformer runtime; availability depends on heavy dependencies.",
        ),
        ModelEvalSpec(
            model_id="audiosep_open_vocab",
            display_name="Vanilla AudioSep open-vocabulary",
            adapter_kind="audiosep_source",
            target_surface="audiosep_prompt",
            runtime="pytorch",
            artifact_paths=(
                get_audiosep_open_vocab_checkpoint_path(),
                get_audiosep_open_vocab_clap_checkpoint_path(),
                _audiosep_open_vocab_config_path(),
            ),
            adapter_options={
                "source_dir": str(get_audiosep_open_vocab_model_path()),
                "config_path": str(_audiosep_open_vocab_config_path()),
                "checkpoint_path": str(get_audiosep_open_vocab_checkpoint_path()),
            },
            notes="Vanilla AudioSep text-query baseline.",
        ),
        ModelEvalSpec(
            model_id="audiosep_hive_raw",
            display_name="AudioSep-Hive raw checkpoint",
            adapter_kind="audiosep_source",
            target_surface="audiosep_prompt",
            runtime="pytorch",
            artifact_paths=(
                get_audiosep_hive_raw_checkpoint_path(),
                get_audiosep_hive_raw_config_path(),
                get_audiosep_hive_raw_clap_checkpoint_path(),
            ),
            adapter_options={
                "source_dir": str(get_audiosep_open_vocab_model_path()),
                "config_path": str(get_audiosep_hive_raw_config_path()),
                "checkpoint_path": str(get_audiosep_hive_raw_checkpoint_path()),
            },
            notes="Raw AudioSep-Hive checkpoint loaded through the vanilla AudioSep source adapter.",
        ),
        ModelEvalSpec(
            model_id="audiosep_hive15cat_onnx",
            display_name="AudioSep-Hive exact-15 ONNX",
            adapter_kind="semantic_batch",
            target_surface="exact15",
            runtime="onnx",
            artifact_paths=(get_audiosep_hive15cat_onnx_path(),),
            adapter_options={"separator_backend": "audiosep_hive15cat"},
            notes="Fixed 15-category AudioSep-Hive ONNX comparison path.",
        ),
        ModelEvalSpec(
            model_id="codecsep_dnrv2_15cat_onnx",
            display_name="CodecSep DNRv2 exact-15 ONNX",
            adapter_kind="semantic_batch",
            target_surface="exact15",
            runtime="onnx",
            artifact_paths=(get_codecsep_dnrv2_15cat_onnx_path(),),
            adapter_options={
                "separator_backend": "codecsep_dnrv2_15cat",
                "codecsep_dnrv2_15cat_runtime": "onnx",
            },
            notes="Frozen exact-15 CodecSep ONNX runtime.",
        ),
        ModelEvalSpec(
            model_id="codecsep_dnrv2_15cat_executorch",
            display_name="CodecSep DNRv2 exact-15 ExecuTorch",
            adapter_kind="semantic_batch",
            target_surface="exact15",
            runtime="executorch",
            artifact_paths=(get_codecsep_dnrv2_15cat_executorch_path(),),
            adapter_options={
                "separator_backend": "codecsep_dnrv2_15cat",
                "codecsep_dnrv2_15cat_runtime": "executorch",
            },
            notes="Frozen exact-15 CodecSep ExecuTorch runtime.",
        ),
        ModelEvalSpec(
            model_id="codecsep_normal_compat",
            display_name="CodecSep prompt-compatible checkpoint",
            adapter_kind="semantic_batch",
            target_surface="legacy",
            runtime="pytorch",
            artifact_paths=(),
            adapter_options={"separator_backend": "codecsep", "codecsep_mode": "compat"},
            notes="Research prompt-compatible CodecSep path; checkpoint availability is local.",
        ),
        ModelEvalSpec(
            model_id="clapsep_research",
            display_name="CLAPSep raw research checkpoint",
            adapter_kind="clapsep_source",
            target_surface="audiosep_prompt",
            runtime="pytorch",
            artifact_paths=(
                get_clapsep_research_checkpoint_path(),
                get_clapsep_research_clap_checkpoint_path(),
                get_clapsep_research_requirements_path(),
            ),
            adapter_options={
                "package_dir": str(get_clapsep_research_checkpoint_path().parents[1]),
                "checkpoint_path": str(get_clapsep_research_checkpoint_path()),
                "clap_checkpoint_path": str(get_clapsep_research_clap_checkpoint_path()),
            },
            notes="Raw CLAPSep source/checkpoint baseline with positive text query.",
        ),
        ModelEvalSpec(
            model_id="waveformer_executorch_export",
            display_name="Waveformer 100 ms ExecuTorch export",
            adapter_kind="unsupported",
            target_surface="waveformer20",
            runtime="executorch",
            runnable=False,
            unsupported_reason="No Python batch adapter exists for this ExecuTorch export.",
            artifact_paths=(_waveformer_pte_path(),),
            notes="Tracked export-only artifact.",
        ),
        ModelEvalSpec(
            model_id="target_speaker_windows",
            display_name="Target Speaker Suppression",
            adapter_kind="unsupported",
            target_surface="reference_speaker",
            runtime="onnx",
            runnable=False,
            unsupported_reason="Out of scope for semantic evaluation; requires speaker reference cases.",
            artifact_paths=(),
            notes="Available product package, intentionally excluded from semantic ranking.",
        ),
    )


def resolve_model_specs(
    requested_models: list[str] | tuple[str, ...] | None,
    *,
    include_unsupported: bool,
) -> list[ModelEvalSpec]:
    """Resolve ids/groups to ordered model specs."""

    specs = {spec.model_id: spec for spec in list_model_specs()}
    requested = list(requested_models or ["auto"])
    if len(requested) > 1:
        groups = sorted(item for item in requested if item in MODEL_GROUPS)
        if groups:
            raise ValueError(f"Model group {groups[0]!r} must be used by itself.")

    if requested == ["all"]:
        names = list(specs)
    elif requested == ["auto"]:
        names = [
            "waveformer_onnx_export",
            "audiosep_hive15cat_onnx",
            "codecsep_dnrv2_15cat_onnx",
            "codecsep_dnrv2_15cat_executorch",
        ]
    elif requested == ["exact15"]:
        names = [
            "audiosep_hive15cat_onnx",
            "codecsep_dnrv2_15cat_onnx",
            "codecsep_dnrv2_15cat_executorch",
        ]
    elif requested == ["research"]:
        names = [
            "audiosep_open_vocab",
            "audiosep_hive_raw",
            "clapsep_research",
            "codecsep_normal_compat",
        ]
    elif requested == ["deployable"]:
        names = [
            "waveformer_onnx_export",
            "audiosep_hive15cat_onnx",
            "codecsep_dnrv2_15cat_onnx",
            "codecsep_dnrv2_15cat_executorch",
        ]
    else:
        names = [MODEL_ALIASES.get(name, name) for name in requested]

    selected: list[ModelEvalSpec] = []
    for name in names:
        if name not in specs:
            raise ValueError(f"Unknown model {name!r}. Use evaluate list-models.")
        spec = specs[name]
        if spec.runnable or include_unsupported:
            selected.append(spec)
    return selected
