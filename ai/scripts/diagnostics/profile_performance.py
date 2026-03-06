"""
Profile performance of real-time noise suppression system.
Run this script to identify bottlenecks and measure optimization impact.
"""

import sys
from pathlib import Path

import soundfile as sf

_root = Path(__file__).resolve().parents[3]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.profiles.profiler import get_profiler
from ai.ai_runtime.utils.paths import get_data_audio_path


def profile_suppression(audio_file: str, iterations: int = 10):
    print(f"Loading audio from: {audio_file}")
    audio, sample_rate = sf.read(audio_file)
    if audio.ndim > 1:
        audio = audio[:, 0]

    print(f"Audio loaded: {len(audio)} samples @ {sample_rate} Hz ({len(audio)/sample_rate:.2f}s)")
    print("\nInitializing SemanticSuppressor...")
    suppressor = SemanticSuppressor()

    profiler = get_profiler()
    profiler.enabled = True
    profiler.reset()

    print(f"\nRunning suppression {iterations} times...")
    for i in range(iterations):
        print(f"  Iteration {i+1}/{iterations}...", end="\r")
        suppressor.suppress(
            audio=audio,
            sample_rate=sample_rate,
            suppress_categories=["typing", "wind"],
            detection_threshold=-1.0,
            aggressiveness=1.5,
        )

    print("\n\nProfiling Results:")
    print(profiler.report(sort_by="mean_ms"))

    output_path = Path(__file__).parent / "profile_results.json"
    profiler.export_json(str(output_path))
    print(f"\nDetailed results exported to: {output_path}")

    total_audio_duration = (len(audio) / sample_rate) * iterations
    print(f"\nTotal audio processed: {total_audio_duration:.2f}s")

    stats = profiler.get_stats()
    if "yamnet_detection" in stats:
        ops = ["yamnet_detection", "input_normalization", "waveformer_separation", "aggressive_subtraction"]
        total_per_iteration = sum(stats.get(op, {}).get("mean_ms", 0) for op in ops)
        print(f"Average processing time per iteration: {total_per_iteration:.2f}ms")
        print(f"Real-time factor: {(total_per_iteration / (len(audio)/sample_rate*1000)):.2f}x")
        print("  (values <1.0 mean faster than real-time)")


if __name__ == "__main__":
    test_files = [
        get_data_audio_path("raw") / "keyboard.wav",
        get_data_audio_path("processed") / "recording_original.wav",
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
