"""
DEBUG Real-time Suppression - Shows what YAMNet detects

This version shows you what sounds YAMNet is actually detecting.
Use this to debug why typing isn't being suppressed.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import sounddevice as sd

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from desktop.src.profiles import ProfileManager, ControlEngine, ControlMode

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_custom_profile(manager, suppress_categories):
    """Create a temporary custom profile."""
    suppressions = {cat: True for cat in suppress_categories}
    
    profile = manager.create_profile(
        name="Custom Realtime DEBUG",
        description=f"Suppress: {', '.join(suppress_categories)}",
        suppressions=suppressions
    )
    
    return profile


def main():
    parser = argparse.ArgumentParser(description="DEBUG Real-time mic - shows detections")
    parser.add_argument(
        "--suppress", "-s",
        type=str,
        default="typing",
        help="Comma-separated categories to suppress"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=30,
        help="Duration in seconds (default: 30)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.3,
        help="Detection threshold (default: 0.3, lower = more sensitive)"
    )
    
    args = parser.parse_args()
    
    categories = [c.strip() for c in args.suppress.split(",")]
    
    logger.info("=== DEBUG Real-time Suppression ===")
    logger.info(f"Will suppress: {', '.join(categories)}")
    logger.info(f"Detection threshold: {args.threshold}")
    logger.info(f"Duration: {args.duration}s")
    logger.info("\nInitializing...")
    
    # Create custom profile with lower threshold
    manager = ProfileManager()
    profile = create_custom_profile(manager, categories)
    
    # Set up control engine
    engine = ControlEngine(profile_manager=manager)
    engine.set_profile(profile)
    engine.set_mode(ControlMode.MANUAL)
    
    # Override detection threshold
    logger.info(f"\nProfile: {profile.name}")
    logger.info("Ready!\n")
    
    detection_count = 0
    last_detections = {}
    
    # Audio callback with DEBUG output
    def audio_callback(indata, outdata, frames, time_info, status):
        nonlocal detection_count, last_detections
        
        if status:
            logger.warning(f"Status: {status}")
        
        try:
            # Convert to mono
            if indata.shape[1] > 1:
                audio_mono = indata.mean(axis=1)
            else:
                audio_mono = indata[:, 0]
            
            # Get detections BEFORE processing (for debugging)
            try:
                # Use the public API of the suppressor
                detections = engine.suppressor.detect_categories(audio_mono, 44100, threshold=args.threshold)
                
                if detections and detections != last_detections:
                    print(f"\n🎯 DETECTED: {detections}")
                    last_detections = detections.copy()
                    detection_count += 1
                
            except Exception:
                pass  # Suppress detection errors for cleaner output
            
            # Process audio
            clean_audio = engine.process_audio(audio_mono, 44100)
            
            # Output - match number of channels
            if outdata.shape[1] == 1:
                outdata[:, 0] = clean_audio
            else:
                outdata[:, 0] = clean_audio
                outdata[:, 1] = clean_audio
        except Exception as e:
            logger.error(f"Error: {e}")
            outdata[:] = indata
    
    # Run
    logger.info("🎤 Recording from mic with DEBUG MODE...")
    logger.info(f"Threshold: {args.threshold} (lower = more sensitive)")
    logger.info("👉 TYPE ON YOUR KEYBOARD NOW to see if it's detected\n")
    
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
            blocksize=int(44100 * 0.5),  # Longer chunks for better detection
            channels=max_input_channels,
            dtype='float32',
            callback=audio_callback
        ):
            for remaining in range(args.duration, 0, -1):
                print(f"\r⏱️  {remaining}s remaining... (Detections so far: {detection_count})  ", end='', flush=True)
                time.sleep(1)
            print("\n\n✅ Complete!")
    
    except Exception as e:
        logger.error(f"Stream error: {e}")
    finally:
        # Clean up
        manager.delete_profile(profile.id)
        print(f"\n📊 Total detections: {detection_count}")
        if detection_count == 0:
            print("\n⚠️  No sounds detected above threshold!")
            print(f"Try running with lower threshold: --threshold 0.1")
        logger.info("\nDone!")


if __name__ == "__main__":
    main()
