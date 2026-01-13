"""
Quick CLI harness to exercise SemanticDetective end-to-end.

Usage (from repo root):
    python desktop/src/test_detective.py --seconds 3

Note: This is a demo script, not a pytest test module.
"""

from __future__ import annotations

# Prevent pytest from collecting this file as a test module
__test__ = False

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Ensure repo root and training package are importable when running as a script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))
TRAINING_DIR = REPO_ROOT / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.append(str(TRAINING_DIR))

try:
    import sounddevice as sd
except Exception as exc:  # pragma: no cover - runtime dependency
    print("sounddevice is required to run mic capture (--seconds):", exc, file=sys.stderr)
    sd = None

from training.models.semantic_detective import SemanticDetective


def record_audio(seconds: float, sample_rate: int) -> np.ndarray:
    if sd is None:
        raise RuntimeError("sounddevice not available; install it or use --wav for file testing.")
    print(f"Recording {seconds:.1f}s of audio at {sample_rate} Hz...")
    frames = int(seconds * sample_rate)
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    return audio.squeeze()


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    if not path.exists():
        raise FileNotFoundError(f"WAV file not found: {path}")
    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32, copy=False)
    return audio, sr


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic Detective sanity check.")
    parser.add_argument("--seconds", type=float, default=3.0, help="Capture duration in seconds.")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Capture sample rate.")
    parser.add_argument("--wav", type=str, help="Path to a WAV file for offline testing.")
    parser.add_argument(
        "--model-handle",
        type=str,
        help="Optional TFHub handle or local yamnet tarball path (e.g., models/checkpoints/yamnet_1.tar.gz).",
    )
    args = parser.parse_args()

    if args.wav:
        wav_path = Path(args.wav)
        audio, sr = load_wav(wav_path)
        print(f"Loaded WAV: {wav_path} (sr={sr}, samples={len(audio)})")
    else:
        audio = record_audio(args.seconds, args.sample_rate)
        sr = args.sample_rate

    detective = SemanticDetective(model_handle=args.model_handle) if args.model_handle else SemanticDetective()
    results = detective.classify(audio, sr)
    top = detective.get_top_detections(results["smoothed"], n=5)
    safety = detective.check_safety_override(results["states"])

    print("\nTop detections:")
    for name, score in top:
        print(f"- {name}: {score:.2f}")

    print("\nSafety override:", "TRIGGERED" if safety else "clear")


if __name__ == "__main__":
    main()
