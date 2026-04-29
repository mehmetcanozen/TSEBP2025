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
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

try:
    import sounddevice as sd
except ImportError:
    class _MissingSoundDevice:
        InputStream = None

        @staticmethod
        def query_devices(*_args, **_kwargs):
            raise ImportError(
                "sounddevice is required for live audio capture. "
                "Install with: pip install sounddevice"
            )

        def __getattr__(self, _name: str):
            raise ImportError(
                "sounddevice is required for live audio capture. "
                "Install with: pip install sounddevice"
            )

    sd = _MissingSoundDevice()

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ai.ai_runtime.profiles import ControlEngine, ControlMode, ProfileManager
from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.utils.codecsep import (
    add_codecsep_runtime_arguments,
    build_codecsep_call_kwargs_from_args,
    build_suppressor_kwargs_from_args,
)
from ai.ai_runtime.utils.target_speaker import (
    add_target_speaker_runtime_arguments,
    build_target_speaker_call_kwargs_from_args,
    build_target_speaker_suppressor_kwargs_from_args,
)
from ai.ai_runtime.utils.paths import get_data_audio_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BufferedRealtimeSuppressor:
    """Background worker for buffered live suppression."""

    def __init__(
        self,
        *,
        suppress_fn: Callable[..., np.ndarray],
        sample_rate: int,
        context_duration: float,
        hop_seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.suppress_fn = suppress_fn
        self.sample_rate = int(sample_rate)
        self.context_duration = float(context_duration)
        self.hop_seconds = max(0.05, float(hop_seconds))
        self.context_size = int(round(self.sample_rate * self.context_duration))
        self._clock = clock or time.monotonic
        self._request_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._result_queue: queue.Queue[dict[str, np.ndarray]] = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._last_submit_at = float("-inf")
        self._inference_pending = False
        self._latest_clean_context: np.ndarray | None = None
        self._latest_gain_envelope: np.ndarray | None = None
        self._latest_result_at: float | None = None

    @property
    def inference_pending(self) -> bool:
        return self._inference_pending

    @property
    def latest_gain_envelope(self) -> np.ndarray | None:
        if self._latest_gain_envelope is None:
            return None
        return np.array(self._latest_gain_envelope, copy=True)

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="audiosep15-live-worker",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None
        self._drain_queue(self._request_queue)
        self._drain_queue(self._result_queue)
        self._inference_pending = False

    @staticmethod
    def _drain_queue(target_queue: queue.Queue[Any]) -> None:
        while True:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                return

    def _replace_queue_item(self, target_queue: queue.Queue[Any], item: Any) -> None:
        try:
            target_queue.put_nowait(item)
        except queue.Full:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                pass
            target_queue.put_nowait(item)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                request = self._request_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                clean_audio = self.suppress_fn(
                    audio=request["audio"],
                    sample_rate=self.sample_rate,
                    **request["kwargs"],
                )
                self._replace_queue_item(
                    self._result_queue,
                    {
                        "audio": request["audio"],
                        "clean_audio": np.asarray(clean_audio, dtype=np.float32),
                    },
                )
            except Exception:
                logger.exception("Buffered realtime suppression worker failed")
                self._replace_queue_item(
                    self._result_queue,
                    {
                        "audio": request["audio"],
                        "clean_audio": np.asarray(request["audio"], dtype=np.float32),
                    },
                )

    def submit_if_due(
        self,
        rolling_buffer: np.ndarray,
        *,
        suppress_kwargs: dict[str, Any],
    ) -> bool:
        now = self._clock()
        if self._inference_pending:
            return False
        if now - self._last_submit_at < self.hop_seconds:
            return False

        self._replace_queue_item(
            self._request_queue,
            {
                "audio": np.asarray(rolling_buffer, dtype=np.float32).copy(),
                "kwargs": dict(suppress_kwargs),
            },
        )
        self._last_submit_at = now
        self._inference_pending = True
        return True

    def poll_results(self) -> bool:
        updated = False
        while True:
            try:
                result = self._result_queue.get_nowait()
            except queue.Empty:
                break

            original = np.asarray(result["audio"], dtype=np.float32)
            clean = np.asarray(result["clean_audio"], dtype=np.float32)
            min_len = min(len(original), len(clean))
            original = original[:min_len]
            clean = clean[:min_len]
            gain = np.ones(min_len, dtype=np.float32)
            np.divide(clean, original, out=gain, where=np.abs(original) > 1.0e-4)
            self._latest_clean_context = clean
            self._latest_gain_envelope = np.clip(gain, 0.0, 1.25)
            self._latest_result_at = self._clock()
            self._inference_pending = False
            updated = True
        return updated

    def render_chunk(
        self,
        rolling_buffer: np.ndarray,
        *,
        chunk_len: int,
        lookahead_seconds: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        context_size = int(rolling_buffer.shape[0])
        lookahead_samples = max(0, int(round(lookahead_seconds * self.sample_rate)))
        lookahead_samples = min(lookahead_samples, max(0, context_size - chunk_len))
        end_idx = context_size - lookahead_samples
        start_idx = max(0, end_idx - chunk_len)
        original_chunk = np.asarray(rolling_buffer[start_idx:end_idx], dtype=np.float32)

        if self._latest_gain_envelope is not None and len(self._latest_gain_envelope) >= end_idx:
            clean_chunk = original_chunk * self._latest_gain_envelope[start_idx:end_idx]
        elif self._latest_clean_context is not None and len(self._latest_clean_context) >= end_idx:
            clean_chunk = self._latest_clean_context[start_idx:end_idx]
        else:
            clean_chunk = original_chunk.copy()

        return (
            np.clip(clean_chunk, -1.0, 1.0).astype(np.float32, copy=False),
            np.clip(original_chunk, -1.0, 1.0).astype(np.float32, copy=False),
        )


def build_parser() -> argparse.ArgumentParser:
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
    add_codecsep_runtime_arguments(
        parser,
        default_mode="fixed_category",
        default_query_strategy="single_pass",
        default_multistep_steps=0,
    )
    add_target_speaker_runtime_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.target_speaker_reference and args.separator_backend == "waveformer":
        args.separator_backend = "target_speaker"
    if args.separator_backend == "target_speaker" and not args.target_speaker_reference:
        parser.error("target_speaker requires --target-speaker-reference")
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
    codecsep_call_kwargs = {
        **build_codecsep_call_kwargs_from_args(args),
        **build_target_speaker_call_kwargs_from_args(args),
    }
    profile = manager.create_profile(
        name="Recorder Temp",
        description="Temp recording profile",
        suppressions=suppressions,
        suppression_params={
            "separator_backend": args.separator_backend,
            "masking_method": args.masking_method,
            "detection_threshold": args.threshold,
            "aggressiveness": args.aggressiveness,
            "codecsep_checkpoint_path": args.codecsep_checkpoint,
            "codecsep_device": args.codecsep_device,
            **codecsep_call_kwargs,
        },
    )

    suppressor = SemanticSuppressor(
        **build_suppressor_kwargs_from_args(args),
        **build_target_speaker_suppressor_kwargs_from_args(args),
    )
    engine = ControlEngine(profile_manager=manager, suppressor=suppressor)
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
    use_buffered_exact15 = args.separator_backend in {
        "audiosep_hive15cat",
        "codecsep_dnrv2_15cat",
        "target_speaker",
    }
    if args.separator_backend == "audiosep_hive15cat":
        context_duration = 5.0
        realtime_hop_seconds = float(
            codecsep_call_kwargs.get("audiosep_hive15cat_realtime_hop_seconds", 1.0)
        )
        buffered_backend_label = "AudioSepHive15Cat"
    elif args.separator_backend == "codecsep_dnrv2_15cat":
        context_duration = 2.0
        realtime_hop_seconds = float(
            codecsep_call_kwargs.get("codecsep_dnrv2_15cat_realtime_hop_seconds", 0.5)
        )
        buffered_backend_label = (
            "CodecSepDNRv2_15Cat "
            f"({codecsep_call_kwargs.get('codecsep_dnrv2_15cat_runtime', 'onnx')})"
        )
    elif args.separator_backend == "target_speaker":
        context_duration = 3.0
        realtime_hop_seconds = 0.5
        buffered_backend_label = f"TargetSpeaker ({args.target_speaker_engine})"
    else:
        context_duration = 3.0
        realtime_hop_seconds = 0.0
        buffered_backend_label = ""
    context_size = int(sample_rate * context_duration)
    rolling_buffer = np.zeros(context_size, dtype=np.float32)
    buffered_live: BufferedRealtimeSuppressor | None = None

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
    if use_buffered_exact15:
        logger.info(
            "%s live mode uses %.1fs rolling context with %.1fs async inference hops",
            buffered_backend_label,
            context_duration,
            realtime_hop_seconds,
        )

    try:
        try:
            dev = sd.query_devices(kind="input")
            input_channels = dev["max_input_channels"]
        except Exception:
            input_channels = 1

        stft_aligned_blocksize = 8192
        if args.device is not None:
            logger.info("Using specified input device ID: %s", args.device)
        if use_buffered_exact15:
            buffered_live = BufferedRealtimeSuppressor(
                suppress_fn=engine.suppressor.suppress,
                sample_rate=sample_rate,
                context_duration=context_duration,
                hop_seconds=realtime_hop_seconds,
            )
            buffered_live.start()

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
                    target_speaker_target = (
                        args.separator_backend == "target_speaker"
                        and bool(args.target_speaker_reference)
                    )

                    if use_buffered_exact15 and (
                        targets or args.suppress_all or universal_targets or target_speaker_target
                    ):
                        buffered_live.poll_results()
                        buffered_live.submit_if_due(
                            rolling_buffer,
                            suppress_kwargs={
                                "suppress_categories": targets,
                                "detection_threshold": args.threshold,
                                "aggressiveness": args.aggressiveness,
                                "suppress_all": args.suppress_all,
                                "universal_prompts": universal_targets,
                                **codecsep_call_kwargs,
                            },
                        )
                        clean_chunk, original_chunk = buffered_live.render_chunk(
                            rolling_buffer,
                            chunk_len=chunk_len,
                            lookahead_seconds=args.lookahead,
                        )
                    elif targets or args.suppress_all or universal_targets or target_speaker_target:
                        clean_full_buffer = engine.suppressor.suppress(
                            audio=rolling_buffer,
                            sample_rate=sample_rate,
                            suppress_categories=targets,
                            detection_threshold=args.threshold,
                            aggressiveness=args.aggressiveness,
                            suppress_all=args.suppress_all,
                            universal_prompts=universal_targets,
                            **codecsep_call_kwargs,
                        )
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
                    else:
                        clean_chunk, original_chunk = (
                            np.asarray(mono_chunk, dtype=np.float32).copy(),
                            np.asarray(mono_chunk, dtype=np.float32).copy(),
                        )

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
        if buffered_live is not None:
            buffered_live.stop()
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
