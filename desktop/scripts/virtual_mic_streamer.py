import argparse
import time
import sys
import logging
import sounddevice as sd
import soundfile as sf
import numpy as np
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def find_cable_input_device(search_name: str = "CABLE Input") -> int:
    """Find the device ID for the virtual device matching the search name."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_output_channels'] > 0 and search_name in dev['name']:
            return i
    
    # Fallback to general "CABLE" search
    for i, dev in enumerate(devices):
        if dev['max_output_channels'] > 0 and 'CABLE' in dev['name']:
            return i
            
    return -1

def stream_virtual_mic(input_path: str, loop: bool = True, device_name: str = "CABLE Input"):
    """
    Streams a WAV file directly into the Virtual Audio Cable.
    This makes the audio appear as if it's coming from a hardware microphone.
    """
    try:
        data, samplerate = sf.read(input_path)
    except Exception as e:
        logger.error(f"Failed to load {input_path}: {e}")
        return

    # Convert everything to stereo, as Virtual Cables generally prefer 2-channels
    if data.ndim == 1:
        data = np.stack((data, data), axis=-1)
        
    cable_device_id = find_cable_input_device(device_name)
    
    if cable_device_id == -1:
        logger.error(f"Could not find device matching '{device_name}'. Is VB-Audio Virtual Cable installed?")
        logger.error("Available output devices:")
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_output_channels'] > 0:
                logger.error(f"  {i}: {dev['name']}")
        sys.exit(1)

    device_info = sd.query_devices(cable_device_id, 'output')
    logger.info(f"Targeting Virtual Device: {device_info['name']} (ID: {cable_device_id})")
    
    # Pre-pad some silence to avoid harsh cut-in immediately upon launch
    silence = np.zeros((int(samplerate * 0.5), data.shape[1]), dtype=data.dtype)
    data = np.concatenate((silence, data))

    # Keep alive flag
    shutdown_event = threading.Event()

    def _play_loop():
        nonlocal shutdown_event
        iteration = 1
        while not shutdown_event.is_set():
            logger.info(f"Streaming iter {iteration}... Press Ctrl+C to stop.")
            try:
                sd.play(data, samplerate, device=cable_device_id)
                sd.wait() # Blocking wait until the file finishes playing
            except Exception as e:
                if not shutdown_event.is_set():  # Only log error if not actively shutting down
                    logger.error(f"Playback error: {e}")
                break
                
            if not loop:
                break
            iteration += 1
            
        logger.info("Stream ended.")

    # Start playback thread
    thread = threading.Thread(target=_play_loop, daemon=True)
    thread.start()

    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("\nStopping virtual microphone stream...")
        shutdown_event.set()
        sd.stop()
        thread.join(timeout=1.0)
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream a WAV file into a Virtual Audio Cable to simulate a microphone.")
    parser.add_argument("--input", type=str, required=True, help="Path to the WAV file to stream")
    parser.add_argument("--no-loop", action="store_true", help="Play the file only once instead of looping indefinitely")
    parser.add_argument("--device-name", type=str, default="CABLE Input", help="Search string for the virtual output device")
    args = parser.parse_args()
    
    stream_virtual_mic(args.input, loop=not args.no_loop, device_name=args.device_name)
