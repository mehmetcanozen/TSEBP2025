"""
Speech Enhancer Wrapper for 'Suppress All' feature.
Uses DeepFilterNet for state-of-the-art voice extraction.
"""

from typing import Optional, Union
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

# PATCH for newer torchaudio versions (2.1+) to fix DeepFilterNet import
if not hasattr(torchaudio, 'backend'):
    import types
    import sys
    tb = types.ModuleType('torchaudio.backend')
    sys.modules['torchaudio.backend'] = tb
    torchaudio.backend = tb
    
    tbc = types.ModuleType('torchaudio.backend.common')
    class AudioMetaData:
        pass
    tbc.AudioMetaData = AudioMetaData
    sys.modules['torchaudio.backend.common'] = tbc
    tb.common = tbc
elif hasattr(torchaudio, 'backend') and not hasattr(torchaudio.backend, 'get_audio_backend'):
    def get_audio_backend():
        return "soundfile"
    torchaudio.backend.get_audio_backend = get_audio_backend

class SpeechEnhancer:
    def __init__(self, device: Optional[Union[str, torch.device]] = None) -> None:
        """
        Initialize the DeepFilterNet wrapper.
        """
        try:
            from df.enhance import init_df
        except ImportError as e:
            raise ImportError(
                f"DeepFilterNet not installed or failed to import: {e}. "
                "Please run `pip install deepfilternet`."
            )
        
        self.device = torch.device(device) if device else self._auto_device()
        
        # Load the default high-quality DeepFilterNet model
        self.model, self.df_state, _ = init_df()
        self.model = self.model.to(self.device).eval()
        
        # DeepFilterNet typically operates at 48kHz
        self.sr = self.df_state.sr()
        
        # Caches for torchaudio transforms
        self._resample_in = {}
        self._resample_out = {}

    def _auto_device(self) -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    def enhance(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Enhance speech (Suppress All noise) from the input audio.
        
        Args:
            audio: numpy array of shape (samples,) or (samples, channels)
            sample_rate: sampling rate of the input audio
            
        Returns:
            numpy array of the cleaned speech, at the original sample_rate
        """
        from df.enhance import enhance
        
        # 1. Prepare tensor (C, T)
        tensor = torch.as_tensor(audio, dtype=torch.float32)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        else:
            # Assume (T, C), convert to (C, T)
            if tensor.shape[0] > tensor.shape[1]:
                tensor = tensor.transpose(0, 1)
                
        # 2. Resample if necessary to DeepFilterNet's expected rate (48kHz)
        needs_resample = sample_rate != self.sr
        if needs_resample:
            if sample_rate not in self._resample_in:
                self._resample_in[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, new_freq=self.sr
                ).to(tensor.device)
            tensor = self._resample_in[sample_rate](tensor)
            
        # Do NOT move tensor to self.device here - DeepFilterNet `enhance` 
        # may expect it on CPU to run internal backend STFT preprocessing
        
        # 3. Enhance
        with torch.inference_mode():
            # DeepFilterNet enhance function
            enhanced_tensor = enhance(self.model, self.df_state, tensor)
            
        # 4. Resample back to original rate
        if needs_resample:
            enhanced_tensor = enhanced_tensor.cpu()
            if sample_rate not in self._resample_out:
                self._resample_out[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=self.sr, new_freq=sample_rate
                )
            enhanced_tensor = self._resample_out[sample_rate](enhanced_tensor)
            
        # Convert back to original shape (T, C) or (T,)
        out = enhanced_tensor.cpu().numpy()
        
        target_len = audio_utils.get_target_length(audio)
        
        if audio.ndim == 1:
            return audio_utils.enforce_length(out[0], target_len)
        else:
            # Match original channel-last shape (T, C)
            result = out.transpose(1, 0)
            return audio_utils.enforce_length(result, target_len)
