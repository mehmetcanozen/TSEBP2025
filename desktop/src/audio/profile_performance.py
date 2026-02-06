"""
Profile performance of real-time noise suppression system.
Run this script to identify bottlenecks and measure optimization impact.
"""

import numpy as np
import soundfile as sf
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from desktop.src.audio.semantic_suppressor import SemanticSuppressor
from desktop.src.audio.profiler import get_profiler


def profile_suppression(audio_file: str, iterations: int = 10):
    """
    Profile suppression performance on a test audio file.
    
    Args:
        audio_file: Path to test audio file
        iterations: Number of times to run suppression for statistical significance
    """
    print(f"Loading audio from: {audio_file}")
    audio, sample_rate = sf.read(audio_file)
    
    # Convert to mono if stereo
    if audio.ndim > 1:
        audio = audio[:, 0]
    
    print(f"Audio loaded: {len(audio)} samples @ {sample_rate} Hz ({len(audio)/sample_rate:.2f}s)")
    
    # Initialize suppressor
    print("\nInitializing SemanticSuppressor...")
    suppressor = SemanticSuppressor()
    
    # Get profiler
    profiler = get_profiler()
    profiler.reset()  # Clear any previous data
    
    # Run suppression multiple times
    print(f"\nRunning suppression {iterations} times...")
    for i in range(iterations):
        print(f"  Iteration {i+1}/{iterations}...", end='\r')
        
        clean_audio = suppressor.suppress(
            audio=audio,
            sample_rate=sample_rate,
            suppress_categories=["typing", "wind"],
            detection_threshold=-1.0,  # Force mode
            aggressiveness=1.5
        )
    
    print("\n\nProfiling Results:")
    print(profiler.report(sort_by='mean_ms'))
    
    # Export to JSON for analysis
    output_path = Path(__file__).parent / "profile_results.json"
    profiler.export_json(str(output_path))
    print(f"\nDetailed results exported to: {output_path}")
    
    # Calculate throughput
    total_audio_duration = (len(audio) / sample_rate) * iterations
    print(f"\nTotal audio processed: {total_audio_duration:.2f}s")
    
    # Get total processing time
    stats = profiler.get_stats()
    if 'yamnet_detection' in stats:
        # Sum all operation means to get per-iteration time
        ops = ['yamnet_detection', 'input_normalization', 'waveformer_separation', 'aggressive_subtraction']
        total_per_iteration = sum(stats.get(op, {}).get('mean_ms', 0) for op in ops)
        
        print(f"Average processing time per iteration: {total_per_iteration:.2f}ms")
        print(f"Real-time factor: {(total_per_iteration / (len(audio)/sample_rate*1000)):.2f}x")
        print(f"  (values <1.0 mean faster than real-time)")


if __name__ == "__main__":
    # Use keyboard sample if available, otherwise use any WAV in samples/
    test_files = [
        Path(__file__).parents[4] / "samples" / "audio" / "keyboard.wav",
        Path(__file__).parents[4] / "samples" / "processed" / "recording_original.wav",
    ]
    
    test_file = None
    for f in test_files:
        if f.exists():
            test_file = str(f)
            break
    
    if not test_file:
        print("ERROR: No test audio file found. Please provide a WAV file.")
        print("  Looking for:")
        for f in test_files:
            print(f"    - {f}")
        sys.exit(1)
    
    profile_suppression(test_file, iterations=10)
