"""
Real-time Microphone Noise Suppression Demo.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

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

from ai.scripts.demos.commons import setup_demo_logging, mono_from_stereo
from ai.ai_runtime.profiles import ControlEngine, ControlMode
from ai.ai_runtime.utils.codecsep import (
    add_codecsep_runtime_arguments,
    build_codecsep_call_kwargs_from_args,
)

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
        self.separator_backend = "waveformer"
        self.masking_method = "wiener_dd"
        self.codecsep_checkpoint_path = None
        self.codecsep_device = None
        self.codecsep_call_kwargs = {}
        self.running = False

    def apply_runtime_overrides(self) -> None:
        profile = self.engine.current_profile
        if profile is None:
            return
        suppression_params = dict(profile.suppression_params or {})
        suppression_params.update(
            {
                "separator_backend": self.separator_backend,
                "masking_method": self.masking_method,
                "codecsep_checkpoint_path": self.codecsep_checkpoint_path,
                "codecsep_device": self.codecsep_device,
                **self.codecsep_call_kwargs,
            },
        )
        profile.suppression_params = suppression_params

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
                    separator_backend=self.separator_backend,
                    masking_method=self.masking_method,
                    codecsep_checkpoint_path=self.codecsep_checkpoint_path,
                    codecsep_device=self.codecsep_device,
                    **self.codecsep_call_kwargs,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Real-time mic noise suppression")
    parser.add_argument("--profile", "-p", default="default-focus")
    parser.add_argument("--duration", "-d", type=int, default=None)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=int, default=None)
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

    if args.list_devices:
        print(sd.query_devices())
        return
    if args.separator_backend in {"audiosep_hive15cat", "codecsep_dnrv2_15cat"}:
        parser.error(
            f"{args.separator_backend} is not supported in demo_realtime.py because this demo runs "
            "suppression directly inside the audio callback. Use ai.ai_runtime.audio.recorder_cleaner "
            "for buffered live support."
        )

    suppressor = RealtimeSuppressor(profile_id=args.profile, sample_rate=44100)
    suppressor.suppress_all = args.suppress_all
    suppressor.universal_prompts = (
        [p.strip() for p in args.audiosep_prompt.split(",")] if args.audiosep_prompt else []
    )
    suppressor.separator_backend = args.separator_backend
    suppressor.masking_method = args.masking_method
    suppressor.codecsep_checkpoint_path = args.codecsep_checkpoint
    suppressor.codecsep_device = args.codecsep_device
    suppressor.codecsep_call_kwargs = build_codecsep_call_kwargs_from_args(args)
    suppressor.apply_runtime_overrides()
    suppressor.start(device=args.device, duration_seconds=args.duration)


if __name__ == "__main__":
    main()
