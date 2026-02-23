"""
Universal Audio Separator (Phase 3)

Wrapper for foundational audio separation models like AudioSep.
Allows extracting highly specific sounds purely using natural language 
prompts (e.g., "typing on a mechanical keyboard", "dog barking in distance").
"""

import logging
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import torch
import torchaudio

# Add project root to path for shared utils
from pathlib import Path
import sys
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from shared.utils import audio_utils

logger = logging.getLogger(__name__)


class UniversalSeparator:
    """
    Wrapper for an open-vocabulary target sound extractor like AudioSep.
    Bypasses the fixed 41-class limitation of Waveformer entirely.
    """
    
    def __init__(
        self, 
        model_dir: Optional[Union[str, Path]] = None,
        device: Optional[Union[str, torch.device]] = None
    ) -> None:
        """
        Initialize the Universal Separator.
        
        Args:
            model_dir: Path to the AudioSep installation/weights.
            device: Compute device ('cuda' or 'cpu')
        """
        self.device = torch.device(device) if device else self._auto_device()
        self.model_dir = Path(model_dir) if model_dir else Path("models/AudioSep")
        self.model = None
        self.sr = 32000 # AudioSep default operational sample rate
        
    def _auto_device(self) -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
        
    def _lazy_load_model(self):
        """Dynamically load the AudioSep model if it exists."""
        if self.model is not None:
            return
            
        repo_path = self.model_dir
        if not repo_path.exists():
            raise FileNotFoundError(
                f"AudioSep not found at {repo_path}. "
                "Please clone 'https://github.com/Audio-AGI/AudioSep' into this directory "
                "and download the checkpoints to use Universal Text-Prompt Separation."
            )
            
        # Dynamically add AudioSep to python path to import its pipeline
        import sys
        if str(repo_path) not in sys.path:
            sys.path.insert(0, str(repo_path))
            
        try:
            from pipeline import build_audiosep
            
            logger.info(f"Loading AudioSep model to {self.device}...")
            config_yaml = repo_path / "config" / "audiosep_base.yaml"
            checkpoint = repo_path / "checkpoint" / "audiosep_base_4M_steps.ckpt"
            
            if not checkpoint.exists():
                raise FileNotFoundError(f"Checkpoint not found at {checkpoint}")
                
            self.model = build_audiosep(
                config_yaml=str(config_yaml),
                checkpoint_path=str(checkpoint),
                device=self.device
            )
            logger.info("AudioSep ready!")
            
        except ImportError as e:
            raise ImportError(f"Failed to import AudioSep pipeline: {e}")
            
    def separate(
        self, 
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        prompts: List[str]
    ) -> np.ndarray:
        """
        Extract sounds matching the text prompts from the audio.
        
        Args:
            audio: Input audio mono or stereo (numpy array or tensor)
            sample_rate: Sample rate of input
            prompts: List of text prompts (e.g., ["typing", "fan noise"])
            
        Returns:
            Extracted noise audio matching the prompts (numpy array)
        """
        if not prompts:
            # If no prompts, return silence
            if isinstance(audio, torch.Tensor):
                return torch.zeros_like(audio).cpu().numpy()
            return np.zeros_like(audio)
            
        self._lazy_load_model()
        from pipeline import inference
        
        # Combine prompts for AudioSep (it supports multi-concept queries via "and" or ",")
        text_query = ", ".join(prompts)
        logger.info(f"Universal Extraction Query: '{text_query}'")
        
        # 1. Prepare tensor format (C, T)
        tensor = torch.as_tensor(audio, dtype=torch.float32)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        else:
            if tensor.shape[0] > tensor.shape[1]:
                tensor = tensor.transpose(0, 1)
                
        # 2. Resample to 32kHz for AudioSep and convert to Mono
        needs_resample = sample_rate != self.sr
        if needs_resample:
            tensor = torchaudio.functional.resample(tensor, orig_freq=sample_rate, new_freq=self.sr)
            
        is_stereo = tensor.shape[0] > 1
        if is_stereo:
            # AudioSep expects mono for core inference
            tensor_mono = tensor.mean(dim=0, keepdim=True)
        else:
            tensor_mono = tensor
            
        tensor_mono = tensor_mono.to(self.device)
        
        # 3. Use torch inference mode
        with torch.inference_mode():
            # Pass to inference pipeline (AudioSep expects numpy float32 mono audio)
            audio_np = tensor_mono.cpu().squeeze().numpy()
            sep_audio_np = inference(self.model, audio_np, text_query, device=self.device)
            
        # 4. Convert back to tensor and restore shape/sample rate
        sep_tensor = torch.from_numpy(sep_audio_np).unsqueeze(0).to(tensor.device)
        
        if is_stereo:
            # Duplicate mono extraction to both channels to match stereo input
            sep_tensor = sep_tensor.repeat(2, 1)
            
        if needs_resample:
            sep_tensor = torchaudio.functional.resample(sep_tensor, orig_freq=self.sr, new_freq=sample_rate)
            
        # Return cleanly shaped numpy array (T, C) or (T,)
        out = sep_tensor.cpu().numpy()
        
        target_len = audio_utils.get_target_length(audio)
        
        if audio.ndim == 1:
            return audio_utils.enforce_length(out[0], target_len)
        else:
            # Match original channel-last shape (T, C)
            result = out.transpose(1, 0)
            return audio_utils.enforce_length(result, target_len)
