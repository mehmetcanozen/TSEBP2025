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

import numpy as np
import torch
import torchaudio

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
    ) -> None:
        self.config_path = config_path or WAVEFORMER_DIR / "default_config.json"
        self.checkpoint_path = checkpoint_path or WAVEFORMER_DIR / "default_ckpt.pt"
        self.device = torch.device(device) if device else self._auto_device()

        self._ensure_assets_exist()

        params = utils.Params(str(self.config_path))
        self.model = WaveformerNet(**params.model_params).to(self.device).eval()

        state = torch.load(
            self.checkpoint_path, map_location=self.device, weights_only=False
        )
        self.model.load_state_dict(state["model_state_dict"])
        
        # CPU Optimization: Dynamic INT8 Quantization for Linear/LSTM layers
        # This drastically reduces memory and CPU inference latency
        if self.device.type == "cpu":
            self.model = torch.quantization.quantize_dynamic(
                self.model,
                {torch.nn.Linear},
                dtype=torch.qint8
            )
        
        # Audio resampling cache
        self._resample_in = {}
        self._resample_out = {}
        
        # Target Query cache
        self._query_cache = {}

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

        query = torch.zeros(1, len(TARGETS), dtype=torch.float32, device=self.device)
        for target in targets:
            if target not in TARGETS:
                raise ValueError(f"Unknown target '{target}'. Valid: {', '.join(TARGETS)}")
            query[0, TARGETS.index(target)] = 1.0
            
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

        mixture = mixture.unsqueeze(0).to(self.device)  # (1, C, T)
        query = self._build_query(targets)

        with torch.inference_mode():
            output = self.model(mixture, query).squeeze(0).cpu()  # (C, T)

        if needs_resample:
            if sample_rate not in self._resample_out:
                self._resample_out[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=TARGET_SAMPLE_RATE, new_freq=sample_rate
                ).to(output.device)
            output = self._resample_out[sample_rate](output)

        # Return channel-last for convenience
        return output.transpose(0, 1).numpy()

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
