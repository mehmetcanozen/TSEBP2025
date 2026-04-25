"""Stream a WAV file into a virtual cable playback endpoint.

This is a source simulator only: it does not run suppression. The intended
debug loop is:

1. Play a WAV into `CABLE Input` with this script.
2. Select the paired `CABLE Output` recording endpoint as the desktop app input.
3. Let the desktop app run its normal live/offline logic.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

try:
    import sounddevice as sd
except ImportError:

    class _MissingSoundDevice:
        @staticmethod
        def query_devices(*_args, **_kwargs):
            raise ImportError(
                "sounddevice is required for virtual mic playback. "
                "Install with: pip install sounddevice"
            )

        @staticmethod
        def play(*_args, **_kwargs):
            raise ImportError(
                "sounddevice is required for virtual mic playback. "
                "Install with: pip install sounddevice"
            )

        @staticmethod
        def wait():
            raise ImportError(
                "sounddevice is required for virtual mic playback. "
                "Install with: pip install sounddevice"
            )

        @staticmethod
        def stop():
            return None

    sd = _MissingSoundDevice()


DEFAULT_PLAYBACK_NAME = "CABLE Input"
PAIRED_RECORDING_NAME = "CABLE Output"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _device_value(device: Any, key: str, default: Any = None) -> Any:
    if hasattr(device, "get"):
        return device.get(key, default)
    try:
        return device[key]
    except (KeyError, TypeError):
        return default


def _max_channels(device: Any, key: str) -> int:
    return int(_device_value(device, key, 0) or 0)


def list_audio_devices() -> None:
    """Log input and output devices in a format useful for cable routing."""
    devices = sd.query_devices()
    logger.info("Output devices you can stream a WAV into:")
    for idx, dev in enumerate(devices):
        out_channels = _max_channels(dev, "max_output_channels")
        if out_channels > 0:
            logger.info("  %3s | out=%s | %s", idx, out_channels, _device_value(dev, "name", ""))

    logger.info("Input devices the desktop app can capture from:")
    for idx, dev in enumerate(devices):
        in_channels = _max_channels(dev, "max_input_channels")
        if in_channels > 0:
            logger.info("  %3s | in=%s  | %s", idx, in_channels, _device_value(dev, "name", ""))


def find_cable_input_device(search_name: str = DEFAULT_PLAYBACK_NAME, device_id: int | None = None) -> int:
    """Return a playback device id for the virtual cable input endpoint."""
    devices = list(sd.query_devices())

    if device_id is not None:
        if device_id < 0 or device_id >= len(devices):
            raise ValueError(f"Device id {device_id} is outside the available device range.")
        if _max_channels(devices[device_id], "max_output_channels") <= 0:
            raise ValueError(f"Device id {device_id} is not an output/playback endpoint.")
        return device_id

    needle = search_name.casefold()
    for idx, dev in enumerate(devices):
        name = str(_device_value(dev, "name", ""))
        if _max_channels(dev, "max_output_channels") > 0 and needle in name.casefold():
            return idx

    for idx, dev in enumerate(devices):
        name = str(_device_value(dev, "name", ""))
        if _max_channels(dev, "max_output_channels") > 0 and "cable" in name.casefold():
            return idx

    return -1


def _match_channels(data: np.ndarray, channels: int) -> np.ndarray:
    channels = max(1, int(channels))
    if channels == 1:
        return data.mean(axis=1, keepdims=True).astype(np.float32, copy=False)
    if data.shape[1] == channels:
        return data.astype(np.float32, copy=False)
    if data.shape[1] == 1:
        return np.repeat(data, channels, axis=1).astype(np.float32, copy=False)
    if data.shape[1] > channels:
        return data[:, :channels].astype(np.float32, copy=False)

    repeats = int(np.ceil(channels / data.shape[1]))
    return np.tile(data, (1, repeats))[:, :channels].astype(np.float32, copy=False)


def _load_wav_for_playback(
    input_path: str | Path,
    *,
    channels: int,
    volume: float,
    start_silence: float,
) -> tuple[np.ndarray, int]:
    data, samplerate = sf.read(str(input_path), dtype="float32", always_2d=True)
    data = _match_channels(np.asarray(data, dtype=np.float32), channels)
    if volume < 0:
        raise ValueError("--volume must be zero or greater.")
    data = np.clip(data * float(volume), -1.0, 1.0).astype(np.float32, copy=False)

    silence_samples = int(round(max(0.0, start_silence) * samplerate))
    if silence_samples > 0:
        silence = np.zeros((silence_samples, data.shape[1]), dtype=np.float32)
        data = np.concatenate((silence, data), axis=0)
    return data, int(samplerate)


def stream_virtual_mic(
    input_path: str,
    loop: bool = True,
    device_name: str = DEFAULT_PLAYBACK_NAME,
    *,
    device_id: int | None = None,
    channels: int = 2,
    volume: float = 1.0,
    start_silence: float = 0.5,
) -> None:
    cable_device_id = find_cable_input_device(device_name, device_id=device_id)
    if cable_device_id == -1:
        logger.error("Could not find output device matching '%s'. Is VB-CABLE installed?", device_name)
        list_audio_devices()
        sys.exit(1)

    device_info = sd.query_devices()[cable_device_id]
    max_output_channels = _max_channels(device_info, "max_output_channels")
    playback_channels = max(1, min(int(channels), max_output_channels))

    try:
        data, samplerate = _load_wav_for_playback(
            input_path,
            channels=playback_channels,
            volume=volume,
            start_silence=start_silence,
        )
    except Exception as exc:
        logger.error("Failed to load %s: %s", input_path, exc)
        return

    logger.info(
        "Target playback endpoint: %s (ID: %s, channels: %s)",
        _device_value(device_info, "name", ""),
        cable_device_id,
        playback_channels,
    )
    logger.info(
        "Select '%s' as the desktop app input device to capture this WAV as a microphone.",
        PAIRED_RECORDING_NAME,
    )
    logger.info(
        "For one-cable testing, use the desktop app's Listen Locally mode. "
        "Testing desktop Virtual Mic output at the same time needs a second cable."
    )

    shutdown_event = threading.Event()

    def _play_loop() -> None:
        iteration = 1
        while not shutdown_event.is_set():
            logger.info("Streaming iteration %s... Press Ctrl+C to stop.", iteration)
            try:
                sd.play(data, samplerate, device=cable_device_id)
                sd.wait()
            except Exception as exc:
                if not shutdown_event.is_set():
                    logger.error("Playback error: %s", exc)
                break
            if not loop:
                break
            iteration += 1
        logger.info("Stream ended.")

    thread = threading.Thread(target=_play_loop, daemon=True)
    thread.start()

    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopping virtual microphone stream...")
        shutdown_event.set()
        sd.stop()
        thread.join(timeout=1.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Play a WAV into a virtual audio cable so another app can capture it as a microphone.",
    )
    parser.add_argument("--input", type=str, default=None, help="Path to the WAV file to stream")
    parser.add_argument("--no-loop", action="store_true", help="Play the file only once instead of looping")
    parser.add_argument(
        "--device-name",
        type=str,
        default=DEFAULT_PLAYBACK_NAME,
        help="Search string for the virtual playback endpoint",
    )
    parser.add_argument("--device-id", type=int, default=None, help="Exact output device ID from --list-devices")
    parser.add_argument("--channels", type=int, default=2, help="Playback channel count to open")
    parser.add_argument("--volume", type=float, default=1.0, help="Linear volume multiplier before playback")
    parser.add_argument(
        "--start-silence",
        type=float,
        default=0.5,
        help="Seconds of silence to prepend before the WAV starts",
    )
    parser.add_argument("--list-devices", action="store_true", help="Print audio devices and exit")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_devices:
        list_audio_devices()
        if not args.input:
            return

    if not args.input:
        parser.error("--input is required unless --list-devices is used")

    stream_virtual_mic(
        args.input,
        loop=not args.no_loop,
        device_name=args.device_name,
        device_id=args.device_id,
        channels=args.channels,
        volume=args.volume,
        start_silence=args.start_silence,
    )


if __name__ == "__main__":
    main()
