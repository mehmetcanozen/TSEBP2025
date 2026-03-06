"""
Batch Audio Processor - Offline Semantic Noise Suppression

Process audio files offline with semantic-aware noise suppression.
Useful for cleaning recorded audio, podcasts, or conference recordings.

Usage:
    python -m ai.ai_runtime.batch.batch_processor --input noisy.wav --suppress typing,wind --output clean.wav
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np
import soundfile as sf
from tqdm import tqdm

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ai.ai_runtime.suppression import SemanticSuppressor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process audio files with semantic noise suppression."""

    def __init__(self, suppressor: Optional[SemanticSuppressor] = None):
        self.suppressor = suppressor or SemanticSuppressor()

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        suppress_categories: List[str],
        chunk_size_seconds: float = 10.0,
        detection_threshold: float = 0.5,
        aggressiveness: float = 1.5,
        suppress_all: bool = False,
        universal_prompts: List[str] = None,
        output_noise: bool = False,
    ) -> dict:
        logger.info("Processing: %s", input_path)
        logger.info("Suppressing: %s", ", ".join(suppress_categories))

        audio, sample_rate = sf.read(input_path, dtype="float32")
        logger.info("Loaded audio: %s, %s Hz", audio.shape, sample_rate)

        chunk_size = int(chunk_size_seconds * sample_rate)
        num_chunks = (len(audio) + chunk_size - 1) // chunk_size
        cleaned_chunks = []
        noise_chunks = []

        with tqdm(total=num_chunks, desc="Processing chunks") as pbar:
            for i in range(0, len(audio), chunk_size):
                chunk = audio[i : i + chunk_size]

                if chunk.ndim == 2:
                    mono_chunk = chunk.mean(axis=1)
                    clean_mono = self.suppressor.suppress(
                        audio=mono_chunk,
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                        aggressiveness=aggressiveness,
                        suppress_all=suppress_all,
                        universal_prompts=universal_prompts or [],
                    )
                    eps = 1e-4
                    ratio = np.ones_like(mono_chunk, dtype=mono_chunk.dtype)
                    np.divide(clean_mono, mono_chunk, out=ratio, where=np.abs(mono_chunk) > eps)
                    ratio = np.clip(ratio, 0.1, 10.0)
                    clean_chunk = chunk * ratio[:, np.newaxis]
                else:
                    clean_chunk = self.suppressor.suppress(
                        audio=chunk,
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                        aggressiveness=aggressiveness,
                        suppress_all=suppress_all,
                        universal_prompts=universal_prompts or [],
                    )

                cleaned_chunks.append(clean_chunk)
                if output_noise:
                    noise_chunks.append(chunk - clean_chunk)
                pbar.update(1)

        cleaned_audio = np.concatenate(cleaned_chunks, axis=0)
        noise_audio = np.concatenate(noise_chunks, axis=0) if output_noise else None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, cleaned_audio, sample_rate)
        logger.info("Saved cleaned audio: %s", output_path)

        original_rms = np.sqrt(np.mean(audio**2))
        cleaned_rms = np.sqrt(np.mean(cleaned_audio**2))
        return {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "sample_rate": sample_rate,
            "duration_seconds": len(audio) / sample_rate,
            "original_rms": float(original_rms),
            "cleaned_rms": float(cleaned_rms),
            "rms_reduction_db": float(20 * np.log10(cleaned_rms / (original_rms + 1e-8))),
            "suppressed_categories": suppress_categories,
            "noise_audio": noise_audio,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch audio noise suppression")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input audio file (WAV, FLAC, etc.)")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output file path")
    parser.add_argument(
        "--suppress",
        "-s",
        type=str,
        required=False,
        help=(
            "Comma-separated list of categories to suppress (e.g., typing,wind,traffic). "
            "Optional if using --suppress-all or --universal instead, but at least one of "
            "--suppress, --suppress-all, or --universal must be provided."
        ),
    )
    parser.add_argument("--threshold", "-t", type=float, default=0.5, help="Detection confidence threshold (0.0-1.0)")
    parser.add_argument("--aggressiveness", "-a", type=float, default=1.5, help="Suppression aggressiveness (1.0-2.0)")
    parser.add_argument(
        "--suppress-all",
        action="store_true",
        help="Use universal speech enhancement (DeepFilterNet) instead of semantic extraction",
    )
    parser.add_argument(
        "--universal",
        "-u",
        type=str,
        default=None,
        help="Phase 3: Open-vocabulary text prompts for exact sound extraction (e.g., 'typing, dog barking, wind')",
    )
    parser.add_argument("--chunk-size", type=float, default=10.0, help="Process audio in chunks of N seconds")
    parser.add_argument("--output-noise", action="store_true", help="Save extracted noise to a separate file")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging")

    args = parser.parse_args()
    if not any([args.suppress, args.suppress_all, args.universal]):
        parser.print_help()
        print("\nERROR: You must specify at least one suppression mode: --suppress, --suppress-all, or --universal")
        sys.exit(1)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    suppress_categories = [cat.strip() for cat in args.suppress.split(",")] if args.suppress else []
    universal_prompts = [p.strip() for p in args.universal.split(",")] if args.universal else []

    processor = BatchProcessor()
    stats = processor.process_file(
        input_path=args.input,
        output_path=args.output,
        suppress_categories=suppress_categories,
        chunk_size_seconds=args.chunk_size,
        detection_threshold=args.threshold,
        aggressiveness=args.aggressiveness,
        suppress_all=args.suppress_all,
        universal_prompts=universal_prompts,
        output_noise=args.output_noise,
    )

    print("\n=== Processing Complete ===")
    print(f"Input: {stats['input_file']}")
    print(f"Output: {stats['output_file']}")
    if args.output_noise:
        noise_path = str(args.output).replace(".wav", "_noise.wav")
        sf.write(noise_path, stats["noise_audio"], stats["sample_rate"])
        print(f"Noise Output: {noise_path}")
    print(f"Duration: {stats['duration_seconds']:.2f}s")
    print(f"RMS Reduction: {stats['rms_reduction_db']:.2f} dB")
    print(f"Suppressed: {', '.join(stats['suppressed_categories'])}")


if __name__ == "__main__":
    main()
