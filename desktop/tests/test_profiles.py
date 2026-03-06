"""Desktop profile management and persistence tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ai.ai_runtime.profiles import ControlEngine, ControlMode, AutoTrigger, ProfileManager
from desktop.src.settings import SettingsStore


@pytest.fixture
def temp_profiles_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def profile_manager(temp_profiles_dir):
    return ProfileManager(profiles_dir=temp_profiles_dir)


def test_load_default_profiles(profile_manager):
    profiles = profile_manager.get_all_profiles()
    names = [p.name for p in profiles]
    assert len(profiles) >= 3
    assert "Focus Mode" in names
    assert "Commute Mode" in names
    assert "Passthrough" in names


def test_profile_crud_roundtrip(profile_manager):
    profile = profile_manager.create_profile(
        name="Custom",
        description="custom profile",
        suppressions={"typing": True, "wind": True},
        gains={"speech": 0.9, "noise": 0.2, "events": 0.5},
        auto_triggers=[AutoTrigger(category="typing", threshold=0.6)],
    )
    fetched = profile_manager.get_profile(profile.id)
    assert fetched is not None
    assert fetched.name == "Custom"

    updated = profile_manager.update_profile(
        profile.id,
        name="Custom Updated",
        suppressions={"typing": True},
        gains={"speech": 1.0, "noise": 0.1, "events": 0.4},
    )
    assert updated.name == "Custom Updated"
    assert updated.suppressions == {"typing": True}
    assert updated.gains["noise"] == 0.1

    assert profile_manager.delete_profile(profile.id) is True
    assert profile_manager.get_profile(profile.id) is None


def test_system_profile_protection(profile_manager):
    system_profile = profile_manager.get_system_profiles()[0]
    with pytest.raises(PermissionError):
        profile_manager.update_profile(system_profile.id, name="Blocked")
    with pytest.raises(PermissionError):
        profile_manager.delete_profile(system_profile.id)


def test_control_engine_mode_and_status(profile_manager):
    engine = ControlEngine(profile_manager=profile_manager)
    engine.set_mode(ControlMode.AUTO)
    assert engine.mode == ControlMode.AUTO
    engine.set_mode(ControlMode.MANUAL)
    assert engine.mode == ControlMode.MANUAL

    assert engine.set_profile_by_id("default-focus") is True
    status = engine.get_status()
    assert status["profile_id"] == "default-focus"
    assert status["mode"] == "manual"


def test_control_engine_auto_switch(profile_manager):
    engine = ControlEngine(profile_manager=profile_manager)
    engine.set_mode(ControlMode.AUTO)
    detections = {"traffic": 0.8, "typing": 0.3}
    engine.on_detection_update(detections)
    assert engine.current_profile is not None


def test_settings_store_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("platformdirs.user_config_dir", return_value=str(Path(tmpdir))):
            store = SettingsStore()
            store.save_settings({"mode": "auto", "custom_value": 123})
            loaded = store.load_settings()
            assert loaded["mode"] == "auto"
            assert loaded["custom_value"] == 123


def test_settings_store_nested_setting():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("platformdirs.user_config_dir", return_value=str(Path(tmpdir))):
            store = SettingsStore()
            store.set_setting("window_geometry.x", 200)
            assert store.get_setting("window_geometry.x") == 200
