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
    ) -> dict:
        """
        Process an audio file with semantic suppression.
        
        Args:
            input_path: Path to input WAV/FLAC file
            output_path: Path to save cleaned audio
            suppress_categories: List of categories to suppress
            chunk_size_seconds: Process audio in chunks (for memory efficiency)
            detection_threshold: Confidence threshold for detection
        
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
                    )
                    # Apply same ratio to stereo channels
                    ratio = clean_mono / (mono_chunk + 1e-8)
                    clean_chunk = chunk * ratio[:, np.newaxis]
                else:
                    clean_chunk = self.suppressor.suppress(
                        audio=chunk,
                        sample_rate=sample_rate,
                        suppress_categories=suppress_categories,
                        detection_threshold=detection_threshold,
                    )
                
                cleaned_chunks.append(clean_chunk)
                pbar.update(1)

        # Concatenate chunks
        cleaned_audio = np.concatenate(cleaned_chunks, axis=0)

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
        required=True,
        help="Comma-separated list of categories to suppress (e.g., typing,wind,traffic)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.5,
        help="Detection confidence threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--chunk-size",
        type=float,
        default=10.0,
        help="Process audio in chunks of N seconds (for memory efficiency)"
    )

    args = parser.parse_args()

    # Parse suppression categories
    suppress_categories = [cat.strip() for cat in args.suppress.split(",")]

    # Initialize processor
    processor = BatchProcessor()

    # Process file
    stats = processor.process_file(
        input_path=args.input,
        output_path=args.output,
        suppress_categories=suppress_categories,
        chunk_size_seconds=args.chunk_size,
        detection_threshold=args.threshold,
    )

    # Print summary
    print("\n=== Processing Complete ===")
    print(f"Input: {stats['input_file']}")
    print(f"Output: {stats['output_file']}")
    print(f"Duration: {stats['duration_seconds']:.2f}s")
    print(f"RMS Reduction: {stats['rms_reduction_db']:.2f} dB")
    print(f"Suppressed: {', '.join(stats['suppressed_categories'])}")


if __name__ == "__main__":
    main()
