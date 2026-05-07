"""
Vanilla AudioSep open-vocabulary separator.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import torch
import torchaudio

from ai.ai_runtime.utils import audio_utils

logger = logging.getLogger(__name__)


class UniversalSeparator:
    """Legacy-named wrapper for the vanilla AudioSep open-vocabulary extractor."""

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        device: Optional[Union[str, torch.device]] = None,
    ) -> None:
        self.device = torch.device(device) if device else self._auto_device()
        self.model_dir = (
            Path(model_dir)
            if model_dir
            else Path(__file__).resolve().parents[2] / "models" / "AudioSep"
        )
        self.model = None
        self.sr = 32000

    def _auto_device(self) -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    def _lazy_load_model(self) -> None:
        if self.model is not None:
            return

        repo_path = self.model_dir.resolve()
        if not repo_path.exists():
            raise FileNotFoundError(
                f"AudioSep not found at {repo_path}. "
                "Clone https://github.com/Audio-AGI/AudioSep and download checkpoints."
            )

        if str(repo_path) not in sys.path:
            sys.path.insert(0, str(repo_path))

        try:
            import importlib.util
            import os

            logger.info("Loading AudioSep model to %s...", self.device)
            original_cwd = os.getcwd()
            os.chdir(str(repo_path))

            original_load = torch.load

            def patched_load(*args, **kwargs):
                if "weights_only" not in kwargs:
                    kwargs["weights_only"] = False
                return original_load(*args, **kwargs)

            torch.load = patched_load
            try:
                spec = importlib.util.spec_from_file_location("audiosep_pipeline", str(repo_path / "pipeline.py"))
                pipeline_module = importlib.util.module_from_spec(spec)
                sys.modules["audiosep_pipeline"] = pipeline_module
                assert spec.loader is not None
                spec.loader.exec_module(pipeline_module)
                self.model = pipeline_module.build_audiosep(
                    config_yaml="config/audiosep_base.yaml",
                    checkpoint_path="checkpoint/audiosep_base_4M_steps.ckpt",
                    device=self.device,
                )
            finally:
                torch.load = original_load
                os.chdir(original_cwd)
            logger.info("AudioSep ready")
        except ImportError as exc:
            raise ImportError(f"Failed to import AudioSep pipeline: {exc}") from exc

    def separate(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        prompts: List[str],
    ) -> np.ndarray:
        if not prompts:
            if isinstance(audio, torch.Tensor):
                return torch.zeros_like(audio).cpu().numpy()
            return np.zeros_like(audio)

        self._lazy_load_model()
        text_query = ", ".join(prompts)
        logger.info("AudioSep open-vocabulary query: '%s'", text_query)

        tensor = torch.as_tensor(audio, dtype=torch.float32)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        elif tensor.shape[0] > tensor.shape[1]:
            tensor = tensor.transpose(0, 1)

        needs_resample = sample_rate != self.sr
        if needs_resample:
            tensor = torchaudio.functional.resample(tensor, orig_freq=sample_rate, new_freq=self.sr)

        is_stereo = tensor.shape[0] > 1
        tensor_mono = tensor.mean(dim=0, keepdim=True) if is_stereo else tensor
        tensor_mono = tensor_mono.to(self.device)

        with torch.no_grad():
            conditions = self.model.query_encoder.get_query_embed(  # type: ignore[union-attr]
                modality="text",
                text=[text_query],
                device=self.device,
            )
            input_dict = {"mixture": tensor_mono[None, :, :].to(self.device), "condition": conditions}
            sep_segment = self.model.ss_model(input_dict)["waveform"]  # type: ignore[union-attr]
            sep_audio_np = sep_segment.squeeze(0).squeeze(0).data.cpu().numpy()

        sep_tensor = torch.from_numpy(sep_audio_np).unsqueeze(0).to(tensor.device)
        if is_stereo:
            sep_tensor = sep_tensor.repeat(2, 1)
        if needs_resample:
            sep_tensor = torchaudio.functional.resample(sep_tensor, orig_freq=self.sr, new_freq=sample_rate)

        out = sep_tensor.cpu().numpy()
        target_len = audio_utils.get_target_length(audio)  # type: ignore[arg-type]
        if getattr(audio, "ndim", 1) == 1:
            return audio_utils.enforce_length(out[0], target_len)
        result = out.transpose(1, 0)
        return audio_utils.enforce_length(result, target_len)


__all__ = ["UniversalSeparator"]
