"""
Batch Audio Processor - Offline Semantic Noise Suppression

Process audio files offline with semantic-aware noise suppression.
Useful for cleaning recorded audio, podcasts, or conference recordings.

Usage:
    python batch_processor.py --input noisy.wav --suppress typing,wind --output clean.wav
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

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from desktop.src.audio.semantic_suppressor import SemanticSuppressor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process audio files with semantic noise suppression."""

    def __init__(self, suppressor: Optional[SemanticSuppressor] = None):
        """
        Initialize batch processor.
        
        Args:
            suppressor: Optional pre-initialized SemanticSuppressor instance
        """
        self.suppressor = suppressor or SemanticSuppressor()

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        suppress_categories: List[str],
        chunk_size_seconds: float = 10.0,
        detection_threshold: float = 0.5,
        suppress_all: bool = False,
        universal_prompts: List[str] = None,
        output_noise: bool = False,
    ) -> dict:
        """
        Process an audio file with semantic suppression.
        
        Args:
            input_path: Path to input WAV/FLAC file
            output_path: Path to save cleaned audio
            suppress_categories: List of categories to suppress
            chunk_size_seconds: Process audio in chunks (for memory efficiency)
            detection_threshold: Confidence threshold for detection
            suppress_all: If True, bypass categories and use DeepFilterNet
            universal_prompts: If provided, bypasses YAMNet/Waveformer and uses open-vocabulary text prompts
            output_noise: If True, also collect noise stem for optional saving
        
        Returns:
            dict with processing statistics
        """
        logger.info(f"Processing: {input_path}")
        logger.info(f"Suppressing: {', '.join(suppress_categories)}")

        # Load audio file
        audio, sample_rate = sf.read(input_path, dtype='float32')
        logger.info(f"Loaded audio: {audio.shape}, {sample_rate} Hz")

        # Process in chunks for memory efficiency
        chunk_size = int(chunk_size_seconds * sample_rate)
        num_chunks = (len(audio) + chunk_size - 1) // chunk_size
        
        cleaned_chunks = []
        noise_chunks = []
        
        with tqdm(total=num_chunks, desc="Processing chunks") as pbar:
            for i in range(0, len(audio), chunk_size):
                chunk = audio[i:i+chunk_size]
                
                # Handle stereo: process each channel separately or convert to mono
                if chunk.ndim == 2:
                    # Process mono version for detection, apply to stereo
                    mono_chunk = chunk.mean(axis=1)
                    clean_mono = self.suppressor.suppress(
                        audio=mono_chunk,
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                        suppress_all=suppress_all,
                        universal_prompts=universal_prompts or [],
                    )
                    # Apply same ratio to stereo channels using a numerically stable, clipped gain
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
                        suppress_all=suppress_all,
                        universal_prompts=universal_prompts or [],
                    )
                
                cleaned_chunks.append(clean_chunk)
                if output_noise:
                    noise_chunks.append(chunk - clean_chunk)
                pbar.update(1)

        # Concatenate chunks
        cleaned_audio = np.concatenate(cleaned_chunks, axis=0)
        noise_audio = np.concatenate(noise_chunks, axis=0) if output_noise else None

        # Save output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, cleaned_audio, sample_rate)
        logger.info(f"Saved cleaned audio: {output_path}")

        # Calculate statistics
        original_rms = np.sqrt(np.mean(audio**2))
        cleaned_rms = np.sqrt(np.mean(cleaned_audio**2))
        
        stats = {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "sample_rate": sample_rate,
            "duration_seconds": len(audio) / sample_rate,
            "original_rms": float(original_rms),
            "cleaned_rms": float(cleaned_rms),
            "rms_reduction_db": float(20 * np.log10(cleaned_rms / (original_rms + 1e-8))),
            "suppressed_categories": suppress_categories,
            "noise_audio": noise_audio,  # None unless output_noise=True
        }

        return stats


def main():
    parser = argparse.ArgumentParser(description="Batch audio noise suppression")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Input audio file (WAV, FLAC, etc.)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        required=True,
        help="Output file path"
    )
    parser.add_argument(
        "--suppress", "-s",
        type=str,
        required=False,
        help="Comma-separated list of categories to suppress (e.g., typing,wind,traffic)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.5,
        help="Detection confidence threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--suppress-all",
        action="store_true",
        help="Use universal speech enhancement (DeepFilterNet) instead of semantic extraction"
    )
    parser.add_argument(
        "--universal", "-u",
        type=str,
        default=None,
        help="Phase 3: Open-vocabulary text prompts for exact sound extraction (e.g., 'typing, dog barking, wind')"
    )
    parser.add_argument(
        "--chunk-size",
        type=float,
        default=10.0,
        help="Process audio in chunks of N seconds (for memory efficiency)"
    )
    parser.add_argument(
        "--output-noise",
        action="store_true",
        help="Save the extracted noise to a separate file for debugging"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG-level logging"
    )

    args = parser.parse_args()

    if not any([args.suppress, args.suppress_all, args.universal]):
        parser.print_help()
        print("\nERROR: You must specify at least one suppression mode: --suppress, --suppress-all, or --universal")
        sys.exit(1)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse suppression categories
    suppress_categories = [cat.strip() for cat in args.suppress.split(",")] if args.suppress else []
    universal_prompts = [p.strip() for p in args.universal.split(",")] if args.universal else []

    # Initialize processor
    processor = BatchProcessor()

    # Process file
    stats = processor.process_file(
        input_path=args.input,
        output_path=args.output,
        suppress_categories=suppress_categories,
        chunk_size_seconds=args.chunk_size,
        detection_threshold=args.threshold,
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
