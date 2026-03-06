import argparse
import logging
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def find_cable_input_device(search_name: str = "CABLE Input") -> int:
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev["max_output_channels"] > 0 and search_name in dev["name"]:
            return i
    for i, dev in enumerate(devices):
        if dev["max_output_channels"] > 0 and "CABLE" in dev["name"]:
            return i
    return -1


def stream_virtual_mic(input_path: str, loop: bool = True, device_name: str = "CABLE Input"):
    try:
        data, samplerate = sf.read(input_path)
    except Exception as e:
        logger.error("Failed to load %s: %s", input_path, e)
        return

    if data.ndim == 1:
        data = np.stack((data, data), axis=-1)

    cable_device_id = find_cable_input_device(device_name)
    if cable_device_id == -1:
        logger.error("Could not find device matching '%s'. Is VB-Audio Virtual Cable installed?", device_name)
        logger.error("Available output devices:")
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_output_channels"] > 0:
                logger.error("  %s: %s", i, dev["name"])
        sys.exit(1)

    device_info = sd.query_devices(cable_device_id, "output")
    logger.info("Targeting Virtual Device: %s (ID: %s)", device_info["name"], cable_device_id)

    silence = np.zeros((int(samplerate * 0.5), data.shape[1]), dtype=data.dtype)
    data = np.concatenate((silence, data))
    shutdown_event = threading.Event()

    def _play_loop():
        iteration = 1
        while not shutdown_event.is_set():
            logger.info("Streaming iter %s... Press Ctrl+C to stop.", iteration)
            try:
                sd.play(data, samplerate, device=cable_device_id)
                sd.wait()
            except Exception as e:
                if not shutdown_event.is_set():
                    logger.error("Playback error: %s", e)
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
        logger.info("\nStopping virtual microphone stream...")
        shutdown_event.set()
        sd.stop()
        thread.join(timeout=1.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream a WAV file into a Virtual Audio Cable to simulate a microphone.")
    parser.add_argument("--input", type=str, required=True, help="Path to the WAV file to stream")
    parser.add_argument("--no-loop", action="store_true", help="Play the file only once instead of looping indefinitely")
    parser.add_argument("--device-name", type=str, default="CABLE Input", help="Search string for the virtual output device")
    args = parser.parse_args()
    stream_virtual_mic(args.input, loop=not args.no_loop, device_name=args.device_name)
