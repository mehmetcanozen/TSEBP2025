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
    parser.add_argument("--aggressiveness", "-a", type=float, default=1.0, help="Suppression aggressiveness (1.0-2.0)")
    parser.add_argument("--suppress-all", action="store_true", help="Use DeepFilterNet to universally suppress all background noise")
    parser.add_argument("--universal", type=str, default=None, help="Phase 3: Open-vocabulary text prompts for exact sound extraction (e.g., 'typing, dog barking')")
    parser.add_argument("--device", type=int, default=None, help="Input device ID (use 'python -m sounddevice' to list)")
    
    args = parser.parse_args()
    
    # Setup output path
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = args.output if args.output else f"recording_{timestamp}_cleaned.wav"
    
    # If user provided a path, respect it (relative to current location)
    # Otherwise, default to samples/processed/
    if args.output and (Path(args.output).parent != Path(".")):
        output_path = Path(args.output).resolve()
    else:
        samples_dir = project_root / "samples" / "processed"
        samples_dir.mkdir(parents=True, exist_ok=True)
        output_path = samples_dir / filename
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
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
    
    if hasattr(engine, 'suppressor'): # Trigger lazy load
        _ = engine.suppressor 
        for cat in suppressions.keys():
            if cat in engine.suppressor.category_map:
                logger.info(f"Setting threshold for '{cat}' to {args.threshold}")
                engine.suppressor.category_map[cat]['detection_threshold'] = args.threshold
    
    # Audio buffers
    q = queue.Queue(maxsize=10) # Bounded queue to prevent memory growth
    sample_rate = 44100
    
    # Rolling buffer for context (Waveformer needs context to work!)
    # We keep 3.0s of history but only output the new 0.1s chunk
    context_duration = 3.0 
    context_size = int(sample_rate * context_duration)
    rolling_buffer = np.zeros(context_size, dtype=np.float32)
    
    def audio_callback(indata, frames, time, status):
        
        # ... (callback remains same)
        if status:
            logger.warning(f"Callback status: {status}")
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            logger.warning("Audio queue full, dropping frame")

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
        except Exception:
            input_channels = 1

        # CRITICAL FIX: Ensure blocksize is an exact multiple of the STFT hop_length (512)
        # to prevent phase misalignment across sliding windows! We use 8192 (~185ms).
        stft_aligned_blocksize = 8192
        
        if args.device is not None:
            logger.info(f"🎤 Using specified input device ID: {args.device}")
            
        with sd.InputStream(samplerate=sample_rate, device=args.device, channels=input_channels, blocksize=stft_aligned_blocksize, callback=audio_callback):
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
                    universal_targets = [p.strip() for p in args.universal.split(",")] if args.universal else []
                    
                    if targets or args.suppress_all or universal_targets:
                        clean_full_buffer = engine.suppressor.suppress(
                            audio=rolling_buffer,
                            sample_rate=sample_rate,
                            suppress_categories=targets,
                            detection_threshold=args.threshold,
                            aggressiveness=args.aggressiveness,
                            suppress_all=args.suppress_all,
                            universal_prompts=universal_targets
                        )
                    else:
                        clean_full_buffer = rolling_buffer
                    
                    # Extract only the NEW part (the last chunk_len samples)
                    # Offset into the buffer to allow lookahead
                    # Taking the middle chunk gives the model "future" context
                    lookahead_delay = 0.5 # seconds
                    offset = int(lookahead_delay * sample_rate)
                    
                    # Ensure we don't go out of bounds
                    end_idx = context_size - offset
                    start_idx = end_idx - chunk_len
                    
                    # Get the current clean chunk
                    raw_clean_chunk = clean_full_buffer[start_idx:end_idx]
                    
                    # Store the ORIGINAL chunk (aligned with suppression)
                    original_chunk = rolling_buffer[start_idx:end_idx].copy()
                    
                    # We need to cross-fade the boundary between the *previous* chunk 
                    # and the *current* chunk to eliminate clicking caused by STFT phase discontinuities.
                    crossfade_frames = int(0.005 * sample_rate) # 5ms crossfade
                    
                    if not hasattr(engine, '_prev_tail'):
                        # First chunk, no crossfade
                        clean_chunk = raw_clean_chunk.copy()
                        engine._prev_tail = clean_full_buffer[end_idx:end_idx+crossfade_frames].copy()
                    else:
                        clean_chunk = raw_clean_chunk.copy()
                        
                        # Apply linear crossfade at the start of the current chunk
                        # blending it with the overlapping tail of the previous full-buffer prediction
                        fade_in = np.linspace(0, 1, crossfade_frames)
                        fade_out = 1.0 - fade_in
                        
                        overlap_len = min(crossfade_frames, len(clean_chunk), len(engine._prev_tail))
                        
                        # Blend the start of the current chunk
                        clean_chunk[:overlap_len] = (
                            clean_chunk[:overlap_len] * fade_in[:overlap_len] +
                            engine._prev_tail[:overlap_len] * fade_out[:overlap_len]
                        )
                        
                        # Save the tail of this chunk's prediction for the NEXT chunk
                        # We take the frames immediately *after* end_idx in the full buffer
                        # Since we do lookahead, these frames exist in the buffer
                        engine._prev_tail = clean_full_buffer[end_idx:end_idx+crossfade_frames].copy()
                    
                    recorded_frames.append(clean_chunk)
                    
                    # DEBUG data collection
                    # Calculate what was REMOVED (original - clean)
                    # We need to use the ORIGINAL chunk, not rolling_buffer which may contain old data
                    noise_chunk = original_chunk - clean_chunk
                    recorded_noise.append(noise_chunk)
                    recorded_original.append(original_chunk)

                    
                    # Log if significant suppression
                    noise_peak = np.max(np.abs(noise_chunk))
                    if noise_peak > 0.001:
                         logger.info(f"Suppression active: peak amplitude removed = {noise_peak:.5f}")
                        
                except queue.Empty:
                    # No new audio data was available within the timeout; continue loop and try again.
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
