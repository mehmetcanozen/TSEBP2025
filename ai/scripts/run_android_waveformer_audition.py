"""Audition the Android-bundled Waveformer ONNX model from the command line."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.ai_runtime.separation.waveformer_onnx_stream import load_android_bundle, suppress_file


DEFAULT_BUNDLE_DIR = (
    PROJECT_ROOT
    / "mobile-part"
    / "android"
    / "app"
    / "build"
    / "generated"
    / "suppression-assets"
    / "suppression-model-bundle"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "ai" / "data" / "audio" / "processed"


@dataclass(frozen=True)
class AuditionCase:
    name: str
    input_path: Path
    target: str
    aggressiveness: float


DEFAULT_CASES = (
    AuditionCase(
        name="traffic_horn_car_horn",
        input_path=PROJECT_ROOT
        / "ai"
        / "data"
        / "audio"
        / "Sounds"
        / "manshaofficial-traffic-sound-111442.mp3",
        target="car_horn",
        aggressiveness=1.2,
    ),
    AuditionCase(
        name="speech_keyboard_computer_typing",
        input_path=PROJECT_ROOT / "ai" / "data" / "audio" / "raw" / "speech_keyboard.wav",
        target="computer_typing",
        aggressiveness=1.25,
    ),
    AuditionCase(
        name="speech_alarm_alarm_clock",
        input_path=PROJECT_ROOT / "ai" / "data" / "audio" / "raw" / "speech_alarm.wav",
        target="alarm_clock",
        aggressiveness=1.1,
    ),
    AuditionCase(
        name="keyboard_barking_dog",
        input_path=PROJECT_ROOT / "ai" / "data" / "audio" / "raw" / "keyboard_barking.wav",
        target="dog",
        aggressiveness=1.1,
    ),
    AuditionCase(
        name="keyboard_barking_computer_typing",
        input_path=PROJECT_ROOT / "ai" / "data" / "audio" / "raw" / "keyboard_barking.wav",
        target="computer_typing",
        aggressiveness=1.25,
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run listening tests against the exact Android-bundled Waveformer ONNX bundle.",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=DEFAULT_BUNDLE_DIR,
        help="Android generated suppression-model-bundle directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to ai/data/audio/processed/android_waveformer_audition_<timestamp>.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="NAME|INPUT|TARGET|AGGRESSIVENESS",
        help=(
            "Custom case. Aggressiveness is optional. "
            "When no cases are passed, the built-in traffic/keyboard/alarm/barking set is used."
        ),
    )
    parser.add_argument(
        "--write-noise",
        action="store_true",
        help="Also write extracted residual/noise WAVs for each case.",
    )
    return parser


def parse_cases(values: Iterable[str]) -> list[AuditionCase]:
    cases: list[AuditionCase] = []
    for value in values:
        parts = [part.strip() for part in value.split("|")]
        if len(parts) not in {3, 4}:
            raise SystemExit(
                "--case must be NAME|INPUT|TARGET or NAME|INPUT|TARGET|AGGRESSIVENESS"
            )
        name, input_path, target = parts[:3]
        aggressiveness = float(parts[3]) if len(parts) == 4 else 1.1
        cases.append(
            AuditionCase(
                name=safe_name(name),
                input_path=Path(input_path),
                target=target,
                aggressiveness=aggressiveness,
            )
        )
    return cases


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("_") or "case"


def default_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_ROOT / f"android_waveformer_audition_{timestamp}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bundle_dir = args.bundle_dir.resolve()
    if not (bundle_dir / "manifest.json").exists():
        raise SystemExit(
            f"Android bundle was not found at {bundle_dir}. "
            "Run: cd mobile-part\\android; .\\gradlew.bat :app:prepareBundledSuppressionModel"
        )

    package = load_android_bundle(bundle_dir)
    output_dir = (args.output_dir or default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = parse_cases(args.case) if args.case else list(DEFAULT_CASES)

    summary: dict[str, object] = {
        "bundle_dir": str(bundle_dir),
        "model_path": str(package.model_path),
        "sample_rate": package.sample_rate,
        "chunk_samples": package.chunk_samples,
        "mix_channels": package.mix_channels,
        "outputs": [],
    }

    for case in cases:
        input_path = case.input_path
        if not input_path.is_absolute():
            input_path = PROJECT_ROOT / input_path
        if not input_path.exists():
            raise SystemExit(f"Missing input audio for case {case.name}: {input_path}")

        output_wav = output_dir / f"{safe_name(case.name)}__suppress_{case.target}.wav"
        noise_wav = (
            output_dir / f"{safe_name(case.name)}__extracted_{case.target}.wav"
            if args.write_noise
            else None
        )
        stats = suppress_file(
            input_path=input_path,
            output_path=output_wav,
            noise_path=noise_wav,
            categories=[case.target],
            aggressiveness=case.aggressiveness,
            package=package,
            mode="android_live",
        )
        stats.pop("noise_audio", None)
        row = {
            "case": case.name,
            "input": str(input_path),
            "target": case.target,
            "aggressiveness": case.aggressiveness,
            "output_wav": str(output_wav),
            "noise_wav": str(noise_wav) if noise_wav is not None else None,
            **stats,
        }
        summary["outputs"].append(row)  # type: ignore[index]
        print(
            f"{case.name}: target={case.target} "
            f"rtf={stats.get('real_time_factor', 0.0):.3f} "
            f"rms_reduction_db={stats.get('rms_reduction_db', 0.0):.2f} "
            f"-> {output_wav}"
        )

    summary_path = output_dir / "android_waveformer_audition_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
