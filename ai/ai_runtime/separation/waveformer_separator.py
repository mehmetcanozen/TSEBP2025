"""
Waveformer inference wrapper for the Semantic Noise Mixer.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, Union

import numpy as np
import torch
import torchaudio

from ai.ai_runtime.utils.paths import (
    get_waveformer_checkpoint_path,
    get_waveformer_config_path,
    get_waveformer_model_path,
)

logger = logging.getLogger(__name__)

# Add Waveformer package to import path (vendored under ai/models/)
WAVEFORMER_DIR = get_waveformer_model_path()
if str(WAVEFORMER_DIR) not in sys.path:
    sys.path.append(str(WAVEFORMER_DIR))

from src.helpers import utils  # type: ignore  # noqa: E402
from src.training.dcc_tf import Net as WaveformerNet  # type: ignore  # noqa: E402

TARGET_SAMPLE_RATE = 44100
TARGETS: Sequence[str] = (
    "Acoustic_guitar",
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
    """Simple Waveformer inference wrapper."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        checkpoint_path: Optional[Path] = None,
        device: Optional[Union[str, torch.device]] = None,
        use_onnx: bool = False,
        onnx_path: Optional[Path] = None,
    ) -> None:
        self.config_path = config_path or get_waveformer_config_path()
        self.checkpoint_path = checkpoint_path or get_waveformer_checkpoint_path()
        self.device = torch.device(device) if device else self._auto_device()
        self._use_onnx = use_onnx
        self._ort_session = None

        if use_onnx:
            _onnx_file = onnx_path or (WAVEFORMER_DIR / "waveformer.onnx")
            if not _onnx_file.exists():
                raise FileNotFoundError(
                    f"ONNX model not found at {_onnx_file}. Run `python -m ai.export.export_onnx` first."
                )
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise ImportError(
                    "onnxruntime is required for ONNX inference. "
                    "Install with: pip install onnxruntime-gpu (or onnxruntime for CPU)."
                ) from exc
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4
            providers = []
            if "TensorrtExecutionProvider" in ort.get_available_providers():
                providers.append("TensorrtExecutionProvider")
            if "CUDAExecutionProvider" in ort.get_available_providers():
                providers.append("CUDAExecutionProvider")
            providers.append("CPUExecutionProvider")
            self._ort_session = ort.InferenceSession(
                str(_onnx_file), sess_options, providers=providers
            )
            logger.info("ONNX Runtime initialized with providers: %s", self._ort_session.get_providers())

        self._ensure_assets_exist()
        params = utils.Params(str(self.config_path))
        self.model = WaveformerNet(**params.model_params).to(self.device).eval()

        state = torch.load(self.checkpoint_path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(state["model_state_dict"])

        if self.device.type == "cpu" and not use_onnx:
            self.model = torch.quantization.quantize_dynamic(
                self.model, {torch.nn.Linear}, dtype=torch.qint8
            )

        if self.device.type == "cuda" and not use_onnx:
            try:
                self.model = torch.compile(self.model, mode="reduce-overhead")
                logger.info("torch.compile enabled for GPU inference (mode=reduce-overhead)")
            except Exception as exc:
                logger.warning("torch.compile failed, falling back to eager mode: %s", exc)

        self._resample_in = {}
        self._resample_out = {}
        self._query_cache = {}
        self._warm_up()

    def _warm_up(self) -> None:
        try:
            dummy_audio = np.zeros(TARGET_SAMPLE_RATE, dtype=np.float32)
            self.separate(dummy_audio, TARGET_SAMPLE_RATE, targets=TARGETS[:1])
            logger.info("Model warm-up complete")
        except Exception as exc:
            logger.warning("Warm-up inference failed (non-critical): %s", exc)

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
                "Run `python ai/scripts/setup/download_models.py` from repo root."
            )

    def _to_channel_first(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        input_format: Optional[str] = None,
    ) -> torch.Tensor:
        tensor = torch.as_tensor(audio, dtype=torch.float32)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        elif tensor.ndim == 2:
            if input_format == "channel_last":
                tensor = tensor.transpose(0, 1)
            elif input_format == "channel_first":
                pass
            elif input_format is not None:
                raise ValueError(
                    f"Unsupported input_format '{input_format}'. Expected channel_first/channel_last/None."
                )
            elif tensor.shape[0] > tensor.shape[1]:
                tensor = tensor.transpose(0, 1)
        else:
            raise ValueError(f"Expected 1D or 2D audio, got {tensor.ndim}D")

        if tensor.shape[0] > 1:
            tensor = tensor.mean(dim=0, keepdim=True)
        return tensor

    def _build_query(
        self,
        targets: Optional[Union[Sequence[str], torch.Tensor, np.ndarray]],
    ) -> torch.Tensor:
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

        cache_key = None
        if isinstance(targets, (list, tuple)) and all(isinstance(t, str) for t in targets):
            cache_key = tuple(sorted(targets))
            if cache_key in self._query_cache:
                return self._query_cache[cache_key].clone()

        query = torch.zeros(1, len(TARGETS), dtype=torch.float32, device=self.device)
        for target in targets:
            if target not in TARGETS:
                raise ValueError(f"Unknown target '{target}'. Valid: {', '.join(TARGETS)}")
            query[0, TARGETS.index(target)] = 1.0

        if cache_key is not None:
            self._query_cache[cache_key] = query.clone()
        return query

    def separate(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        targets: Optional[Union[Sequence[str], torch.Tensor, np.ndarray]] = None,
    ) -> np.ndarray:
        mixture = self._to_channel_first(audio)
        needs_resample = sample_rate != TARGET_SAMPLE_RATE
        if needs_resample:
            if sample_rate not in self._resample_in:
                self._resample_in[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, new_freq=TARGET_SAMPLE_RATE
                ).to(mixture.device)
            mixture = self._resample_in[sample_rate](mixture)

        mixture = mixture.unsqueeze(0)
        query = self._build_query(targets)

        if self._ort_session is not None:
            ort_inputs = {
                "audio_input": mixture.cpu().numpy(),
                "query_vector": query.cpu().numpy(),
            }
            ort_output = self._ort_session.run(None, ort_inputs)[0]
            output = torch.from_numpy(ort_output).squeeze(0)
        else:
            mixture_gpu = mixture.to(self.device)
            with torch.inference_mode():
                output = self.model(mixture_gpu, query).squeeze(0).cpu()

        if needs_resample:
            if sample_rate not in self._resample_out:
                self._resample_out[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=TARGET_SAMPLE_RATE, new_freq=sample_rate
                ).to(output.device)
            output = self._resample_out[sample_rate](output)

        return output.transpose(0, 1).numpy()

    def separate_multi_query(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        target_groups: Sequence[Sequence[str]],
    ) -> list[np.ndarray]:
        if not target_groups:
            return []
        if len(target_groups) == 1:
            return [self.separate(audio, sample_rate, targets=list(target_groups[0]))]

        mixture = self._to_channel_first(audio)
        needs_resample = sample_rate != TARGET_SAMPLE_RATE
        if needs_resample:
            if sample_rate not in self._resample_in:
                self._resample_in[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, new_freq=TARGET_SAMPLE_RATE
                ).to(mixture.device)
            mixture = self._resample_in[sample_rate](mixture)

        mixture_unsqueeze = mixture.unsqueeze(0)
        queries = [self._build_query(list(tg)) for tg in target_groups]
        n_groups = len(queries)

        if self._ort_session is not None:
            mixture_np = mixture_unsqueeze.cpu().numpy()
            outputs_ct = []
            for q in queries:
                ort_inputs = {"audio_input": mixture_np, "query_vector": q.cpu().numpy()}
                ort_out = self._ort_session.run(None, ort_inputs)[0]
                outputs_ct.append(torch.from_numpy(ort_out).squeeze(0))
        else:
            mixture_gpu = mixture_unsqueeze.to(self.device)
            mixture_batch = mixture_gpu.expand(n_groups, -1, -1).contiguous()
            queries_batch = torch.cat(queries, dim=0)
            with torch.inference_mode():
                batch_output = self.model(mixture_batch, queries_batch)
            outputs_ct = [batch_output[i].cpu() for i in range(n_groups)]

        if needs_resample:
            if sample_rate not in self._resample_out:
                self._resample_out[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=TARGET_SAMPLE_RATE, new_freq=sample_rate
                ).to(outputs_ct[0].device)
            resampler = self._resample_out[sample_rate]
            outputs_ct = [resampler(o) for o in outputs_ct]

        return [o.transpose(0, 1).numpy() for o in outputs_ct]

    def separate_stems(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        stem_queries: Mapping[str, Iterable[str]],
    ) -> Mapping[str, np.ndarray]:
        results = {}
        for stem, targets in stem_queries.items():
            results[stem] = self.separate(audio, sample_rate, targets=targets)
        return results


__all__ = ["TARGET_SAMPLE_RATE", "TARGETS", "WaveformerSeparator"]
