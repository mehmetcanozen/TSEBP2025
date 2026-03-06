"""
Show ALL YAMNet Detections - See what YAMNet actually hears.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sounddevice as sd
import tensorflow_hub as hub

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

print("Loading YAMNet model...")
model = hub.load("https://tfhub.dev/google/yamnet/1")

class_map_path = model.class_map_path().numpy().decode("utf-8")
class_names = list(pd.read_csv(class_map_path)["display_name"])

print(f"Loaded {len(class_names)} YAMNet classes\n")
print("=" * 60)
print("LISTENING TO YOUR MIC - TYPE ON KEYBOARD NOW!")
print("=" * 60)
print("Showing top 5 detected sounds every 0.5 seconds...\n")

duration = 30
sample_rate = 16000


def audio_callback(indata, frames, time_info, status):
    if status:
        print(f"Status: {status}")
    try:
        if indata.shape[1] > 1:
            audio = indata.mean(axis=1)
        else:
            audio = indata[:, 0]

        scores, embeddings, spectrogram = model(audio)  # noqa: F841
        mean_scores = scores.numpy().mean(axis=0)
        top5_idx = np.argsort(mean_scores)[-5:][::-1]

        print(f"\r{remaining}s | Top 5 sounds:")
        for idx in top5_idx:
            score = mean_scores[idx]
            if score > 0.01:
                print(f"  [{idx:3d}] {class_names[idx]:30s} = {score:.3f}")
        print()
    except Exception as e:
        print(f"Error: {e}")


try:
    print(f"Recording for {duration} seconds...")
    with sd.InputStream(
        samplerate=sample_rate,
        blocksize=int(sample_rate * 0.5),
        channels=1,
        dtype="float32",
        callback=audio_callback,
    ):
        for remaining in range(duration, 0, -1):
            time.sleep(1)

    print("\nDone! Check the output above to see what class your keyboard is.")
    print("\nIf you see 'Typing' or 'Computer_keyboard' or similar, note the [index number]")
    print("Then update ai/ai_runtime/config/yamnet_to_waveformer.yaml with the correct index.")
except KeyboardInterrupt:
    print("\n\nStopped by user")
except Exception as e:
    print(f"\nError: {e}")
