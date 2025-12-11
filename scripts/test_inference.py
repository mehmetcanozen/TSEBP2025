import csv
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal
import tensorflow as tf
import tensorflow_hub as hub


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
WAVEFORMER_DIR = ROOT / "training" / "models" / "Waveformer"
CHECKPOINTS_DIR = ROOT / "models" / "checkpoints"


def generate_test_audio(path: Path, sample_rate: int = 44100, seconds: float = 1.0) -> None:
    """Generate a short white-noise waveform for quick smoke tests."""
    samples = int(sample_rate * seconds)
    waveform = np.random.normal(0, 0.05, size=(samples,)).astype(np.float32)
    sf.write(path, waveform, sample_rate)


def run_waveformer_test() -> None:
    """Run Waveformer CLI on the generated audio."""
    input_wav = SCRIPTS_DIR / "sample_noise.wav"
    output_wav = SCRIPTS_DIR / "sample_waveformer_out.wav"
    generate_test_audio(input_wav)
    if output_wav.exists():
        output_wav.unlink()

    cmd = [
        sys.executable,
        str(WAVEFORMER_DIR / "Waveformer.py"),
        str(input_wav),
        str(output_wav),
    ]
    print(f"[Waveformer] Running: {' '.join(cmd)} (cwd={WAVEFORMER_DIR})")
    subprocess.run(cmd, cwd=WAVEFORMER_DIR, check=True)
    if not output_wav.exists():
        raise FileNotFoundError("Waveformer output not produced.")
    print(f"[Waveformer] Success. Output written to {output_wav}")


def run_yamnet_test() -> None:
    """Load YAMNet from local TFHub archive and run inference."""
    yamnet_path = CHECKPOINTS_DIR / "yamnet_1.tar.gz"
    class_map_path = CHECKPOINTS_DIR / "yamnet_class_map.csv"
    input_wav = SCRIPTS_DIR / "sample_noise.wav"

    if not input_wav.exists():
        generate_test_audio(input_wav, sample_rate=16000)

    waveform, sr = sf.read(input_wav)
    target_sr = 16000
    if sr != target_sr:
        # Resample to 16 kHz expected by YAMNet.
        waveform = signal.resample(
            waveform, int(len(waveform) * target_sr / sr)
        )

    waveform = tf.convert_to_tensor(waveform, dtype=tf.float32)
    if len(waveform.shape) > 1:
        waveform = tf.reduce_mean(waveform, axis=1)

    try:
        yamnet_model = hub.load(str(yamnet_path))
    except Exception:
        print("[YAMNet] Local archive incompatible, falling back to TFHub.")
        yamnet_model = hub.load("https://tfhub.dev/google/yamnet/1")
    scores, embeddings, spectrogram = yamnet_model(waveform)
    scores_np = scores.numpy()
    top_class = int(np.argmax(np.mean(scores_np, axis=0)))

    with class_map_path.open(newline="") as f:
        reader = csv.DictReader(f)
        classes = [row["display_name"] for row in reader]

    label = classes[top_class] if top_class < len(classes) else "unknown"
    print(f"[YAMNet] Success. Top class: {label}")


def main() -> None:
    run_waveformer_test()
    run_yamnet_test()
    print("[Inference] All smoke tests completed.")


if __name__ == "__main__":
    main()

