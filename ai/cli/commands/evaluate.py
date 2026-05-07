"""Evaluation and report-generation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from ai.evaluation.runner import available_models, plan_evaluation, regenerate_report, run_evaluation


app = typer.Typer(no_args_is_help=True)


def _report_formats(value: str) -> tuple[str, ...]:
    normalized = value.strip().lower()
    if normalized in {"none", "off", "false"}:
        return ()
    if normalized in {"md-html", "html-md", "all"}:
        return ("md", "html")
    if normalized in {"md", "markdown"}:
        return ("md",)
    if normalized == "html":
        return ("html",)
    raise typer.BadParameter("Use one of: none, md, html, md-html.", param_hint="--report")


@app.command("list-models")
def list_models() -> None:
    """List semantic evaluation models and adapter status."""

    typer.echo("Model ID                         Runtime      Adapter                  Status")
    typer.echo("-" * 92)
    for card in available_models():
        status = "runnable" if card.get("runnable", True) else "unsupported"
        typer.echo(
            f"{card['model_id']:<32} {card['runtime']:<12} {card['adapter_kind']:<24} {status}"
        )
        if card.get("unsupported_reason"):
            typer.echo(f"  reason: {card['unsupported_reason']}")
        if card.get("notes"):
            typer.echo(f"  {card['notes']}")


@app.command("plan")
def plan(
    input_dir: Annotated[
        Path,
        typer.Option("--input-dir", help="Raw input audio directory."),
    ] = Path("ai/data/audio/raw"),
    suite: Annotated[
        str,
        typer.Option("--suite", help="Evaluation suite: full, reference, or coverage."),
    ] = "full",
    models: Annotated[
        list[str] | None,
        typer.Option("--model", "--models", help="Model id/group. Repeat for multiple."),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", help="Planned output directory."),
    ] = None,
    max_cases: Annotated[
        int | None,
        typer.Option("--max-cases", min=1, help="Limit cases for smoke planning."),
    ] = None,
    include_unsupported: Annotated[
        bool,
        typer.Option("--include-unsupported/--skip-unsupported", help="Include unsupported model rows."),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the plan without writing files."),
    ] = False,
) -> None:
    """Build an evaluation manifest and case/model plan without running models."""

    result = plan_evaluation(
        input_dir=input_dir,
        suite=suite,
        models=models,
        output_root=output_root,
        max_cases=max_cases,
        include_unsupported=include_unsupported,
        dry_run=dry_run,
    )
    typer.echo(json.dumps(result, indent=2))


@app.command("run")
def run(
    input_dir: Annotated[
        Path,
        typer.Option("--input-dir", help="Raw input audio directory."),
    ] = Path("ai/data/audio/raw"),
    suite: Annotated[
        str,
        typer.Option("--suite", help="Evaluation suite: full, reference, or coverage."),
    ] = "full",
    models: Annotated[
        list[str] | None,
        typer.Option("--model", "--models", help="Model id/group. Repeat for multiple."),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", help="Evaluation output directory."),
    ] = None,
    max_cases: Annotated[
        int | None,
        typer.Option("--max-cases", min=1, help="Limit cases for smoke runs."),
    ] = None,
    repeats: Annotated[int, typer.Option("--repeats", min=1, help="Timed repeats per case.")] = 1,
    warmup_runs: Annotated[
        int,
        typer.Option("--warmup-runs", min=0, help="Warmup passes before timed runs."),
    ] = 1,
    include_unsupported: Annotated[
        bool,
        typer.Option("--include-unsupported/--skip-unsupported", help="Include unsupported model rows."),
    ] = True,
    save_audio: Annotated[
        bool,
        typer.Option("--save-audio/--no-save-audio", help="Keep clean/removed WAV outputs."),
    ] = True,
    report: Annotated[
        str,
        typer.Option("--report", help="Report formats: none, md, html, md-html."),
    ] = "md-html",
    monitor_interval_seconds: Annotated[
        float,
        typer.Option("--monitor-interval-seconds", min=0.05, help="Resource sampling interval."),
    ] = 0.25,
) -> None:
    """Run a fair isolated-worker evaluation and generate structured outputs."""

    result = run_evaluation(
        input_dir=input_dir,
        suite=suite,
        models=models,
        output_root=output_root,
        max_cases=max_cases,
        repeats=repeats,
        warmup_runs=warmup_runs,
        include_unsupported=include_unsupported,
        save_audio=save_audio,
        report_formats=_report_formats(report),
        monitor_interval_seconds=monitor_interval_seconds,
    )
    typer.echo(json.dumps(result, indent=2))


@app.command("report")
def report_command(
    run_dir: Annotated[
        Path,
        typer.Option("--run-dir", help="Existing evaluation run directory."),
    ],
    report: Annotated[
        str,
        typer.Option("--report", help="Report formats: md, html, md-html."),
    ] = "md-html",
) -> None:
    """Regenerate report.md/report.html and figures from existing CSV/JSON outputs."""

    result = regenerate_report(run_dir, _report_formats(report))
    typer.echo(json.dumps(result, indent=2))
