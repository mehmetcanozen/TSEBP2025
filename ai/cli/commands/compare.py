"""Model comparison CLI commands."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True)

LIGHTWEIGHT_MODEL_ALIASES = {
    "auto": "Run the default lightweight comparison selection in the legacy runner.",
    "exact15": "Run exact-15 comparison backends in the legacy runner.",
    "all": "Run every comparison model known to the legacy runner.",
    "audiosep_open_vocab": "Vanilla AudioSep open-vocabulary comparison path.",
    "pure_audiosep": "Legacy alias for audiosep_open_vocab.",
    "audiosep_hive_raw": "Raw AudioSep-Hive research checkpoint registered for future adapter/export work.",
    "waveformer": "Default Waveformer ONNX product backend.",
    "waveformer_onnx_export": "Packaged Waveformer ONNX export smoke target.",
    "waveformer_executorch_export": "Packaged Waveformer ExecuTorch export smoke target.",
    "audiosep_hive15cat": "Alias for audiosep_hive15cat_onnx.",
    "audiosep_hive15cat_onnx": "Packaged AudioSep-Hive exact-15 ONNX backend.",
    "audiosep_hive15cat_executorch": "Packaged AudioSep-Hive exact-15 ExecuTorch backend.",
    "clapsep_hive15cat_onnx": "Prototype CLAPSep-Hive exact-15 ONNX backend.",
    "clapsep_research": "Raw CLAPSep research checkpoint registered for future adapter/export work.",
    "codecsep_normal_compat": "Legacy CodecSep prompt-compatible comparison path.",
    "codecsep_dnrv2_15cat": "Alias for codecsep_dnrv2_15cat_onnx.",
    "codecsep_dnrv2_15cat_onnx": "Packaged CodecSepDNRv2 exact-15 ONNX backend.",
    "codecsep_dnrv2_15cat_executorch": "Packaged CodecSepDNRv2 exact-15 ExecuTorch backend.",
}
LEGACY_MODEL_ID_ALIASES = {
    "pure_audiosep": "audiosep_open_vocab",
    "audiosep_hive15cat": "audiosep_hive15cat_onnx",
    "codecsep_dnrv2_15cat": "codecsep_dnrv2_15cat_onnx",
}
MODEL_GROUPS = {"auto", "exact15", "all"}
CONCRETE_MODEL_IDS = [
    "waveformer",
    "audiosep_open_vocab",
    "audiosep_hive_raw",
    "audiosep_hive15cat_onnx",
    "codecsep_normal_compat",
    "codecsep_dnrv2_15cat_onnx",
    "codecsep_dnrv2_15cat_executorch",
    "waveformer_onnx_export",
    "waveformer_executorch_export",
    "audiosep_hive15cat_executorch",
    "clapsep_hive15cat_onnx",
    "clapsep_research",
]
RUNNABLE_MODEL_IDS = {
    "waveformer",
    "audiosep_open_vocab",
    "audiosep_hive15cat_onnx",
    "codecsep_normal_compat",
    "codecsep_dnrv2_15cat_onnx",
    "codecsep_dnrv2_15cat_executorch",
    "waveformer_onnx_export",
}
MODEL_GROUP_SELECTIONS = {
    "auto": [
        "waveformer",
        "audiosep_hive15cat_onnx",
        "codecsep_dnrv2_15cat_onnx",
        "codecsep_dnrv2_15cat_executorch",
    ],
    "exact15": [
        "audiosep_hive15cat_onnx",
        "codecsep_dnrv2_15cat_onnx",
        "codecsep_dnrv2_15cat_executorch",
    ],
    "all": CONCRETE_MODEL_IDS,
}


def _append_option(argv: list[str], name: str, value: object | None) -> None:
    if value is not None:
        argv.extend([name, str(value)])


def _run_legacy_comparison(argv: list[str]) -> int:
    from ai.scripts import run_model_comparison

    return int(run_model_comparison.main(argv) or 0)


def _resolve_models(models: list[str] | None) -> list[str]:
    requested = list(models or ["auto"])
    if len(requested) > 1:
        grouped = sorted(model for model in requested if model in MODEL_GROUPS)
        if grouped:
            raise typer.BadParameter(
                f"Model group {grouped[0]!r} must be used by itself.",
                param_hint="--model",
            )

    if len(requested) == 1 and requested[0] in MODEL_GROUP_SELECTIONS:
        return list(MODEL_GROUP_SELECTIONS[requested[0]])

    resolved: list[str] = []
    for model in requested:
        if model not in LIGHTWEIGHT_MODEL_ALIASES:
            raise typer.BadParameter(
                f"Unknown model {model!r}. Use --list-models to inspect available ids.",
                param_hint="--model",
            )
        resolved.append(LEGACY_MODEL_ID_ALIASES.get(model, model))
    return resolved


def _write_lightweight_model_registry() -> None:
    typer.echo(json.dumps(LIGHTWEIGHT_MODEL_ALIASES, indent=2, sort_keys=True))


def _write_dry_run_plan(
    *,
    output_root: Path | None,
    input_dir: Path | None,
    models: list[str] | None,
    max_files: int | None,
    target: str | None,
    audiosep_prompt: str | None,
    include_unsupported: bool,
) -> int:
    resolved_models = _resolve_models(models)
    planned_models = [
        model
        for model in resolved_models
        if include_unsupported or model in RUNNABLE_MODEL_IDS
    ]
    resolved_output_root = output_root or Path("ai/data/audio/processed/model_comparison_dry_run")
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model",
        "status",
        "target",
        "audiosep_prompt",
        "input_dir",
        "max_files",
        "include_unsupported",
        "notes",
    ]

    rows = [
        {
            "model": model,
            "status": "planned" if model in RUNNABLE_MODEL_IDS else "unsupported",
            "target": target or "model_default",
            "audiosep_prompt": audiosep_prompt or "",
            "input_dir": str(input_dir or Path("ai/data/audio/raw")),
            "max_files": "" if max_files is None else str(max_files),
            "include_unsupported": str(bool(include_unsupported)).lower(),
            "notes": "lightweight dry-run; no model runtime imported",
        }
        for model in planned_models
    ]

    summary_path = resolved_output_root / "comparison_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest_path = resolved_output_root / "comparison_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "mode": "dry_run",
                "summary": str(summary_path),
                "models": planned_models,
                "input_dir": str(input_dir or Path("ai/data/audio/raw")),
                "target": target,
                "audiosep_prompt": audiosep_prompt,
                "max_files": max_files,
                "include_unsupported": include_unsupported,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    typer.echo(f"Dry-run wrote {len(rows)} row(s): {summary_path}")
    return 0


@app.command("run")
def run(
    input_dir: Annotated[
        Path | None,
        typer.Option("--input-dir", help="Directory containing input audio files."),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", help="Output folder for comparison results."),
    ] = None,
    models: Annotated[
        list[str] | None,
        typer.Option("--model", "--models", help="Model id/group. Repeat for multiple."),
    ] = None,
    max_files: Annotated[int | None, typer.Option("--max-files", help="Limit input files.")] = None,
    target: Annotated[str | None, typer.Option("--target", help="Override target for every model.")] = None,
    audiosep_prompt: Annotated[
        str | None,
        typer.Option(
            "--audiosep-prompt",
            "--audiosep-query",
            "--universal-prompt",
            help=(
                "Override the vanilla AudioSep open-vocabulary prompt. "
                "--universal-prompt is a legacy alias."
            ),
        ),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Plan without loading models.")] = False,
    list_models: Annotated[bool, typer.Option("--list-models", help="Print comparison registry JSON.")] = False,
    include_unsupported: Annotated[
        bool,
        typer.Option("--include-unsupported", help="Include export-only models as skipped rows."),
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging.")] = False,
) -> None:
    """Run the existing model-comparison workflow through the new CLI front door."""

    if list_models:
        _write_lightweight_model_registry()
        raise typer.Exit(code=0)

    if dry_run:
        raise typer.Exit(
            code=_write_dry_run_plan(
                output_root=output_root,
                input_dir=input_dir,
                models=models,
                max_files=max_files,
                target=target,
                audiosep_prompt=audiosep_prompt,
                include_unsupported=include_unsupported,
            )
        )

    argv: list[str] = []
    _append_option(argv, "--input-dir", input_dir)
    _append_option(argv, "--output-root", output_root)
    if models:
        argv.append("--models")
        argv.extend(_resolve_models(models))
    _append_option(argv, "--max-files", max_files)
    _append_option(argv, "--target", target)
    _append_option(argv, "--audiosep-prompt", audiosep_prompt)
    if dry_run:
        argv.append("--dry-run")
    if list_models:
        argv.append("--list-models")
    if include_unsupported:
        argv.append("--include-unsupported")
    if debug:
        argv.append("--debug")
    raise typer.Exit(code=_run_legacy_comparison(argv))
