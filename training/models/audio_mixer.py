"""
Waveformer inference wrapper for the Semantic Noise Mixer.

Responsibilities:
- Load pretrained Waveformer (config + checkpoint) with CPU/GPU auto-selection.
- Accept mono/stereo numpy or torch audio buffers and resample to model rate.
- Build target query vectors from class names or explicit tensors.
- Return separated audio at the caller's original sample rate.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Union
import logging

import numpy as np
import torch
import torchaudio

logger = logging.getLogger(__name__)

# Add Waveformer package to import path
WAVEFORMER_DIR = Path(__file__).resolve().parent / "Waveformer"
if str(WAVEFORMER_DIR) not in sys.path:
    sys.path.append(str(WAVEFORMER_DIR))

from src.helpers import utils  # type: ignore  # added to sys.path above
from src.training.dcc_tf import Net as WaveformerNet  # type: ignore

TARGET_SAMPLE_RATE = 44100

# Default target list from the original Waveformer CLI
TARGETS: Sequence[str] = (
    "Acoustic_guitar",
    "Alarm",
    "Applause",
    "Bark",
    "Bass_drum",
    "Burping_or_eructation",
    "Bus",
    "Cello",
    "Chime",
    "Clarinet",
    "Computer_keyboard",
    "Cough",
    "Cowbell",
    "Double_bass",
    "Drawer_open_or_close",
    "Electric_piano",
    "Fart",
    "Finger_snapping",
    "Fireworks",
    "Flute",
    "Glockenspiel",
    "Gong",
    "Gunshot_or_gunfire",
    "Harmonica",
    "Hi-hat",
    "Keys_jangling",
    "Knock",
    "Laughter",
    "Meow",
    "Microwave_oven",
    "Oboe",
    "Saxophone",
    "Scissors",
    "Shatter",
    "Siren",
    "Snare_drum",
    "Squeak",
    "Tambourine",
    "Tearing",
    "Telephone",
    "Trumpet",
    "Violin_or_fiddle",
    "Writing",
)


class WaveformerSeparator:
    """
    Simple Waveformer inference wrapper.

    Usage:
        separator = WaveformerSeparator()
        out = separator.separate(audio, sample_rate, targets=["Speech"])
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        checkpoint_path: Optional[Path] = None,
        device: Optional[Union[str, torch.device]] = None,
        use_onnx: bool = False,
        onnx_path: Optional[Path] = None,
    ) -> None:
        self.config_path = config_path or WAVEFORMER_DIR / "default_config.json"
        self.checkpoint_path = checkpoint_path or WAVEFORMER_DIR / "default_ckpt.pt"
        self.device = torch.device(device) if device else self._auto_device()
        self._use_onnx = use_onnx
        self._ort_session = None

        # ── ONNX Runtime inference path ──
        # Provides cross-platform acceleration via TensorRT/CUDA/CPU execution providers.
        # Requires a pre-exported .onnx file (run export/export_onnx.py first).
        if use_onnx:
            _onnx_file = onnx_path or (WAVEFORMER_DIR / "waveformer.onnx")
            if not _onnx_file.exists():
                raise FileNotFoundError(
                    f"ONNX model not found at {_onnx_file}. "
                    "Run `python -m export.export_onnx` first."
                )
            try:
                import onnxruntime as ort
            except ImportError:
                raise ImportError(
                    "onnxruntime is required for ONNX inference. "
                    "Install with: pip install onnxruntime-gpu  (or onnxruntime for CPU)"
                )
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4
            # Prefer TensorRT > CUDA > CPU, falling back automatically
            providers = []
            if "TensorrtExecutionProvider" in ort.get_available_providers():
                providers.append("TensorrtExecutionProvider")
            if "CUDAExecutionProvider" in ort.get_available_providers():
                providers.append("CUDAExecutionProvider")
            providers.append("CPUExecutionProvider")
            self._ort_session = ort.InferenceSession(
                str(_onnx_file), sess_options, providers=providers
            )
            logger.info(f"ONNX Runtime initialized with providers: {self._ort_session.get_providers()}")
            # Still load PyTorch model for resampling utilities
            # but skip heavy init since inference goes through ORT

        self._ensure_assets_exist()

        params = utils.Params(str(self.config_path))
        self.model = WaveformerNet(**params.model_params).to(self.device).eval()

        state = torch.load(
            self.checkpoint_path, map_location=self.device, weights_only=False
        )
        self.model.load_state_dict(state["model_state_dict"])
        
        # CPU Optimization: Dynamic INT8 Quantization for Linear/LSTM layers
        # This drastically reduces memory and CPU inference latency
        if self.device.type == "cpu" and not use_onnx:
            self.model = torch.quantization.quantize_dynamic(
                self.model,
                {torch.nn.Linear},
                dtype=torch.qint8
            )
        
        # GPU Optimization: torch.compile with reduce-overhead mode
        # Fuses GPU kernels and eliminates Python overhead for 1.5-5x speedup.
        # First call triggers JIT compilation (~10-30s), all subsequent calls are fast.
        if self.device.type == "cuda" and not use_onnx:
            try:
                self.model = torch.compile(self.model, mode="reduce-overhead")
                logger.info("torch.compile enabled for GPU inference (mode=reduce-overhead)")
            except Exception as e:
                logger.warning(f"torch.compile failed, falling back to eager mode: {e}")
        
        # Audio resampling cache
        self._resample_in = {}
        self._resample_out = {}
        
        # Target Query cache
        self._query_cache = {}
        
        # Warm-up: run a single dummy inference to eliminate first-call latency
        # (triggers CUDA context init, JIT compilation, ONNX graph optimization)
        self._warm_up()

    def _warm_up(self) -> None:
        """Run a dummy inference to trigger all lazy initializations."""
        try:
            dummy_audio = np.zeros(TARGET_SAMPLE_RATE, dtype=np.float32)  # 1s silence
            self.separate(dummy_audio, TARGET_SAMPLE_RATE, targets=TARGETS[:1])
            logger.info("Model warm-up complete")
        except Exception as e:
            logger.warning(f"Warm-up inference failed (non-critical): {e}")

    def _auto_device(self) -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    def _ensure_assets_exist(self) -> None:
        missing = []
        if not self.config_path.exists():
            missing.append(self.config_path)
        if not self.checkpoint_path.exists():
            missing.append(self.checkpoint_path)
        if missing:
            raise FileNotFoundError(
                f"Waveformer assets missing: {', '.join(str(m) for m in missing)}. "
                "Run `python scripts/download_models.py` from repo root."
            )

    def _to_channel_first(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        input_format: Optional[str] = None,
    ) -> torch.Tensor:
        """
        Normalize input to (channels, samples) float32 tensor.
        Accepts mono or stereo, channel-last or channel-first.

        Args:
            audio: Input audio array (np.ndarray or torch.Tensor).
            input_format: Specify 'channel_first' or 'channel_last' explicitly.
                If None, uses heuristic: assumes channel-last (T, C) if samples > channels.
                WARNING: The heuristic can be incorrect for edge cases. For robust 
                behavior, specify input_format explicitly.

        Note on Mono Conversion:
            This method FORCES mono conversion (averaging channels) because the 
            underlying Waveformer model is strictly mono. Stereo inputs will be
            downmixed before inference. This is a deliberate design choice as
            Waveformer is not trained for stereo separation.
        """
        tensor = torch.as_tensor(audio, dtype=torch.float32)
        
        # 1. Ensure channel-first format (C, T)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)  # (samples,) -> (1, samples)
        elif tensor.ndim == 2:
            if input_format == "channel_last":
                tensor = tensor.transpose(0, 1)
            elif input_format == "channel_first":
                pass
            elif input_format is not None:
                raise ValueError(
                    f"Unsupported input_format '{input_format}'. "
                    "Expected 'channel_first', 'channel_last', or None."
                )
            else:
                # Heuristic: assume channel-last if samples > channels
                if tensor.shape[0] > tensor.shape[1]:
                    tensor = tensor.transpose(0, 1)
        else:
            raise ValueError(f"Expected 1D or 2D audio, got {tensor.ndim}D")
            
        # 2. FORCE MONO - Waveformer is ONLY trained on mono (1, T)
        if tensor.shape[0] > 1:
            tensor = tensor.mean(dim=0, keepdim=True)
            
        return tensor

    def _build_query(
        self,
        targets: Optional[Union[Sequence[str], torch.Tensor, np.ndarray]],
    ) -> torch.Tensor:
        """
        Build query vector for the model.
        - None: all ones (full mixture)
        - List[str]: one-hot/multi-hot over TARGETS
        - Tensor/ndarray: used directly after validation
        """
        if targets is None:
            return torch.ones(1, len(TARGETS), dtype=torch.float32, device=self.device)

        if isinstance(targets, (torch.Tensor, np.ndarray)):
            query = torch.as_tensor(targets, dtype=torch.float32, device=self.device)
            if query.ndim == 1:
                query = query.unsqueeze(0)
            if query.shape[-1] != len(TARGETS):
                raise ValueError(
                    f"Query length {query.shape[-1]} does not match TARGETS ({len(TARGETS)})."
                )
            return query

        # Check cache first for string lists (most common case)
        if isinstance(targets, (list, tuple)) and all(isinstance(t, str) for t in targets):
            cache_key = tuple(sorted(targets))
            if cache_key in self._query_cache:
                return self._query_cache[cache_key].clone()

        # Use 41 as the strict Waveformer compatibility size
        query = torch.zeros(1, 41, dtype=torch.float32, device=self.device)
        for target in targets:
            if target not in TARGETS:
                raise ValueError(f"Unknown target '{target}'. Valid: {', '.join(TARGETS)}")
            
            # Siren and Alarm do not have Waveformer targets, so we skip adding them
            # to the query vector.
            if target in ("Siren", "Alarm"):
                continue

            # We use the original index of the target in TARGETS to set the query vector.
            # However, because Siren and Alarm were added to the TARGETS list, we need to
            # map the TARGETS index back to the 41 original targets.
            index = TARGETS.index(target)
            if index > TARGETS.index("Siren"):
                index -= 1
            if index > TARGETS.index("Alarm"):
                index -= 1

            query[0, index] = 1.0
            
        # Add to cache for string lists
        if isinstance(targets, (list, tuple)) and all(isinstance(t, str) for t in targets):
            self._query_cache[cache_key] = query.clone()
            
        return query

    def separate(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        targets: Optional[Union[Sequence[str], torch.Tensor, np.ndarray]] = None,
    ) -> np.ndarray:
        """
        Run Waveformer separation.

        Args:
            audio: mono/stereo buffer (np or torch), shape (samples,) or (samples, channels)
            sample_rate: input sample rate
            targets: None (all ones), list of class names, or explicit vector
            
        Returns:
            np.ndarray shape (samples, channels) at original sample_rate. 
            Note: The output will be mono (identical channels) as Waveformer 
            strictly operates in mono.
        """
        mixture = self._to_channel_first(audio)
        needs_resample = sample_rate != TARGET_SAMPLE_RATE
        if needs_resample:
            if sample_rate not in self._resample_in:
                self._resample_in[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, new_freq=TARGET_SAMPLE_RATE
                ).to(mixture.device)
            mixture = self._resample_in[sample_rate](mixture)

        mixture = mixture.unsqueeze(0)  # (1, C, T)
        query = self._build_query(targets)

        # ── Inference: ONNX Runtime or PyTorch ──
        if self._ort_session is not None:
            ort_inputs = {
                "audio_input": mixture.numpy(),
                "query_vector": query.cpu().numpy(),
            }
            ort_output = self._ort_session.run(None, ort_inputs)[0]
            output = torch.from_numpy(ort_output).squeeze(0)  # (C, T)
        else:
            mixture_gpu = mixture.to(self.device)
            with torch.inference_mode():
                output = self.model(mixture_gpu, query).squeeze(0).cpu()  # (C, T)

        if needs_resample:
            if sample_rate not in self._resample_out:
                self._resample_out[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=TARGET_SAMPLE_RATE, new_freq=sample_rate
                ).to(output.device)
            output = self._resample_out[sample_rate](output)

        # Return channel-last for convenience
        return output.transpose(0, 1).numpy()

    def separate_multi_query(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        target_groups: Sequence[Sequence[str]],
    ) -> list[np.ndarray]:
        """
        Run Waveformer separation for multiple target groups with shared preprocessing.

        Preprocesses audio exactly once (conversion, resampling, GPU transfer),
        then runs inference for all query groups.  On the PyTorch path, queries
        are *batched* into a single forward pass for maximum GPU utilisation.

        Args:
            audio: mono/stereo buffer, shape (samples,) or (samples, channels)
            sample_rate: input sample rate
            target_groups: list of target-name lists, one per category
                e.g. [["Computer_keyboard", "Writing"], ["Bark", "Meow"]]

        Returns:
            List of np.ndarray, one per target group, each shape (samples, channels)
            at the original sample_rate.
        """
        if not target_groups:
            return []

        # ── Single-group fast path: delegate to existing method ──
        if len(target_groups) == 1:
            return [self.separate(audio, sample_rate, targets=list(target_groups[0]))]

        # ── Shared preprocessing (done ONCE) ──
        mixture = self._to_channel_first(audio)                # numpy → torch (C, T)
        needs_resample = sample_rate != TARGET_SAMPLE_RATE
        if needs_resample:
            if sample_rate not in self._resample_in:
                self._resample_in[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, new_freq=TARGET_SAMPLE_RATE
                ).to(mixture.device)
            mixture = self._resample_in[sample_rate](mixture)

        mixture_unsqueeze = mixture.unsqueeze(0)

        # ── Build all queries ──
        queries = [self._build_query(list(tg)) for tg in target_groups]  # each (1, Q)
        n_groups = len(queries)

        # ── Inference ──
        if self._ort_session is not None:
            # ONNX path: sequential per-query (shared preprocessed tensor)
            mixture_np = mixture_unsqueeze.numpy()
            outputs_ct = []
            for q in queries:
                ort_inputs = {
                    "audio_input": mixture_np,
                    "query_vector": q.cpu().numpy(),
                }
                ort_out = self._ort_session.run(None, ort_inputs)[0]
                outputs_ct.append(torch.from_numpy(ort_out).squeeze(0))  # (C, T)
        else:
            # PyTorch path: batch all queries in a single forward pass
            mixture_gpu = mixture_unsqueeze.to(self.device)
            mixture_batch = mixture_gpu.expand(n_groups, -1, -1).contiguous()  # (N, C, T)
            queries_batch = torch.cat(queries, dim=0)                          # (N, Q)
            with torch.inference_mode():
                batch_output = self.model(mixture_batch, queries_batch)  # (N, C, T)
            outputs_ct = [batch_output[i].cpu() for i in range(n_groups)]

        # ── Shared postprocessing ──
        if needs_resample:
            if sample_rate not in self._resample_out:
                self._resample_out[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=TARGET_SAMPLE_RATE, new_freq=sample_rate
                ).to(outputs_ct[0].device)
            resampler = self._resample_out[sample_rate]
            outputs_ct = [resampler(o) for o in outputs_ct]

        # Channel-last numpy for each group
        return [o.transpose(0, 1).numpy() for o in outputs_ct]

    def separate_stems(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        stem_queries: Mapping[str, Iterable[str]],
    ) -> Mapping[str, np.ndarray]:
        """
        Convenience: run multiple queries and return a dict of stems.
        stem_queries example:
            {"speech": ["Speech"], "noise": ["Bus", "Microwave_oven"]}
        """
        results = {}
        for stem, targets in stem_queries.items():
            results[stem] = self.separate(audio, sample_rate, targets=targets)
        return results


__all__ = ["WaveformerSeparator", "TARGETS", "TARGET_SAMPLE_RATE"]
