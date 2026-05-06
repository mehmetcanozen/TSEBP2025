"""Main Typer application for TSEBP2025 AI tooling."""

from __future__ import annotations

import typer

from ai.cli.commands import artifacts, compare, diagnostics, export, models, stream, suppress

app = typer.Typer(
    name="tsebp-ai",
    help="Practical CLI for local model suppression, artifact checks, exports, and diagnostics.",
    no_args_is_help=True,
)

app.add_typer(suppress.app, name="suppress", help="Run file-based semantic or speaker suppression.")
app.add_typer(models.app, name="models", help="Inspect available model backends and category surfaces.")
app.add_typer(artifacts.app, name="artifacts", help="Check restored model artifacts.")
app.add_typer(compare.app, name="compare", help="Run or inspect model comparison jobs.")
app.add_typer(stream.app, name="stream", help="Stream WAV files into a Windows playback endpoint.")
app.add_typer(export.app, name="export", help="Run export and packaging entrypoints.")
app.add_typer(diagnostics.app, name="diagnostics", help="Inspect Python/runtime environment state.")


@app.command()
def version() -> None:
    """Print the AI CLI version."""

    typer.echo("tsebp-ai 0.1.0")
