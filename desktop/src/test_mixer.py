"""
CLI smoke test for the audio mixer.

Example:
    python desktop/src/test_mixer.py --duration 10 --speech-gain 1.0 --noise-gain 0.2
"""

from __future__ import annotations

import argparse
import time
from typing import List, Optional

from audio.mixer_controller import MixerController
from audio.audio_io import StreamConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audio mixer smoke test")
    parser.add_argument("--duration", type=int, default=10, help="Seconds to run")
    parser.add_argument("--sample-rate", type=int, default=44_100, help="Sample rate")
    parser.add_argument("--frames", type=int, default=512, help="Frames per buffer")
    parser.add_argument("--channels", type=int, default=1, help="Input/output channels")
    parser.add_argument("--speech-gain", type=float, default=1.0, help="Speech gain")
    parser.add_argument("--noise-gain", type=float, default=0.2, help="Noise gain")
    parser.add_argument("--events-gain", type=float, default=0.5, help="Events gain")
    parser.add_argument(
        "--targets",
        nargs="*",
        default=None,
        help="Waveformer targets (defaults to all targets when omitted)",
    )
    parser.add_argument(
        "--freeze-ui",
        action="store_true",
        help="Simulate a UI freeze in the main process to verify GIL isolation.",
    )
    return parser.parse_args()


def run_smoke(duration: int, config: StreamConfig, gains, targets: Optional[List[str]], freeze_ui: bool) -> None:
    with MixerController(config=config, targets=targets) as mixer:
        mixer.set_gains(**gains)
        theoretical_latency_ms = (config.frames_per_buffer / config.sample_rate) * 1000
        print(
            f"Running mixer for {duration}s @ {config.sample_rate} Hz, "
            f"{config.frames_per_buffer} f/buffer (~{theoretical_latency_ms:.1f} ms buffer)."
        )
        start = time.time()
        freeze_done = False
        while time.time() - start < duration:
            levels = mixer.get_levels()
            if levels:
                rms = levels.get("rms")
                print(f"RMS: {rms:.4f} Gains: {levels.get('gains')}")
            if freeze_ui and not freeze_done and (time.time() - start) > (duration / 2):
                print("Simulating UI freeze (main thread sleep 0.5s)")
                time.sleep(0.5)
                freeze_done = True
            time.sleep(0.05)
        print("Stopping mixer...")


def main() -> None:
    args = parse_args()
    cfg = StreamConfig(
        sample_rate=args.sample_rate,
        frames_per_buffer=args.frames,
        channels=args.channels,
    )
    gains = {
        "speech": args.speech_gain,
        "noise": args.noise_gain,
        "events": args.events_gain,
    }
    run_smoke(args.duration, cfg, gains, targets=args.targets, freeze_ui=args.freeze_ui)


if __name__ == "__main__":
    main()
