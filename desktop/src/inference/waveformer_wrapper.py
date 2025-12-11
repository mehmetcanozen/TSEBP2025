"""
Desktop-friendly import shim for Waveformer separation.

Reuses the training-side `WaveformerSeparator` to avoid code drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import torchaudio

if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["sox_io"]

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_DIR = REPO_ROOT / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.append(str(TRAINING_DIR))

# Re-export the training wrapper
from models.audio_mixer import TARGETS, TARGET_SAMPLE_RATE, WaveformerSeparator  # type: ignore  # noqa: E402

__all__ = ["WaveformerSeparator", "TARGETS", "TARGET_SAMPLE_RATE"]
