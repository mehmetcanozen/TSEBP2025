"""Lightweight integration tests for core AI + profile wiring."""

from __future__ import annotations

import numpy as np

from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.profiles import ControlEngine, ControlMode, ProfileManager


def test_semantic_suppressor_minimal_path():
    sample_rate = 44100
    duration = 1.0
    samples = int(sample_rate * duration)
    t = np.linspace(0, duration, samples)
    noisy_audio = (0.5 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.random.randn(samples)).astype(np.float32)
    suppressor = SemanticSuppressor()
    clean_audio = suppressor.suppress(audio=noisy_audio, sample_rate=sample_rate, suppress_categories=[])
    assert clean_audio.shape == noisy_audio.shape


def test_profile_manager_create_delete():
    manager = ProfileManager()
    profile = manager.create_profile(
        name="Test Profile",
        description="Temporary test profile",
        suppressions={"typing": True, "wind": True},
    )
    assert manager.get_profile(profile.id) is not None
    assert manager.delete_profile(profile.id) is True


def test_control_engine_status():
    engine = ControlEngine()
    engine.set_mode(ControlMode.AUTO)
    engine.set_profile_by_id("default-focus")
    status = engine.get_status()
    assert status["mode"] in {"auto", "manual"}
    assert "profile" in status
