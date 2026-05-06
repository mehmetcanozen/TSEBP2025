"""Export and packaging commands."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True)

_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


@app.command("waveformer-edge", context_settings=_PASSTHROUGH)
def waveformer_edge(ctx: typer.Context) -> None:
    """Run the Waveformer edge packager.

    Extra arguments are passed through to `ai.export.export_waveformer_edge`.
    """

    from ai.export import export_waveformer_edge

    raise typer.Exit(code=export_waveformer_edge.main(list(ctx.args)))


@app.command("target-speaker-windows", context_settings=_PASSTHROUGH)
def target_speaker_windows(ctx: typer.Context) -> None:
    """Run the TargetSpeakerWindows packager.

    Extra arguments are passed through to `ai.export.export_target_speaker_windows`.
    """

    from ai.export import export_target_speaker_windows

    export_target_speaker_windows.main(list(ctx.args))


@app.command("codecsep-dnrv2-15cat", context_settings=_PASSTHROUGH)
def codecsep_dnrv2_15cat(ctx: typer.Context) -> None:
    """Run the CodecSepDNRv2 exact-15 freeze/export workflow."""

    from ai.export import freeze_codecsep_dnrv2_15cat

    freeze_codecsep_dnrv2_15cat.main(list(ctx.args))
