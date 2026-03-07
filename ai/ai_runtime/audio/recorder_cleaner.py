"""
Real-time Recorder & Cleaner

Records audio from microphone, applies semantic noise suppression in real-time,
and saves the cleaned audio to a WAV file.

Usage:
    python -m ai.ai_runtime.audio.recorder_cleaner --duration 10 --suppress typing
"""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ai.ai_runtime.profiles import ControlEngine, ControlMode, ProfileManager
from ai.ai_runtime.utils.paths import get_data_audio_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and clean audio in real-time")
    parser.add_argument("--duration", "-d", type=int, default=10, help="Recording duration in seconds")
    parser.add_argument("--suppress", "-s", type=str, default="typing", help="Categories to suppress")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output filename (optional)")
    parser.add_argument("--threshold", "-t", type=float, default=0.06, help="Detection threshold (raised from 0.03 to reduce false positives)")
    parser.add_argument(
        "--aggressiveness", "-a", type=float, default=1.5, help="Suppression aggressiveness (1.0-2.0)"
    )
    parser.add_argument(
        "--suppress-all",
        action="store_true",
        help="Use DeepFilterNet to universally suppress all background noise",
    )
    parser.add_argument(
        "--universal",
        type=str,
        default=None,
        help="Phase 3: Open-vocabulary text prompts for exact sound extraction (e.g., 'typing, dog barking')",
    )
    parser.add_argument(
        "--device", type=int, default=None, help="Input device ID (use 'python -m sounddevice' to list)"
    )
    parser.add_argument(
        "--lookahead",
        type=float,
        default=0.5,
        help="Lookahead delay in seconds (0.0-1.5). Provides 'future' context to the model at the cost of processing latency.",
    )

    args = parser.parse_args()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = args.output if args.output else f"recording_{timestamp}_cleaned.wav"

    if args.output and (Path(args.output).parent != Path(".")):
        output_path = Path(args.output).resolve()
    else:
        samples_dir = get_data_audio_path("processed")
        samples_dir.mkdir(parents=True, exist_ok=True)
        output_path = samples_dir / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing engine...")
    manager = ProfileManager()
    suppressions = {cat.strip(): True for cat in args.suppress.split(",")}
    profile = manager.create_profile(
        name="Recorder Temp",
        description="Temp recording profile",
        suppressions=suppressions,
    )

    engine = ControlEngine(profile_manager=manager)
    engine.set_profile(profile)
    engine.set_mode(ControlMode.MANUAL)

    # Apply threshold: use category default when it's more sensitive (lower) than CLI; else max of both
    if hasattr(engine, "suppressor"):
        _ = engine.suppressor
        for cat in suppressions.keys():
            if cat in engine.suppressor.category_map:
                cat_default = engine.suppressor.category_map[cat].get(
                    "detection_threshold", 0.5
                )
                # Use more sensitive (lower) threshold; -1 (always suppress) passes through
                effective = (
                    cat_default
                    if cat_default < 0
                    else min(args.threshold, cat_default)
                )
                engine.suppressor.category_map[cat]["detection_threshold"] = effective
                logger.info(
                    "Category '%s': threshold %.3f (CLI %.3f, config default %.3f)",
                    cat, effective, args.threshold, cat_default,
                )

    q = queue.Queue(maxsize=10)
    sample_rate = 44100
    context_duration = 3.0
    context_size = int(sample_rate * context_duration)
    rolling_buffer = np.zeros(context_size, dtype=np.float32)

    def audio_callback(indata, frames, callback_time, status):  # noqa: ARG001
        if status:
            logger.warning("Callback status: %s", status)
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            logger.warning("Audio queue full, dropping frame")

    recorded_frames = []
    recorded_noise = []
    recorded_original = []

    logger.info("Recording for %ss...", args.duration)
    logger.info("Suppressing: %s", args.suppress)
    logger.info("Press Ctrl+C to stop early")

    try:
        try:
            dev = sd.query_devices(kind="input")
            input_channels = dev["max_input_channels"]
        except Exception:
            input_channels = 1

        stft_aligned_blocksize = 8192
        if args.device is not None:
            logger.info("Using specified input device ID: %s", args.device)

        with sd.InputStream(
            samplerate=sample_rate,
            device=args.device,
            channels=input_channels,
            blocksize=stft_aligned_blocksize,
            callback=audio_callback,
        ):
            start_time = time.time()
            while time.time() - start_time < args.duration:
                try:
                    raw_chunk = q.get(timeout=1.0)
                    if raw_chunk.shape[1] > 1:
                        mono_chunk = raw_chunk.mean(axis=1)
                    else:
                        mono_chunk = raw_chunk.flatten()

                    chunk_len = len(mono_chunk)
                    rolling_buffer = np.roll(rolling_buffer, -chunk_len)
                    rolling_buffer[-chunk_len:] = mono_chunk

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
                            universal_prompts=universal_targets,
                        )
                    else:
                        clean_full_buffer = rolling_buffer

                    lookahead_delay = args.lookahead
                    offset = int(lookahead_delay * sample_rate)
                    end_idx = context_size - offset
                    start_idx = end_idx - chunk_len
                    clean_chunk = np.asarray(
                        clean_full_buffer[start_idx:end_idx], dtype=np.float32
                    ).copy()
                    original_chunk = np.asarray(
                        rolling_buffer[start_idx:end_idx], dtype=np.float32
                    ).copy()

                    # Clip to valid WAV range to prevent distortion
                    clean_chunk = np.clip(clean_chunk, -1.0, 1.0)
                    recorded_frames.append(clean_chunk)
                    noise_chunk = np.clip(
                        original_chunk - clean_chunk, -1.0, 1.0
                    ).astype(np.float32)
                    recorded_noise.append(noise_chunk)
                    recorded_original.append(original_chunk)

                    noise_peak = np.max(np.abs(noise_chunk))
                    if noise_peak > 0.001:
                        logger.info("Suppression active: peak amplitude removed = %.5f", noise_peak)

                except queue.Empty:
                    pass
                except KeyboardInterrupt:
                    break

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        if recorded_frames:
            logger.info("Saving audio...")
            audio_data = np.concatenate(recorded_frames).astype(np.float32)
            audio_data = np.clip(audio_data, -1.0, 1.0)
            sf.write(str(output_path), audio_data, sample_rate)
            logger.info("Saved clean audio to: %s", output_path)

            noise_data = np.concatenate(recorded_noise).astype(np.float32)
            noise_data = np.clip(noise_data, -1.0, 1.0)
            noise_path = str(output_path).replace(".wav", "_noise.wav")
            sf.write(noise_path, noise_data, sample_rate)
            logger.info("Saved extracted noise to: %s", noise_path)

            orig_data = np.concatenate(recorded_original).astype(np.float32)
            orig_data = np.clip(orig_data, -1.0, 1.0)
            orig_path = str(output_path).replace(".wav", "_original.wav")
            sf.write(orig_path, orig_data, sample_rate)
            logger.info("Saved original mic input to: %s", orig_path)

        manager.delete_profile(profile.id)


if __name__ == "__main__":
    main()
