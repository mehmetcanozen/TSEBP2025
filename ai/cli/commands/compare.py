"""Model comparison CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai.scripts import run_model_comparison

app = typer.Typer(no_args_is_help=True)


def _append_option(argv: list[str], name: str, value: object | None) -> None:
    if value is not None:
        argv.extend([name, str(value)])


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
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Plan without loading models.")] = False,
    list_models: Annotated[bool, typer.Option("--list-models", help="Print comparison registry JSON.")] = False,
    include_unsupported: Annotated[
        bool,
        typer.Option("--include-unsupported", help="Include export-only models as skipped rows."),
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging.")] = False,
) -> None:
    """Run the existing model-comparison workflow through the new CLI front door."""

    argv: list[str] = []
    _append_option(argv, "--input-dir", input_dir)
    _append_option(argv, "--output-root", output_root)
    if models:
        argv.append("--models")
        argv.extend(models)
    _append_option(argv, "--max-files", max_files)
    _append_option(argv, "--target", target)
    if dry_run:
        argv.append("--dry-run")
    if list_models:
        argv.append("--list-models")
    if include_unsupported:
        argv.append("--include-unsupported")
    if debug:
        argv.append("--debug")
    raise typer.Exit(code=run_model_comparison.main(argv))
