"""
Test Suite for Profiles and Control Logic
Tests for profile CRUD, auto-mode, safety override, and mode switching
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np

from profile_manager import ProfileManager, Profile
from auto_controller import AutoController
from safety_override import SafetyOverride, SafetyStatus
from control_engine import ControlEngine, ControlMode
from settings_store import SettingsStore


class TestProfileManager:
    """Test Profile Manager CRUD operations"""
    
    @pytest.fixture
    def temp_profiles_dir(self):
        """Create temporary profiles directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def profile_manager(self, temp_profiles_dir):
        """Create ProfileManager instance"""
        return ProfileManager(profiles_dir=temp_profiles_dir)
    
    def test_load_default_profiles(self, profile_manager):
        """Test loading default profiles"""
        profiles = profile_manager.get_all_profiles()
        assert len(profiles) >= 3
        
        # Check for default profiles
        profile_names = [p.name for p in profiles]
        assert 'Focus Mode' in profile_names
        assert 'Commute Mode' in profile_names
        assert 'Passthrough' in profile_names
    
    def test_create_profile(self, profile_manager):
        """Test creating a new profile"""
        gains = {'speech': 0.5, 'noise': 0.3, 'events': 0.4}
        suppressions = {'typing': True, 'wind': True}
        
        profile = profile_manager.create_profile(
            name='Test Mode',
            gains=gains,
            suppressions=suppressions,
            description='Test profile'
        )
        
        assert profile.name == 'Test Mode'
        assert profile.gains == gains
        assert profile.suppressions == suppressions
        assert profile.isSystemProfile is False
        
        # Verify it's in the list
        all_profiles = profile_manager.get_all_profiles()
        assert any(p.id == profile.id for p in all_profiles)
    
    def test_get_profile(self, profile_manager):
        """Test retrieving a profile"""
        profile = profile_manager.create_profile(
            name='Retrieve Test',
            gains={'speech': 0.5, 'noise': 0.5, 'events': 0.5}
        )
        
        retrieved = profile_manager.get_profile(profile.id)
        assert retrieved is not None
        assert retrieved.id == profile.id
        assert retrieved.name == 'Retrieve Test'
    
    def test_update_profile(self, profile_manager):
        """Test updating a profile"""
        profile = profile_manager.create_profile(
            name='Update Test',
            gains={'speech': 0.5, 'noise': 0.5, 'events': 0.5}
        )
        
        updated = profile_manager.update_profile(
            profile.id,
            name='Updated Name',
            gains={'speech': 0.8, 'noise': 0.2, 'events': 0.5}
        )
        
        assert updated.name == 'Updated Name'
        assert updated.gains['speech'] == 0.8
        assert updated.gains['noise'] == 0.2
    
    def test_cannot_update_system_profile(self, profile_manager):
        """Test that system profiles cannot be updated"""
        system_profile = profile_manager.get_system_profiles()[0]
        
        with pytest.raises(PermissionError):
            profile_manager.update_profile(
                system_profile.id,
                name='Modified'
            )
    
    def test_delete_profile(self, profile_manager):
        """Test deleting a profile"""
        profile = profile_manager.create_profile(
            name='Delete Test',
            gains={'speech': 0.5, 'noise': 0.5, 'events': 0.5}
        )
        
        profile_id = profile.id
        assert profile_manager.delete_profile(profile_id)
        
        # Verify it's deleted
        assert profile_manager.get_profile(profile_id) is None
    
    def test_cannot_delete_system_profile(self, profile_manager):
        """Test that system profiles cannot be deleted"""
        system_profile = profile_manager.get_system_profiles()[0]
        
        with pytest.raises(PermissionError):
            profile_manager.delete_profile(system_profile.id)
    
    def test_apply_profile(self, profile_manager):
        """Test applying a profile to get gains"""
        profile = profile_manager.create_profile(
            name='Apply Test',
            gains={'speech': 0.3, 'noise': 0.1, 'events': 0.2}
        )
        
        gains = profile_manager.apply_profile(profile)
        assert gains['speech'] == 0.3
        assert gains['noise'] == 0.1
        assert gains['events'] == 0.2
    
    def test_get_user_vs_system_profiles(self, profile_manager):
        """Test filtering user vs system profiles"""
        profile_manager.create_profile(
            name='User Profile',
            gains={'speech': 0.5, 'noise': 0.5, 'events': 0.5}
        )
        
        user_profiles = profile_manager.get_user_profiles()
        system_profiles = profile_manager.get_system_profiles()
        
        assert len(user_profiles) == 1
        assert len(system_profiles) >= 3
        assert all(p.isSystemProfile for p in system_profiles)


class TestAutoController:
    """Test Auto-Mode Controller"""
    
    @pytest.fixture
    def temp_profiles_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def auto_controller(self, temp_profiles_dir):
        pm = ProfileManager(profiles_dir=temp_profiles_dir)
        return AutoController(pm)
    
    def test_auto_controller_initialization(self, auto_controller):
        """Test AutoController initializes correctly"""
        assert auto_controller.profile_manager is not None
        assert auto_controller.current_profile is None
    
    def test_evaluate_no_triggers(self, auto_controller):
        """Test evaluation with no matching triggers"""
        detections = {'speech': 0.3, 'traffic': 0.2, 'wind': 0.1}
        profile = auto_controller.evaluate(detections)
        
        # No profiles have triggers, so no match
        assert profile is None
    
    def test_evaluate_with_triggers(self, auto_controller):
        """Test evaluation with matching triggers"""
        pm = auto_controller.profile_manager
        
        # Get commute profile which has traffic trigger
        commute = pm.get_profile('default-commute')
        assert commute is not None
        
        # Detections that match commute triggers
        detections = {'traffic': 0.7, 'wind': 0.3}
        profile = auto_controller.evaluate(detections)
        
        assert profile is not None
        assert profile.id == 'default-commute'
    
    def test_get_recommendation(self, auto_controller):
        """Test getting recommendation with reason"""
        detections = {'traffic': 0.75, 'wind': 0.2}
        
        recommendation = auto_controller.get_recommendation(detections)
        
        assert recommendation.profile is not None
        assert 'Traffic' in recommendation.reason or 'traffic' in recommendation.reason
        assert recommendation.confidence > 0
    
    def test_profile_match_score(self, auto_controller):
        """Test profile match scoring"""
        pm = auto_controller.profile_manager
        commute = pm.get_profile('default-commute')
        
        # High traffic
        detections_high = {'traffic': 0.8}
        score_high = auto_controller.get_profile_match_score(commute, detections_high)
        
        # Low traffic
        detections_low = {'traffic': 0.3}
        score_low = auto_controller.get_profile_match_score(commute, detections_low)
        
        assert score_high > score_low
    
    def test_all_profile_scores(self, auto_controller):
        """Test getting scores for all profiles"""
        detections = {'traffic': 0.7, 'wind': 0.3}
        scores = auto_controller.get_all_profile_scores(detections)
        
        # Should have some scores
        assert len(scores) > 0
        
        # Scores should be sorted descending
        for i in range(len(scores) - 1):
            assert scores[i][1] >= scores[i + 1][1]


class TestSafetyOverride:
    """Test Safety Override System"""
    
    @pytest.fixture
    def safety_override(self):
        return SafetyOverride(enable_alerts=False)
    
    def test_initialization(self, safety_override):
        """Test SafetyOverride initializes correctly"""
        assert safety_override.status == SafetyStatus.NORMAL
        assert not safety_override.is_active()
    
    def test_detect_siren(self, safety_override):
        """Test detecting siren sound"""
        detections = {'siren': 0.85, 'speech': 0.3}
        alert = safety_override.check(detections)
        
        assert alert.active
        assert alert.category == 'siren'
        assert alert.confidence == 0.85
    
    def test_detect_alarm(self, safety_override):
        """Test detecting alarm sound"""
        detections = {'alarm': 0.75, 'speech': 0.3}
        alert = safety_override.check(detections)
        
        assert alert.active
        assert alert.category == 'alarm'
    
    def test_no_critical_sound(self, safety_override):
        """Test normal operation without critical sounds"""
        detections = {'speech': 0.8, 'traffic': 0.3}
        alert = safety_override.check(detections)
        
        assert not alert.active
        assert alert.category is None
    
    def test_apply_override(self, safety_override):
        """Test applying safety override to gains"""
        current_gains = {'speech': 0.0, 'noise': 0.0, 'events': 0.0}
        detections = {'siren': 0.85, 'speech': 0.0}
        
        override_gains = safety_override.apply_override(current_gains, detections)
        
        # Events should be boosted to 1.0
        assert override_gains['events'] == 1.0
        
        # Other sounds should be ducked
        assert override_gains['speech'] <= 0.2
        assert override_gains['noise'] <= 0.2
    
    def test_override_threshold(self, safety_override):
        """Test that detection below threshold doesn't trigger override"""
        detections = {'siren': 0.6}  # Below 0.7 threshold
        alert = safety_override.check(detections)
        
        assert not alert.active
    
    def test_override_hold_time(self, safety_override):
        """Test override hold time after critical sound disappears"""
        import time
        
        # Trigger alert
        detections_with_siren = {'siren': 0.85}
        alert1 = safety_override.check(detections_with_siren)
        assert alert1.active
        
        # Alert disappears
        detections_without_siren = {'siren': 0.0}
        
        # Immediately after, should still be in hold time
        alert2 = safety_override.check(detections_without_siren)
        assert alert2.active
        
        # Status should be OVERRIDE_FADING
        assert safety_override.status == SafetyStatus.OVERRIDE_FADING
    
    def test_status_string(self, safety_override):
        """Test status string generation"""
        detections = {'siren': 0.85}
        safety_override.check(detections)
        
        status_str = safety_override.get_status_string()
        assert 'SAFETY ALERT' in status_str
        assert 'siren' in status_str.lower()


class TestControlEngine:
    """Test Control Engine Integration"""
    
    @pytest.fixture
    def temp_profiles_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def control_engine(self, temp_profiles_dir):
        pm = ProfileManager(profiles_dir=temp_profiles_dir)
        return ControlEngine(pm)
    
    def test_initialization(self, control_engine):
        """Test ControlEngine initializes correctly"""
        assert control_engine.mode == ControlMode.MANUAL
        assert control_engine.auto_controller is not None
        assert control_engine.safety_override is not None
    
    def test_set_mode(self, control_engine):
        """Test switching modes"""
        control_engine.set_mode(ControlMode.AUTO)
        assert control_engine.mode == ControlMode.AUTO
        
        control_engine.set_mode(ControlMode.MANUAL)
        assert control_engine.mode == ControlMode.MANUAL
    
    def test_set_gains(self, control_engine):
        """Test setting gains manually"""
        control_engine.set_gains(speech=0.5, noise=0.3, events=0.4)
        
        assert control_engine.current_gains['speech'] == 0.5
        assert control_engine.current_gains['noise'] == 0.3
        assert control_engine.current_gains['events'] == 0.4
    
    def test_apply_profile(self, control_engine):
        """Test applying a profile"""
        profile = control_engine.get_profile('default-focus')
        control_engine.apply_profile(profile)
        
        assert control_engine.current_profile.id == profile.id
        assert control_engine.current_gains == profile.gains
    
    def test_save_as_profile(self, control_engine):
        """Test saving current gains as a profile"""
        control_engine.set_gains(0.5, 0.3, 0.4)
        profile = control_engine.save_current_as_profile(
            'Custom Profile',
            description='Test custom'
        )
        
        assert profile.name == 'Custom Profile'
        assert profile.gains == {'speech': 0.5, 'noise': 0.3, 'events': 0.4}
    
    def test_on_detection_update_manual_mode(self, control_engine):
        """Test detection update in manual mode"""
        control_engine.set_mode(ControlMode.MANUAL)
        
        detections = {'speech': 0.8, 'traffic': 0.3}
        control_engine.on_detection_update(detections)
        
        assert control_engine.last_detections == detections
    
    def test_on_detection_update_auto_mode(self, control_engine):
        """Test detection update in auto mode"""
        control_engine.set_mode(ControlMode.AUTO)
        initial_profile = control_engine.current_profile
        
        # Trigger commute mode
        detections = {'traffic': 0.8}
        control_engine.on_detection_update(detections)
        
        # Should have switched to a profile with traffic trigger
        # (Note: commute mode has traffic trigger)
    
    def test_safety_override_in_detection(self, control_engine):
        """Test safety override during detection update"""
        control_engine.set_gains(speech=0.0, noise=0.0, events=0.0)
        
        # Siren detected
        detections = {'siren': 0.85, 'speech': 0.0}
        control_engine.on_detection_update(detections)
        
        # Should have applied override
        assert control_engine.safety_override.is_active()
        assert control_engine.current_gains['events'] == 1.0
    
    def test_bypass_model_check(self, control_engine):
        """Test passthrough detection"""
        gains = {'speech': 1.0, 'noise': 1.0, 'events': 1.0}
        assert control_engine.should_bypass_model(gains)
        
        gains_partial = {'speech': 0.5, 'noise': 1.0, 'events': 1.0}
        assert not control_engine.should_bypass_model(gains_partial)
    
    def test_silence_detection(self, control_engine):
        """Test silence detection"""
        # Silent buffer
        silent_buffer = np.zeros(1000)
        assert control_engine.is_silent(silent_buffer)
        
        # Non-silent buffer
        loud_buffer = np.ones(1000) * 0.5
        assert not control_engine.is_silent(loud_buffer)
    
    def test_get_state(self, control_engine):
        """Test getting control state"""
        control_engine.set_mode(ControlMode.AUTO)
        control_engine.set_gains(0.5, 0.3, 0.4)
        
        state = control_engine.get_state()
        assert state.mode == ControlMode.AUTO
        assert state.current_gains == {'speech': 0.5, 'noise': 0.3, 'events': 0.4}


class TestSettingsStore:
    """Test Settings Store Persistence"""
    
    @pytest.fixture
    def temp_config_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def settings_store(self, temp_config_dir):
        with patch('platformdirs.user_config_dir', return_value=str(temp_config_dir)):
            return SettingsStore()
    
    def test_initialization(self, settings_store):
        """Test SettingsStore initializes correctly"""
        assert settings_store.config_dir.exists()
        assert settings_store.profiles_dir.exists()
    
    def test_save_and_load_settings(self, settings_store):
        """Test saving and loading settings"""
        test_settings = {'mode': 'auto', 'custom_value': 123}
        settings_store.save_settings(test_settings)
        
        loaded = settings_store.load_settings()
        assert loaded['mode'] == 'auto'
        assert loaded['custom_value'] == 123
    
    def test_get_set_setting(self, settings_store):
        """Test getting and setting individual settings"""
        settings_store.set_setting('mode', 'auto')
        assert settings_store.get_setting('mode') == 'auto'
    
    def test_nested_settings(self, settings_store):
        """Test nested setting access"""
        settings_store.set_setting('window_geometry.x', 200)
        assert settings_store.get_setting('window_geometry.x') == 200
    
    def test_save_window_geometry(self, settings_store):
        """Test saving window geometry"""
        settings_store.save_window_geometry(100, 200, 800, 600)
        geometry = settings_store.get_window_geometry()
        
        assert geometry['x'] == 100
        assert geometry['y'] == 200
        assert geometry['width'] == 800
        assert geometry['height'] == 600


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
