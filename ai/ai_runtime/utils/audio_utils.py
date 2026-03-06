"""
Shared audio utility functions for processing and formatting.
"""

import numpy as np


def get_target_length(audio: np.ndarray) -> int:
    """
    Derive the temporal length (number of samples) from a 1D or 2D audio array.
    Correctly handles both channel-last (T, C) and channel-first (C, T) inputs
    by assuming that the larger dimension is time.
    """
    if audio.ndim == 1:
        return audio.shape[0]
    # In practically all audio use-cases, samples >> channels (e.g., 44100 vs 2)
    return max(audio.shape[0], audio.shape[1])


def enforce_length(audio: np.ndarray, target_len: int) -> np.ndarray:
    """
    Truncate or zero-pad an audio array to exactly match the target length.
    Expects (T,) or (T, C).
    """
    current_len = audio.shape[0]

    if current_len == target_len:
        return audio

    if audio.ndim == 1:
        if current_len > target_len:
            return audio[:target_len]
        padded = np.zeros(target_len, dtype=audio.dtype)
        padded[:current_len] = audio
        return padded

    # (T, C)
    if current_len > target_len:
        return audio[:target_len, :]
    num_channels = audio.shape[1]
    padded = np.zeros((target_len, num_channels), dtype=audio.dtype)
    padded[:current_len, :] = audio
    return padded
