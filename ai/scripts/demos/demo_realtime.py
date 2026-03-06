"""
Real-time Microphone Noise Suppression Demo.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import sounddevice as sd

_root = Path(__file__).resolve().parents[3]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ai.scripts.demos.commons import setup_demo_logging, mono_from_stereo
from ai.ai_runtime.profiles import ControlEngine, ControlMode

logger = setup_demo_logging()


class RealtimeSuppressor:
    def __init__(self, profile_id: str = "default-focus", sample_rate: int = 44100):
        self.sample_rate = sample_rate
        hop_length = 512
        approx_chunk_size = int(self.sample_rate * 0.1)
        self.chunk_size = max(hop_length, (approx_chunk_size // hop_length) * hop_length)
        self.engine = ControlEngine()
        self.engine.set_profile_by_id(profile_id)
        self.engine.set_mode(ControlMode.MANUAL)
        self.suppress_all = False
        self.universal_prompts = []
        self.running = False

    def audio_callback(self, indata, outdata, frames, time_info, status):
        if status:
            logger.warning("Audio callback status: %s", status)
        try:
            audio_mono = mono_from_stereo(indata)
            if self.suppress_all or self.universal_prompts:
                clean_audio = self.engine.suppressor.suppress(
                    audio_mono,
                    self.sample_rate,
                    [],
                    suppress_all=self.suppress_all,
                    universal_prompts=self.universal_prompts,
                )
            else:
                clean_audio = self.engine.process_audio(audio_mono, self.sample_rate)
            outdata[:, 0] = clean_audio
            outdata[:, 1] = clean_audio
        except Exception:
            outdata[:] = indata

    def start(self, device=None, duration_seconds=None):
        self.running = True
        try:
            with sd.Stream(
                device=device,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                channels=2,
                dtype="float32",
                callback=self.audio_callback,
            ):
                if duration_seconds:
                    time.sleep(duration_seconds)
                else:
                    while self.running:
                        time.sleep(0.1)
        finally:
            self.running = False


def main():
    parser = argparse.ArgumentParser(description="Real-time mic noise suppression")
    parser.add_argument("--profile", "-p", default="default-focus")
    parser.add_argument("--duration", "-d", type=int, default=None)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--suppress-all", action="store_true")
    parser.add_argument("--universal", "-u", type=str, default=None)
    args = parser.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    suppressor = RealtimeSuppressor(profile_id=args.profile, sample_rate=44100)
    suppressor.suppress_all = args.suppress_all
    suppressor.universal_prompts = [p.strip() for p in args.universal.split(",")] if args.universal else []
    suppressor.start(device=args.device, duration_seconds=args.duration)


if __name__ == "__main__":
    main()
