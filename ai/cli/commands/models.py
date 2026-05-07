"""Model registry commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from ai.ai_runtime.artifacts import load_model_selection
from ai.ai_runtime.registry import list_backends, list_model_packages

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_models(
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON instead of a text table.")] = False,
    include_categories: Annotated[
        bool,
        typer.Option("--categories", help="Include category names in text output."),
    ] = False,
    include_packages: Annotated[
        bool,
        typer.Option("--packages/--no-packages", help="Include registered model packages."),
    ] = True,
) -> None:
    """List model backends exposed by the Python runtime."""

    backends = list_backends()
    packages = list_model_packages() if include_packages else ()
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "backends": [
                        {
                            "backend_id": item.backend_id.value,
                            "display_name": item.display_name,
                            "category_surface": item.category_surface,
                            "runtime_kind": item.runtime_kind,
                            "categories": list(item.categories),
                            "artifact_paths": [str(path) for path in item.artifact_paths],
                            "notes": item.notes,
                        }
                        for item in backends
                    ],
                    "packages": [
                        {
                            "model_id": item.model_id,
                            "display_name": item.display_name,
                            "family": item.family,
                            "runtime_status": item.runtime_status,
                            "package_path": str(item.package_path),
                            "categories": list(item.categories),
                            "artifact_paths": [str(path) for path in item.artifact_paths],
                            "notes": item.notes,
                        }
                        for item in packages
                    ],
                },
                indent=2,
            ),
        )
        return

    selection = load_model_selection()
    typer.echo(f"Default model: {selection.get('default_model_id', 'unknown')}")
    typer.echo("")
    typer.echo(f"{'Backend':<26} {'Surface':<24} {'Runtime'}")
    typer.echo("-" * 88)
    for item in backends:
        typer.echo(f"{item.backend_id.value:<26} {item.category_surface:<24} {item.runtime_kind}")
        typer.echo(f"  {item.display_name}: {item.notes}")
        if include_categories and item.categories:
            typer.echo(f"  categories: {', '.join(item.categories)}")

    if packages:
        typer.echo("")
        typer.echo("Registered model packages")
        typer.echo(f"{'Model ID':<28} {'Family':<16} {'Status'}")
        typer.echo("-" * 88)
        for item in packages:
            typer.echo(f"{item.model_id:<28} {item.family:<16} {item.runtime_status}")
            typer.echo(f"  {item.display_name}: {item.notes}")
            typer.echo(f"  manifest: {item.package_path}")
            if include_categories and item.categories:
                typer.echo(f"  categories: {', '.join(item.categories)}")


@app.command("selection")
def model_selection() -> None:
    """Print the tracked model selection manifest."""

    typer.echo(json.dumps(load_model_selection(), indent=2))
