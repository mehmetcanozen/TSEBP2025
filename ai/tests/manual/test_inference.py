"""Manual smoke helpers for inference stack.

This module is kept under `ai/tests` for organization, but it is not part of
the default automated pytest suite.
"""

from __future__ import annotations

__test__ = False

import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import tensorflow as tf
import tensorflow_hub as hub
from scipy import signal

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "ai" / "tests" / "manual"
WAVEFORMER_DIR = ROOT / "ai" / "models" / "Waveformer"
CHECKPOINTS_DIR = ROOT / "ai" / "models" / "checkpoints"


def generate_test_audio(path: Path, sample_rate: int = 44100, seconds: float = 1.0) -> None:
    samples = int(sample_rate * seconds)
    waveform = np.random.normal(0, 0.05, size=(samples,)).astype(np.float32)
    sf.write(path, waveform, sample_rate)


def run_waveformer_test() -> None:
    input_wav = SCRIPTS_DIR / "sample_noise.wav"
    output_wav = SCRIPTS_DIR / "sample_waveformer_out.wav"
    generate_test_audio(input_wav)
    if output_wav.exists():
        output_wav.unlink()

    cmd = [sys.executable, str(WAVEFORMER_DIR / "Waveformer.py"), str(input_wav), str(output_wav)]
    subprocess.run(cmd, cwd=WAVEFORMER_DIR, check=True)
    if not output_wav.exists():
        raise FileNotFoundError("Waveformer output not produced.")


def run_yamnet_test() -> None:
    yamnet_path = CHECKPOINTS_DIR / "yamnet_1.tar.gz"
    class_map_path = CHECKPOINTS_DIR / "yamnet_class_map.csv"
    if not class_map_path.exists():
        with class_map_path.open("w", newline="") as f:
            f.write("index,display_name\n0,silence\n")
    input_wav = SCRIPTS_DIR / "sample_noise.wav"

    if not input_wav.exists():
        generate_test_audio(input_wav, sample_rate=16000)

    waveform, sr = sf.read(input_wav)
    target_sr = 16000
    if sr != target_sr:
        waveform = signal.resample(waveform, int(len(waveform) * target_sr / sr))

    waveform = tf.convert_to_tensor(waveform, dtype=tf.float32)
    if len(waveform.shape) > 1:
        waveform = tf.reduce_mean(waveform, axis=1)

    try:
        yamnet_model = hub.load(str(yamnet_path))
    except Exception:
        yamnet_model = hub.load("https://tfhub.dev/google/yamnet/1")
    scores, _, _ = yamnet_model(waveform)
    scores_np = scores.numpy()
    top_class = int(np.argmax(np.mean(scores_np, axis=0)))

    with class_map_path.open(newline="") as f:
        reader = csv.DictReader(f)
        classes = [row["display_name"] for row in reader]
    _ = classes[top_class] if top_class < len(classes) else "unknown"


def main() -> None:
    run_waveformer_test()
    run_yamnet_test()


if __name__ == "__main__":
    main()
