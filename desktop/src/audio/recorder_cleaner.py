"""
Real-time Recorder & Cleaner

Records audio from microphone, applies semantic noise suppression in real-time,
and saves the cleaned audio to a WAV file.

Usage:
    python -m desktop.src.audio.recorder_cleaner --duration 10 --suppress typing
"""

import argparse
import logging
import time
import sys
from pathlib import Path
import queue
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from desktop.src.profiles import ProfileManager, ControlEngine, ControlMode

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Record and clean audio in real-time")
    parser.add_argument("--duration", "-d", type=int, default=10, help="Recording duration in seconds")
    parser.add_argument("--suppress", "-s", type=str, default="typing", help="Categories to suppress")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output filename (optional)")
    parser.add_argument("--threshold", "-t", type=float, default=0.03, help="Detection threshold")
    
    args = parser.parse_args()
    
    # Setup output path
    samples_dir = project_root / "samples" / "processed"
    samples_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = args.output if args.output else f"recording_{timestamp}_cleaned.wav"
    output_path = samples_dir / filename
    
    # Setup Engine
    logger.info("Initializing engine...")
    manager = ProfileManager()
    
    # Create temp profile
    suppressions = {cat.strip(): True for cat in args.suppress.split(",")}
    profile = manager.create_profile(
        name="Recorder Temp",
        description="Temp recording profile",
        suppressions=suppressions
    )
    
    engine = ControlEngine(profile_manager=manager)
    engine.set_profile(profile)
    engine.set_mode(ControlMode.MANUAL)
    
    # ⚠️ OVERRIDE THRESHOLD
    # Force the threshold for the suppressed categories directly in the suppressor's mapping
    # -1.0 means FORCE SUPPRESSION (bypass detection)
    if hasattr(engine, 'suppressor'): # Trigger lazy load
        _ = engine.suppressor 
        for cat in suppressions.keys():
            if cat in engine.suppressor.category_map:
                logger.info(f"Forcing suppression for '{cat}' (Threshold: -1.0)")
                engine.suppressor.category_map[cat]['detection_threshold'] = -1.0
    
    # Audio buffers
    q = queue.Queue()
    sample_rate = 44100
    channels = 1 
    
    # Rolling buffer for context (Waveformer needs context to work!)
    # We keep 1.0s of history but only output the new 0.1s chunk
    context_duration = 1.0 
    context_size = int(sample_rate * context_duration)
    rolling_buffer = np.zeros(context_size, dtype=np.float32)
    
    def audio_callback(indata, frames, time, status):
        
        # ... (callback remains same)
        if status:
            logger.warning(f"Callback status: {status}")
        q.put(indata.copy())

    recorded_frames = []
    recorded_noise = []
    recorded_original = []
    
    logger.info(f"🎤 Recording for {args.duration}s...")
    logger.info(f"Suppressing: {args.suppress}")
    logger.info("Press Ctrl+C to stop early")
    
    try:
        # Detect device channels
        try:
            dev = sd.query_devices(kind='input')
            input_channels = dev['max_input_channels']
        except:
            input_channels = 1

        with sd.InputStream(samplerate=sample_rate, channels=input_channels, callback=audio_callback):
            start_time = time.time()
            while time.time() - start_time < args.duration:
                try:
                    # Get chunk
                    raw_chunk = q.get(timeout=1.0)
                    
                    # Convert to mono
                    if raw_chunk.shape[1] > 1:
                        mono_chunk = raw_chunk.mean(axis=1)
                    else:
                        mono_chunk = raw_chunk.flatten()
                    
                    chunk_len = len(mono_chunk)
                    
                    # Update rolling buffer
                    # Shift left by chunk_len
                    rolling_buffer = np.roll(rolling_buffer, -chunk_len)
                    # Overwrite end with new data
                    rolling_buffer[-chunk_len:] = mono_chunk
                    
                    # Process the FULL buffer to get context
                    # Bypass ControlEngine and call suppressor directly to use aggressiveness
                    targets = list(engine.current_profile.suppressions.keys()) if engine.current_profile else []
                    if targets:
                        clean_full_buffer = engine.suppressor.suppress(
                            audio=rolling_buffer,
                            sample_rate=sample_rate,
                            suppress_categories=targets,
                            detection_threshold=-1.0,  # Force mode
                            safety_check=False,  # Already verified
                            aggressiveness=1.5  # AGGRESSIVE SUPPRESSION
                        )
                    else:
                        clean_full_buffer = rolling_buffer
                    
                    # Extract only the NEW part (the last chunk_len samples)
                    clean_chunk = clean_full_buffer[-chunk_len:]
                    
                    # Store the ORIGINAL chunk (before suppression) for comparison
                    original_chunk = mono_chunk.copy()  # This is the raw input
                    
                    recorded_frames.append(clean_chunk)
                    
                    # DEBUG data collection
                    # Calculate what was REMOVED (original - clean)
                    # We need to use the ORIGINAL chunk, not rolling_buffer which may contain old data
                    noise_chunk = original_chunk - clean_chunk
                    recorded_noise.append(noise_chunk)
                    recorded_original.append(original_chunk)

                    
                    # Log if significant suppression
                    if np.max(np.abs(noise_chunk)) > 0.05:
                         # logger.debug(f"Suppressed amplitude: {np.max(np.abs(noise_chunk)):.3f}")
                         pass
                        
                except queue.Empty:
                    pass
                except KeyboardInterrupt:
                    break
                    
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        # Save file
        if recorded_frames:
            logger.info("Saving audio...")
            
            # Save Clean
            audio_data = np.concatenate(recorded_frames)
            sf.write(str(output_path), audio_data, sample_rate)
            logger.info(f"✅ Saved clean audio to: {output_path}")
            
            # Save Noise (what was removed)
            noise_data = np.concatenate(recorded_noise)
            noise_path = str(output_path).replace(".wav", "_noise.wav")
            sf.write(noise_path, noise_data, sample_rate)
            logger.info(f"🐛 Saved extracted noise to: {noise_path}")
            
            # Save Original (raw input)
            orig_data = np.concatenate(recorded_original)
            orig_path = str(output_path).replace(".wav", "_original.wav")
            sf.write(orig_path, orig_data, sample_rate)
            logger.info(f"🎤 Saved original mic input to: {orig_path}")
            
        manager.delete_profile(profile.id)

if __name__ == "__main__":
    main()
