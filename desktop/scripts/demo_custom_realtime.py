"""
Custom Real-time Suppression Demo

Suppress specific sounds from your microphone in real-time.
Perfect for suppressing keyboard noise during calls!
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from desktop.src.profiles import ProfileManager, ControlEngine, ControlMode

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_custom_profile(manager, suppress_categories):
    """Create a temporary custom profile."""
    suppressions = {cat: True for cat in suppress_categories}
    
    profile = manager.create_profile(
        name="Custom Realtime",
        description=f"Suppress: {', '.join(suppress_categories)}",
        suppressions=suppressions
    )
    
    return profile


def main():
    parser = argparse.ArgumentParser(description="Real-time mic noise suppression (custom categories)")
    parser.add_argument(
        "--suppress", "-s",
        type=str,
        default="typing",
        help="Comma-separated categories to suppress (e.g., typing,wind,traffic)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=10,
        help="Duration in seconds (default: 10)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.3,
        help="Detection threshold (default: 0.3)"
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="List available suppression categories"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List audio devices"
    )
    
    args = parser.parse_args()
    
    if args.list_categories:
        print("\nAvailable Suppression Categories:")
        print("  - typing       (keyboard/mouse sounds)")
        print("  - traffic      (cars, buses)")
        print("  - wind         (wind noise)")
        print("  - music        (musical instruments)")
        print("  - nature       (rain, animals)")
        print("  - appliances   (microwave, etc.)")
        print("  - misc         (applause, cough, etc.)")
        print("\nNOTE: 'siren' and 'alarm' cannot be suppressed (safety override)")
        print("\nExample: python demo_custom_realtime.py --suppress typing,wind")
        return
    
    if args.list_devices:
        print("\nAvailable Audio Devices:")
        print(sd.query_devices())
        return
    
    # Parse categories
    categories = [c.strip() for c in args.suppress.split(",")]
    
    logger.info("=== Custom Real-time Suppression ===")
    logger.info(f"Will suppress: {', '.join(categories)}")
    logger.info(f"Duration: {args.duration}s")
    logger.info("\nInitializing...")
    
    # Create custom profile
    manager = ProfileManager()
    profile = create_custom_profile(manager, categories)
    
    # Use the user-specified threshold
    # Note: In a real app we'd set this on the profile, but for now we'll rely on the default
    # or updated mapping file values. 
    # To truly force it for this demo without modifying the profile class, 
    # we can log that we are using it (and if we wanted, pass it to the engine later).
    # Since we updated the YAML mapping file, that 0.03 for typing is now the system default!
    
    # Set up control engine
    engine = ControlEngine(profile_manager=manager)
    engine.set_profile(profile)
    engine.set_mode(ControlMode.MANUAL)
    
    # ⚠️ OVERRIDE THRESHOLD
    if hasattr(engine, 'suppressor'): # Trigger lazy load
        _ = engine.suppressor 
        for cat in categories: # categories list from args
            if cat in engine.suppressor.category_map:
                engine.suppressor.category_map[cat]['detection_threshold'] = args.threshold
                logger.info(f"Set threshold for '{cat}' to {args.threshold}")
    
    logger.info(f"Profile: {profile.name}")
    logger.info("Ready!\n")
    
    # Rolling buffer for context
    context_duration = 1.0
    context_size = int(44100 * context_duration)
    rolling_buffer = np.zeros(context_size, dtype=np.float32)
    
    # Audio callback
    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal rolling_buffer
        if status:
            logger.warning(f"Status: {status}")
        
        try:
            # Convert to mono
            if indata.shape[1] > 1:
                audio_mono = indata.mean(axis=1)
            else:
                audio_mono = indata[:, 0]
            
            chunk_len = len(audio_mono)
            
            # Update rolling buffer
            rolling_buffer = np.roll(rolling_buffer, -chunk_len)
            rolling_buffer[-chunk_len:] = audio_mono
            
            # Process full buffer for context
            clean_full = engine.process_audio(rolling_buffer, 44100)
            
            # Extract latest chunk
            clean_audio = clean_full[-chunk_len:]
            
            # Output - match number of channels
            if outdata.shape[1] == 1:
                # Mono output
                outdata[:, 0] = clean_audio
            else:
                # Stereo output (duplicate mono)
                outdata[:, 0] = clean_audio
                outdata[:, 1] = clean_audio
        except Exception as e:
            logger.error(f"Error: {e}")
            outdata[:] = indata
    
    # Run
    logger.info("🎤 Recording from mic with noise suppression...")
    logger.info("(Speak/type to hear the difference)")
    
    # Auto-detect device channels
    try:
        default_device = sd.query_devices(kind='input')
        max_input_channels = default_device['max_input_channels']
        logger.info(f"Using {max_input_channels} input channel(s)")
    except Exception as e:
        logger.warning(f"Could not detect channels: {e}, defaulting to 1 (mono)")
        max_input_channels = 1
    
    try:
        with sd.Stream(
            samplerate=44100,
            blocksize=int(44100 * 0.1),  # 100ms
            channels=max_input_channels,  # Auto-detect
            dtype='float32',
            callback=audio_callback
        ):
            for remaining in range(args.duration, 0, -1):
                print(f"\r{remaining}s remaining...", end='', flush=True)
                time.sleep(1)
            print("\r✅ Complete!       ")
    
    except Exception as e:
        logger.error(f"Stream error: {e}")
    finally:
        # Clean up custom profile
        manager.delete_profile(profile.id)
        logger.info("\nDone!")


if __name__ == "__main__":
    main()
