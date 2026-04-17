"""
DEBUG Real-time Suppression - Shows what YAMNet detects.
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

from ai.scripts.demos.commons import setup_demo_logging, create_custom_profile, mono_from_stereo
from ai.ai_runtime.profiles import ControlEngine, ControlMode, ProfileManager
from ai.ai_runtime.utils.codecsep import (
    add_codecsep_runtime_arguments,
    build_codecsep_call_kwargs_from_args,
)

logger = setup_demo_logging()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DEBUG Real-time mic - shows detections")
    parser.add_argument("--suppress", "-s", type=str, default="typing")
    parser.add_argument("--duration", "-d", type=int, default=30)
    parser.add_argument("--threshold", "-t", type=float, default=0.3)
    parser.add_argument("--suppress-all", action="store_true")
    add_codecsep_runtime_arguments(
        parser,
        default_mode="fixed_category",
        default_query_strategy="single_pass",
        default_multistep_steps=0,
    )
    return parser


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.separator_backend == "audiosep_hive15cat":
        parser.error(
            "audiosep_hive15cat is not supported in demo_debug_realtime.py because this demo "
            "runs suppression inside the audio callback. Use ai.ai_runtime.audio.recorder_cleaner "
            "for buffered live support."
        )

    categories = [c.strip() for c in args.suppress.split(",")]
    codecsep_call_kwargs = build_codecsep_call_kwargs_from_args(args)
    manager = ProfileManager()
    profile = create_custom_profile(
        manager,
        categories,
        suppression_params={
            "separator_backend": args.separator_backend,
            "masking_method": args.masking_method,
            "detection_threshold": args.threshold,
            "codecsep_checkpoint_path": args.codecsep_checkpoint,
            "codecsep_device": args.codecsep_device,
            **codecsep_call_kwargs,
        },
    )
    engine = ControlEngine(profile_manager=manager)
    engine.set_profile(profile)
    engine.set_mode(ControlMode.MANUAL)
    detection_count = 0
    last_detections = {}

    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal detection_count, last_detections
        if status:
            logger.warning("Status: %s", status)
        try:
            audio_mono = mono_from_stereo(indata)
            try:
                detections = engine.suppressor.detect_categories(audio_mono, 44100, threshold=args.threshold)
                if detections and detections != last_detections:
                    print(f"\nDETECTED: {detections}")
                    last_detections = detections.copy()
                    detection_count += 1
            except Exception:
                pass

            if args.suppress_all:
                clean_audio = engine.suppressor.suppress(
                    audio_mono,
                    44100,
                    [],
                    suppress_all=True,
                    separator_backend=args.separator_backend,
                    masking_method=args.masking_method,
                    codecsep_checkpoint_path=args.codecsep_checkpoint,
                    codecsep_device=args.codecsep_device,
                    **codecsep_call_kwargs,
                )
            else:
                clean_audio = engine.process_audio(audio_mono, 44100)

            if outdata.shape[1] == 1:
                outdata[:, 0] = clean_audio
            else:
                outdata[:, 0] = clean_audio
                outdata[:, 1] = clean_audio
        except Exception:
            outdata[:] = indata

    try:
        with sd.Stream(
            samplerate=44100,
            blocksize=int(44100 * 0.5),
            channels=max(1, sd.query_devices(kind="input")["max_input_channels"]),
            dtype="float32",
            callback=audio_callback,
        ):
            for _ in range(args.duration):
                time.sleep(1)
    finally:
        manager.delete_profile(profile.id)
        print(f"\nTotal detections: {detection_count}")


if __name__ == "__main__":
    main()
