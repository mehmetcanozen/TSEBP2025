"""Audio streaming helper commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai.scripts.demos import virtual_mic_streamer

app = typer.Typer(no_args_is_help=True)


@app.command("wav")
def wav(
    input_path: Annotated[
        Path | None,
        typer.Option("--input", "-i", help="WAV/FLAC/etc. file to play into a playback endpoint."),
    ] = None,
    list_devices: Annotated[
        bool,
        typer.Option("--list-devices", help="List input/output audio devices and exit."),
    ] = False,
    device_name: Annotated[
        str,
        typer.Option("--device-name", help="Search string for the playback endpoint."),
    ] = virtual_mic_streamer.DEFAULT_PLAYBACK_NAME,
    device_id: Annotated[
        int | None,
        typer.Option("--device-id", help="Exact output device id from --list-devices."),
    ] = None,
    channels: Annotated[int, typer.Option("--channels", min=1, help="Playback channel count.")] = 2,
    volume: Annotated[float, typer.Option("--volume", min=0.0, help="Linear playback gain.")] = 1.0,
    start_silence: Annotated[
        float,
        typer.Option("--start-silence", min=0.0, help="Seconds of silence before playback."),
    ] = 0.5,
    once: Annotated[bool, typer.Option("--once", help="Play once instead of looping.")] = False,
) -> None:
    """Play a WAV into VB-CABLE or another Windows playback endpoint."""

    if list_devices:
        virtual_mic_streamer.list_audio_devices()
        if input_path is None:
            return
    if input_path is None:
        raise typer.BadParameter("--input is required unless --list-devices is used")
    virtual_mic_streamer.stream_virtual_mic(
        str(input_path),
        loop=not once,
        device_name=device_name,
        device_id=device_id,
        channels=channels,
        volume=volume,
        start_silence=start_silence,
    )
