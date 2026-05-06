"""Environment diagnostics for the Python AI workspace."""

from __future__ import annotations

import importlib.util
import json
import platform
import sys
from typing import Annotated

import typer

from ai.ai_runtime.artifacts import missing_required_artifacts
from ai.ai_runtime.utils.paths import get_project_root

app = typer.Typer(no_args_is_help=True)


def _module_status(name: str) -> dict[str, object]:
    spec = importlib.util.find_spec(name)
    return {"module": name, "available": spec is not None}


@app.command("env")
def env(
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON diagnostics.")] = False,
) -> None:
    """Print Python, dependency, and artifact readiness diagnostics."""

    modules = [
        "numpy",
        "soundfile",
        "typer",
        "sounddevice",
        "onnxruntime",
        "torch",
        "torchaudio",
        "tensorflow",
        "clearvoice",
    ]
    payload = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "project_root": str(get_project_root()),
        "modules": [_module_status(name) for name in modules],
        "missing_required_artifacts": [status.as_dict() for status in missing_required_artifacts()],
    }
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo(f"Python: {payload['python'].split()[0]} ({payload['executable']})")
    typer.echo(f"Platform: {payload['platform']}")
    typer.echo(f"Project: {payload['project_root']}")
    typer.echo("")
    typer.echo("Modules:")
    for item in payload["modules"]:
        marker = "OK" if item["available"] else "missing"
        typer.echo(f"  {marker:<7} {item['module']}")
    typer.echo("")
    if payload["missing_required_artifacts"]:
        typer.echo("Missing required model artifacts:")
        for item in payload["missing_required_artifacts"]:
            typer.echo(f"  {item['key']}: {item['path']}")
    else:
        typer.echo("Required model artifacts are present.")
