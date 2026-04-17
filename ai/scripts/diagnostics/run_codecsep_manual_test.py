"""
Run the AI runtime CodecSep separator on a local audio file and save stems.

Example:
    python ai/scripts/diagnostics/run_codecsep_manual_test.py ^
        --input ai/data/audio/raw/speech_barking.wav ^
        --sfx-prompt "dog barking, animal"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from ai.ai_runtime.separation.codecsep_separator import CodecSepSeparator
from ai.ai_runtime.utils.paths import resolve_codecsep_checkpoint_path


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if isinstance(audio, np.ndarray) and audio.ndim == 2:
        # soundfile returns (samples, channels)
        pass
    return audio, sample_rate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual CodecSep runtime separation test.")
    parser.add_argument("--input", type=Path, required=True, help="Input wav path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ai/models/temp_export/codecsep_manual_test"),
        help="Directory to write separated stems.",
    )
    parser.add_argument(
        "--sfx-prompt",
        type=str,
        default="dog barking, animal",
        help="Prompt override for the SFX stem.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Optional device override, e.g. cuda or cpu.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Optional CodecSep run directory or checkpoint override.",
    )
    parser.add_argument(
        "--max-length",
        type=float,
        default=10.0,
        help="Maximum seconds to process, matching the vendored single-file demo default.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = args.input.resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input audio not found: {input_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    audio, sample_rate = _load_audio(input_path)
    max_samples = int(args.max_length * sample_rate)
    if max_samples > 0 and audio.shape[0] > max_samples:
        audio = audio[:max_samples] if audio.ndim == 1 else audio[:max_samples, :]
        print(f"Truncated input to {args.max_length:.1f}s ({max_samples} samples)")
    separator = CodecSepSeparator(
        checkpoint_path=args.checkpoint,
        device=args.device,
    )
    stems = separator.separate_stems(
        audio,
        sample_rate=sample_rate,
        stems=("speech", "music", "sfx"),
        prompt_overrides={"sfx": [args.sfx_prompt]},
    )

    stem_name = input_path.stem
    for name, stem_audio in stems.items():
        out_path = output_dir / f"{stem_name}_sep_{name}.wav"
        sf.write(str(out_path), np.asarray(stem_audio, dtype=np.float32), sample_rate)
        print(f"Saved {name}: {out_path}")

    print(f"Checkpoint source: {separator.checkpoint_path}")
    print(f"Resolved checkpoint: {resolve_codecsep_checkpoint_path(args.checkpoint)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
