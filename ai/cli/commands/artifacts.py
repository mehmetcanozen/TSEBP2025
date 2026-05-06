"""Model artifact diagnostic commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from ai.ai_runtime.artifacts import ARTIFACT_DOWNLOAD_URL, check_artifacts
from ai.ai_runtime.contracts import ArtifactRole

app = typer.Typer(no_args_is_help=True)


@app.command("check")
def check(
    include_optional: Annotated[
        bool,
        typer.Option("--include-optional/--required-only", help="Include optional comparison artifacts."),
    ] = True,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON diagnostics.")] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit non-zero when required artifacts are missing."),
    ] = False,
) -> None:
    """Check whether local model artifacts are restored."""

    statuses = check_artifacts(include_optional=include_optional)
    missing_required = [
        status for status in statuses if status.role == ArtifactRole.REQUIRED and not status.exists
    ]
    if as_json:
        typer.echo(json.dumps([status.as_dict() for status in statuses], indent=2))
    else:
        for status in statuses:
            marker = "OK" if status.exists else "MISSING"
            size = f"{status.size_bytes} bytes" if status.size_bytes is not None else "-"
            typer.echo(f"[{marker:<7}] {status.role.value:<8} {status.key:<38} {size}")
            typer.echo(f"          {status.path}")
        typer.echo("")
        if missing_required:
            typer.echo("Missing required artifacts. Restore ai/models/Exports from:")
            typer.echo(ARTIFACT_DOWNLOAD_URL)
        else:
            typer.echo("Required artifacts are present.")

    if strict and missing_required:
        raise typer.Exit(code=1)
