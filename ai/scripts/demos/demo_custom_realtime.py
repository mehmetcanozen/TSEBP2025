"""
Custom Real-time Suppression Demo
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
try:
    import sounddevice as sd
except ImportError:
    class _MissingSoundDevice:
        InputStream = None

        @staticmethod
        def query_devices(*_args, **_kwargs):
            raise ImportError(
                "sounddevice is required for realtime microphone demos. "
                "Install with: pip install sounddevice"
            )

        def __getattr__(self, _name: str):
            raise ImportError(
                "sounddevice is required for realtime microphone demos. "
                "Install with: pip install sounddevice"
            )

    sd = _MissingSoundDevice()

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
    parser = argparse.ArgumentParser(description="Real-time mic noise suppression (custom categories)")
    parser.add_argument("--suppress", "-s", type=str, default="typing")
    parser.add_argument("--duration", "-d", type=int, default=10)
    parser.add_argument("--threshold", "-t", type=float, default=0.3)
    parser.add_argument("--suppress-all", action="store_true")
    parser.add_argument(
        "--audiosep-prompt",
        "--audiosep-query",
        "--universal",
        "-u",
        dest="audiosep_prompt",
        type=str,
        default=None,
        help="Vanilla AudioSep/open-vocabulary prompts. --universal is a legacy alias.",
    )
    parser.add_argument("--list-categories", action="store_true")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=int, default=None)
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

    if args.list_categories:
        print("Example: python ai/scripts/demos/demo_custom_realtime.py --suppress typing,wind,siren")
        return
    if args.list_devices:
        print(sd.query_devices())
        return
    if args.separator_backend in {"audiosep_hive15cat", "codecsep_dnrv2_15cat"}:
        parser.error(
            f"{args.separator_backend} is not supported in demo_custom_realtime.py because this demo "
            "runs suppression inside the audio callback. Use ai.ai_runtime.audio.recorder_cleaner "
            "for buffered live support."
        )

    categories = [c.strip() for c in args.suppress.split(",")] if args.suppress else []
    universal_prompts = (
        [p.strip() for p in args.audiosep_prompt.split(",")] if args.audiosep_prompt else []
    )
    codecsep_call_kwargs = build_codecsep_call_kwargs_from_args(args)
    suppression_params = {
        "separator_backend": args.separator_backend,
        "masking_method": args.masking_method,
        "detection_threshold": args.threshold,
        "codecsep_checkpoint_path": args.codecsep_checkpoint,
        "codecsep_device": args.codecsep_device,
        **codecsep_call_kwargs,
    }

    manager = ProfileManager()
    profile = create_custom_profile(
        manager,
        categories,
        name="Custom Realtime",
        suppression_params=suppression_params,
    )
    engine = ControlEngine(profile_manager=manager)
    engine.set_profile(profile)
    engine.set_mode(ControlMode.MANUAL)

    if hasattr(engine, "suppressor"):
        _ = engine.suppressor
        for cat in categories:
            if cat in engine.suppressor.category_map:
                engine.suppressor.category_map[cat]["detection_threshold"] = args.threshold

    context_duration = 1.0
    context_size = int(44100 * context_duration)
    rolling_buffer = np.zeros(context_size, dtype=np.float32)

    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal rolling_buffer
        if status:
            logger.warning("Status: %s", status)
        try:
            audio_mono = mono_from_stereo(indata)
            chunk_len = len(audio_mono)
            rolling_buffer = np.roll(rolling_buffer, -chunk_len)
            rolling_buffer[-chunk_len:] = audio_mono

            if args.suppress_all or universal_prompts:
                clean_full = engine.suppressor.suppress(
                    rolling_buffer,
                    44100,
                    [],
                    suppress_all=args.suppress_all,
                    universal_prompts=universal_prompts,
                    separator_backend=args.separator_backend,
                    masking_method=args.masking_method,
                    codecsep_checkpoint_path=args.codecsep_checkpoint,
                    codecsep_device=args.codecsep_device,
                    **codecsep_call_kwargs,
                )
            else:
                clean_full = engine.process_audio(rolling_buffer, 44100)

            clean_audio = clean_full[-chunk_len:]
            if outdata.shape[1] == 1:
                outdata[:, 0] = clean_audio
            else:
                outdata[:, 0] = clean_audio
                outdata[:, 1] = clean_audio
        except Exception:
            outdata[:] = indata

    try:
        hop_length = 512
        samplerate = 44100
        approx_chunk_size = int(samplerate * 0.1)
        chunk_size = max(hop_length, (approx_chunk_size // hop_length) * hop_length)
        with sd.Stream(
            device=(args.device, None),
            samplerate=samplerate,
            blocksize=chunk_size,
            channels=max(1, sd.query_devices(kind="input")["max_input_channels"]),
            dtype="float32",
            callback=audio_callback,
        ):
            for _ in range(args.duration):
                time.sleep(1)
    finally:
        manager.delete_profile(profile.id)


if __name__ == "__main__":
    main()
