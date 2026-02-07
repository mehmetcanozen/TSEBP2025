"""
Unit tests for ControlEngine - profile/control logic and safety overrides.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from profiles.control_engine import ControlEngine, ControlMode, SafetyStatus
from profiles.profile_manager import Profile, AutoTrigger


class FakeSuppressor:
    """Mock suppressor for testing."""
    def __init__(self):
        self.suppress_calls = []

    def suppress(self, audio, sample_rate, suppress_categories, safety_check=True):
        """Track suppression calls and return mock processed audio."""
        self.suppress_calls.append({
            "audio_shape": audio.shape,
            "sample_rate": sample_rate,
            "suppress_categories": suppress_categories,
            "safety_check": safety_check,
        })
        # Return slightly modified audio to verify processing occurred
        return audio * 0.9


class FakeProfileManager:
    """Mock profile manager for testing."""
    def __init__(self):
        self.profiles = {
            "default-passthrough": Profile(
                id="default-passthrough",
                name="Passthrough",
                description="No suppression",
                suppressions={},
                is_system_profile=True,
            ),
            "focus": Profile(
                id="focus",
                name="Focus Mode",
                description="Suppress typing and wind",
                suppressions={"typing": True, "wind": True},
                auto_triggers=[
                    AutoTrigger(category="typing", threshold=0.6),
                ],
                is_system_profile=True,
            ),
            "office": Profile(
                id="office",
                name="Office Mode",
                description="Suppress keyboard and chatter",
                suppressions={"typing": True, "chatter": True},
                auto_triggers=[
                    AutoTrigger(category="chatter", threshold=0.7),
                ],
                is_system_profile=True,
            ),
        }

    def get_profile(self, profile_id):
        """Get profile by ID."""
        return self.profiles.get(profile_id)

    def get_all_profiles(self):
        """Get all profiles."""
        return list(self.profiles.values())


@pytest.fixture
def engine():
    """Create ControlEngine with mocks."""
    profile_manager = FakeProfileManager()
    suppressor = FakeSuppressor()
    engine = ControlEngine(profile_manager=profile_manager, suppressor=suppressor)
    return engine


@pytest.fixture
def audio_buffer():
    """Create a simple audio buffer for testing."""
    return np.random.randn(16000).astype(np.float32)


def test_engine_initialization(engine):
    """Test that engine initializes with correct defaults."""
    assert engine.mode == ControlMode.MANUAL
    assert engine.current_profile is not None
    assert engine.current_profile.name == "Passthrough"
    assert not engine.safety_status.active


def test_set_mode(engine):
    """Test mode switching."""
    engine.set_mode(ControlMode.AUTO)
    assert engine.mode == ControlMode.AUTO

    engine.set_mode(ControlMode.MANUAL)
    assert engine.mode == ControlMode.MANUAL


def test_set_profile(engine):
    """Test manual profile setting."""
    focus_profile = engine.profile_manager.get_profile("focus")
    engine.set_profile(focus_profile)
    assert engine.current_profile.id == "focus"


def test_set_profile_by_id(engine):
    """Test setting profile by ID."""
    result = engine.set_profile_by_id("office")
    assert result is True
    assert engine.current_profile.id == "office"

    result = engine.set_profile_by_id("nonexistent")
    assert result is False


def test_passthrough_no_suppression(engine, audio_buffer):
    """Test that passthrough profile does not call suppressor."""
    passthrough = engine.profile_manager.get_profile("default-passthrough")
    engine.set_profile(passthrough)

    result = engine.process_audio(audio_buffer, 16000)

    # Passthrough should return original audio unchanged
    assert np.array_equal(result, audio_buffer)
    assert len(engine._suppressor.suppress_calls) == 0


def test_active_suppression(engine, audio_buffer):
    """Test that active profile calls suppressor with correct categories."""
    focus = engine.profile_manager.get_profile("focus")
    engine.set_profile(focus)

    result = engine.process_audio(audio_buffer, 16000)

    # Should have called suppressor
    assert len(engine._suppressor.suppress_calls) == 1
    call = engine._suppressor.suppress_calls[0]

    # Verify correct categories
    assert set(call["suppress_categories"]) == {"typing", "wind"}
    assert call["safety_check"] is True
    assert call["sample_rate"] == 16000

    # Verify audio was processed (scaled by 0.9 in FakeSuppressor)
    assert not np.array_equal(result, audio_buffer)
    assert np.allclose(result, audio_buffer * 0.9)


def test_safety_override_detection(engine):
    """Test safety override detection with critical sounds."""
    # No critical sounds
    detections = {"typing": 0.8, "wind": 0.5}
    status = engine._check_safety_override(detections)
    assert not status.active

    # Siren detected but below threshold
    detections = {"siren": 0.6, "typing": 0.8}
    status = engine._check_safety_override(detections)
    assert not status.active

    # Siren detected above threshold
    detections = {"siren": 0.8, "typing": 0.5}
    status = engine._check_safety_override(detections)
    assert status.active
    assert status.category == "siren"
    assert status.confidence == 0.8

    # Alarm detected above threshold
    detections = {"alarm": 0.9, "wind": 0.3}
    status = engine._check_safety_override(detections)
    assert status.active
    assert status.category == "alarm"
    assert status.confidence == 0.9


def test_safety_override_forces_passthrough(engine, audio_buffer):
    """Test that safety override switches to passthrough and suppression stops."""
    # Start with active suppression
    focus = engine.profile_manager.get_profile("focus")
    engine.set_profile(focus)

    # Trigger safety override with siren
    detections = {"siren": 0.85, "typing": 0.7}
    engine.on_detection_update(detections)

    # Should have switched to passthrough
    assert engine.current_profile.name == "Passthrough"
    assert engine.safety_status.active
    assert engine.safety_status.category == "siren"

    # Process audio - should NOT suppress
    result = engine.process_audio(audio_buffer, 16000)
    assert np.array_equal(result, audio_buffer)


def test_safety_override_clears(engine):
    """Test that safety override clears when critical sound stops."""
    # Activate safety override
    detections = {"siren": 0.85}
    engine.on_detection_update(detections)
    assert engine.safety_status.active

    # Clear siren - safety should clear
    detections = {"siren": 0.3, "typing": 0.6}
    engine.on_detection_update(detections)
    assert not engine.safety_status.active


def test_auto_mode_profile_switching(engine):
    """Test automatic profile switching based on detections."""
    engine.set_mode(ControlMode.AUTO)

    # Initially should be in passthrough
    assert engine.current_profile.name == "Passthrough"

    # Trigger focus mode (typing detected)
    detections = {"typing": 0.7, "wind": 0.3}
    engine.on_detection_update(detections)

    # Should switch to Focus mode
    assert engine.current_profile.name == "Focus Mode"

    # Trigger office mode (chatter detected with higher confidence)
    detections = {"typing": 0.5, "chatter": 0.8}
    engine.on_detection_update(detections)

    # Should switch to Office mode (higher score)
    assert engine.current_profile.name == "Office Mode"


def test_auto_mode_trigger_scoring(engine):
    """Test auto-mode profile selection uses correct scoring logic."""
    engine.set_mode(ControlMode.AUTO)

    # Both profiles triggered, but office has higher confidence
    detections = {"typing": 0.6, "chatter": 0.9}
    new_profile = engine._evaluate_auto_mode(detections)

    # Office should win (0.9 > 0.6)
    assert new_profile.name == "Office Mode"

    # Focus profile triggered with higher confidence
    detections = {"typing": 0.95, "chatter": 0.5}
    new_profile = engine._evaluate_auto_mode(detections)

    # Focus should win (0.95 > 0)
    assert new_profile.name == "Focus Mode"


def test_manual_mode_ignores_auto_triggers(engine):
    """Test that manual mode does not auto-switch profiles."""
    engine.set_mode(ControlMode.MANUAL)
    office = engine.profile_manager.get_profile("office")
    engine.set_profile(office)

    # Trigger focus mode detection
    detections = {"typing": 0.9, "wind": 0.5}
    engine.on_detection_update(detections)

    # Should stay in office mode (manual override)
    assert engine.current_profile.name == "Office Mode"


def test_concurrent_access_thread_safety(engine, audio_buffer):
    """Test that control engine handles concurrent access safely."""
    import threading

    focus = engine.profile_manager.get_profile("focus")

    results = []
    errors = []

    def process_audio_task():
        try:
            result = engine.process_audio(audio_buffer, 16000)
            results.append(result)
        except Exception as e:
            errors.append(e)

    def switch_profile_task():
        try:
            engine.set_profile(focus)
        except Exception as e:
            errors.append(e)

    # Launch multiple threads
    threads = []
    for _ in range(5):
        t1 = threading.Thread(target=process_audio_task)
        t2 = threading.Thread(target=switch_profile_task)
        threads.extend([t1, t2])

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    # Should complete without errors
    assert len(errors) == 0
    assert len(results) == 5


def test_empty_suppressions_bypasses_processing(engine, audio_buffer):
    """Test that profile with empty suppressions bypasses suppressor."""
    # Create profile with all suppressions disabled
    profile = Profile(
        id="test-empty",
        name="Empty",
        description="No active suppressions",
        suppressions={"typing": False, "wind": False},
    )
    engine.set_profile(profile)

    result = engine.process_audio(audio_buffer, 16000)

    # Should bypass suppressor and return original audio
    assert np.array_equal(result, audio_buffer)
    assert len(engine._suppressor.suppress_calls) == 0


def test_suppressor_error_returns_original_audio(engine, audio_buffer):
    """Test that suppressor errors are handled gracefully."""
    # Make suppressor raise exception
    def failing_suppress(*args, **kwargs):
        raise RuntimeError("Suppressor failure")

    engine._suppressor.suppress = failing_suppress

    focus = engine.profile_manager.get_profile("focus")
    engine.set_profile(focus)

    result = engine.process_audio(audio_buffer, 16000)

    # Should return original audio on error (fail-safe)
    assert np.array_equal(result, audio_buffer)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
