"""
Simple profiling script for semantic suppression - run from desktop/ directory
"""

import soundfile as sf
from pathlib import Path

from desktop.src.audio.semantic_suppressor import SemanticSuppressor
from desktop.src.audio.profiler import get_profiler


def main():
    profiler = get_profiler()
    profiler.enabled = True
    
    # Find test audio
    test_files = [
        Path("samples/audio/keyboard.wav"),
        Path("samples/processed/recording_original.wav"),
    ]
    
    test_file = None
    for f in test_files:
        if f.exists():
            test_file = str(f)
            break
    
    if not test_file:
        print("ERROR: No test audio found")
        return
    
    print(f"Loading: {test_file}")
    audio, sr = sf.read(test_file)
    if audio.ndim > 1:
        audio = audio[:, 0]
    print(f"Loaded: {len(audio)} samples @ {sr}Hz ({len(audio)/sr:.2f}s)")
    
    # Initialize
    print("\nInitializing suppressor...")
    suppressor = SemanticSuppressor()
    profiler = get_profiler()
    profiler.reset()
    
    # Profile 10 iterations
    iterations = 10
    print(f"\nRunning {iterations} iterations...")
    for i in range(iterations):
        suppressor.suppress(
            audio=audio,
            sample_rate=sr,
            suppress_categories=["typing", "wind"],
            detection_threshold=-1.0,
            aggressiveness=1.5
        )
    
    # Report
    print("\n" + "="*80)
    print(profiler.report())
    
    # Save results
    output = Path(__file__).parent / "src" / "audio" / "profile_results.json"
    profiler.export_json(str(output))
    print(f"\nResults saved to: {output}")


if __name__ == "__main__":
    main()
