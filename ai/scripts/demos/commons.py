"""
Shared utilities for demo scripts.
"""

import logging

from ai.ai_runtime.profiles import ProfileManager


def setup_demo_logging() -> logging.Logger:
    """Configure logging and return a logger for the calling module."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    return logging.getLogger(__name__)


def create_custom_profile(
    manager: ProfileManager,
    suppress_categories: list[str],
    name: str = "Custom Realtime",
):
    """Create a custom profile with given suppression categories."""
    suppressions = {cat: True for cat in suppress_categories}
    return manager.create_profile(
        name=name,
        description=f"Suppress: {', '.join(suppress_categories)}",
        suppressions=suppressions,
    )


def mono_from_stereo(indata):
    """Convert stereo input to mono (mean of channels or first channel)."""
    import numpy as np
    if indata.ndim == 1:
        return indata
    if indata.shape[1] > 1:
        return indata.mean(axis=1).astype(indata.dtype)
    return indata[:, 0]
