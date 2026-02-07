"""
Show ALL YAMNet Detections - See what YAMNet actually hears

This will show you the top 5 sounds YAMNet detects in real-time.
Use this to find out what class your keyboard is detected as.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sounddevice as sd
import tensorflow_hub as hub

# Add project root
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

print("Loading YAMNet model...")
model = hub.load('https://tfhub.dev/google/yamnet/1')

# Load class names
class_map_path = model.class_map_path().numpy().decode('utf-8')
class_names = list(pd.read_csv(class_map_path)['display_name'])

print(f"Loaded {len(class_names)} YAMNet classes\n")
print("="*60)
print("🎤 LISTENING TO YOUR MIC - TYPE ON KEYBOARD NOW!")
print("="*60)
print("Showing top 5 detected sounds every 0.5 seconds...\n")

duration = 30  # seconds
sample_rate = 16000  # YAMNet expects 16kHz

def audio_callback(indata, frames, time_info, status):
    """Process audio and show detections."""
    if status:
        print(f"Status: {status}")
    
    try:
        # Convert to mono float32
        if indata.shape[1] > 1:
            audio = indata.mean(axis=1)
        else:
            audio = indata[:, 0]
        
        # Run YAMNet
        scores, embeddings, spectrogram = model(audio)
        
        # Get mean scores across all frames
        mean_scores = scores.numpy().mean(axis=0)
        
        # Get top 5
        top5_idx = np.argsort(mean_scores)[-5:][::-1]
        
        # Display
        print(f"\r⏱️  {remaining}s | Top 5 sounds:")
        for idx in top5_idx:
            score = mean_scores[idx]
            if score > 0.01:  # Only show if > 1%
                print(f"  [{idx:3d}] {class_names[idx]:30s} = {score:.3f}")
        print()
        
    except Exception as e:
        print(f"Error: {e}")


# Start recording
try:
    print(f"Recording for {duration} seconds...")
    print("👉 TYPE AGGRESSIVELY ON YOUR KEYBOARD\n")
    
    with sd.InputStream(
        samplerate=sample_rate,
        blocksize=int(sample_rate * 0.5),  # 0.5 second chunks
        channels=1,
        dtype='float32',
        callback=audio_callback
    ):
        for remaining in range(duration, 0, -1):
            time.sleep(1)
    
    print("\n✅ Done! Check the output above to see what class your keyboard is.")
    print("\nIf you see 'Typing' or 'Computer_keyboard' or similar, note the [index number]")
    print("Then update shared/mappings/yamnet_to_waveformer.yaml with the correct index!")

except KeyboardInterrupt:
    print("\n\nStopped by user")
except Exception as e:
    print(f"\nError: {e}")
