"""
Real-time Microphone Noise Suppression Demo

Live demonstration of semantic noise suppression from mic input.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import sounddevice as sd

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from desktop.src.profiles import ControlEngine, ControlMode

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RealtimeSuppressor:
    """Real-time microphone noise suppression."""
    
    def __init__(self, profile_id: str = "default-focus", sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.chunk_size = int(sample_rate * 0.1)  # 100ms chunks
        self.engine = ControlEngine()
        self.engine.set_profile_by_id(profile_id)
        self.engine.set_mode(ControlMode.MANUAL)
        
        self.running = False
        self.input_buffer = []
        self.output_buffer = []
        
        logger.info(f"Initialized with profile: {self.engine.current_profile.name}")
        logger.info(f"Sample rate: {sample_rate} Hz, Chunk size: {self.chunk_size}")
    
    def audio_callback(self, indata, outdata, frames, time_info, status):
        """Audio callback for real-time processing."""
        if status:
            logger.warning(f"Audio callback status: {status}")
        
        try:
            # Convert to mono if stereo
            if indata.shape[1] > 1:
                audio_mono = indata.mean(axis=1)
            else:
                audio_mono = indata[:, 0]
            
            # Process audio with control engine
            clean_audio = self.engine.process_audio(audio_mono, self.sample_rate)
            
            # Output stereo (duplicate mono to both channels)
            outdata[:, 0] = clean_audio
            outdata[:, 1] = clean_audio
            
        except Exception as e:
            logger.error(f"Processing error: {e}")
            # Pass through on error
            outdata[:] = indata
    
    def start(self, device=None, duration_seconds=None):
        """Start real-time processing."""
        logger.info("Starting real-time mic suppression...")
        logger.info(f"Profile: {self.engine.current_profile.name}")
        
        suppressions = [cat for cat, enabled in self.engine.current_profile.suppressions.items() if enabled]
        if suppressions:
            logger.info(f"Suppressing: {', '.join(suppressions)}")
        else:
            logger.info("Passthrough mode (no suppression)")
        
        logger.info("\nPress Ctrl+C to stop...")
        
        self.running = True
        
        try:
            with sd.Stream(
                device=device,
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                channels=2,  # Stereo
                dtype='float32',
                callback=self.audio_callback
            ):
                if duration_seconds:
                    time.sleep(duration_seconds)
                else:
                    while self.running:
                        time.sleep(0.1)
        
        except KeyboardInterrupt:
            logger.info("\nStopped by user")
        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """Stop processing."""
        self.running = False


def main():
    parser = argparse.ArgumentParser(description="Real-time mic noise suppression")
    parser.add_argument(
        "--profile", "-p",
        default="default-focus",
        help="Profile ID to use (default: default-focus)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=None,
        help="Duration in seconds (default: run until Ctrl+C)"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio devices"
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="Audio device ID to use"
    )
    
    args = parser.parse_args()
    
    if args.list_devices:
        logger.info("Available audio devices:")
        print(sd.query_devices())
        return
    
    suppressor = RealtimeSuppressor(
        profile_id=args.profile,
        sample_rate=44100
    )
    
    suppressor.start(device=args.device, duration_seconds=args.duration)
    
    logger.info("Done!")


if __name__ == "__main__":
    main()
