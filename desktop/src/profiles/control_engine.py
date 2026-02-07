"""
Control Engine - Central coordinator for all control logic
"""

from typing import Dict, Optional, Callable, List
from enum import Enum
import numpy as np
from dataclasses import dataclass

from profile_manager import ProfileManager, Profile
from auto_controller import AutoController
from safety_override import SafetyOverride


class ControlMode(Enum):
    """Control mode"""
    AUTO = "auto"
    MANUAL = "manual"


@dataclass
class ControlState:
    """Current control engine state"""
    mode: ControlMode
    current_profile: Optional[Profile]
    current_gains: Dict[str, float]
    safety_active: bool
    last_detections: Dict[str, float]


class ControlEngine:
    """Central coordinator for all control logic"""
    
    def __init__(self, profile_manager: ProfileManager, mixer=None, detective=None):
        """
        Initialize ControlEngine
        
        Args:
            profile_manager: ProfileManager instance
            mixer: Mixer instance (optional for integration)
            detective: Detective instance (optional for integration)
        """
        self.profile_manager = profile_manager
        self.mixer = mixer
        self.detective = detective
        
        # Initialize sub-modules
        self.auto_controller = AutoController(profile_manager)
        self.safety_override = SafetyOverride(enable_alerts=True)
        
        # State
        self.mode = ControlMode.MANUAL
        self.current_profile: Optional[Profile] = None
        self.current_gains: Dict[str, float] = {
            'speech': 1.0,
            'noise': 1.0,
            'events': 1.0
        }
        self.last_detections: Dict[str, float] = {}
        
        # Callbacks for UI updates
        self.on_profile_changed: Optional[Callable[[Profile, str], None]] = None
        self.on_gains_changed: Optional[Callable[[Dict], None]] = None
        self.on_mode_changed: Optional[Callable[[ControlMode], None]] = None
        self.on_safety_alert: Optional[Callable[[Dict], None]] = None
        self.on_detections_updated: Optional[Callable[[Dict], None]] = None
        
        # Load last used settings
        self._load_saved_settings()
    
    def set_mode(self, mode: ControlMode):
        """
        Switch between auto and manual modes
        
        Args:
            mode: ControlMode.AUTO or ControlMode.MANUAL
        """
        if mode == self.mode:
            return  # Already in this mode
        
        self.mode = mode
        
        if self.mode == ControlMode.AUTO:
            # When switching to auto, start with a default profile
            if self.current_profile is None:
                default = self._get_default_profile()
                if default:
                    self.apply_profile(default)
        
        # Notify UI
        if self.on_mode_changed:
            self.on_mode_changed(self.mode)
        
        print(f"[CONTROL] Mode switched to: {mode.value}")
    
    def on_detection_update(self, detections: Dict[str, float]):
        """
        Called when Detective has new detection results
        
        This is the main control flow:
        1. Check safety override first
        2. If auto mode and no safety: Evaluate profiles
        3. Apply to mixer if available
        
        Args:
            detections: Detection results from Detective
                       e.g. {"speech": 0.8, "traffic": 0.6, "wind": 0.1}
        """
        self.last_detections = detections.copy()
        
        # Step 1: Check safety override first
        alert = self.safety_override.check(detections)
        
        if alert.active:
            # Apply safety override gains
            override_gains = self.safety_override.apply_override(
                self.current_gains, 
                detections
            )
            self._apply_gains(override_gains, apply_to_mixer=True)
            
            # Alert UI
            alert_info = self.safety_override.get_alert_info()
            if alert_info and self.on_safety_alert:
                self.on_safety_alert(alert_info)
            
            # Notify UI of detections
            if self.on_detections_updated:
                self.on_detections_updated(detections)
            
            print(f"[CONTROL] Safety override active: {alert.category}")
            return
        
        # Step 2: If auto mode, evaluate profiles
        if self.mode == ControlMode.AUTO:
            recommendation = self.auto_controller.get_recommendation(detections)
            
            if recommendation.profile is not None:
                # Check if we should switch
                should_switch = self.auto_controller.should_switch_profile(
                    recommendation.profile,
                    self.current_profile
                )
                
                if should_switch:
                    self.apply_profile(recommendation.profile)
                    
                    # Notify UI
                    if self.on_profile_changed:
                        self.on_profile_changed(
                            recommendation.profile,
                            recommendation.reason
                        )
                    
                    print(f"[CONTROL] Auto-switched to '{recommendation.profile.name}': "
                          f"{recommendation.reason}")
        
        # Step 3: Notify UI of detections
        if self.on_detections_updated:
            self.on_detections_updated(detections)
    
    def apply_profile(self, profile: Profile):
        """
        Apply a profile (set gains and suppressions)
        
        Args:
            profile: Profile to apply
        """
        if profile is None:
            return
        
        self.current_profile = profile
        
        # Extract gains from profile
        gains = self.profile_manager.apply_profile(profile)
        self._apply_gains(gains, apply_to_mixer=True)
        
        print(f"[CONTROL] Profile applied: {profile.name}")
    
    def set_gains(self, speech: float, noise: float, events: float):
        """
        Manually set gains (switches to manual mode if not already)
        
        Args:
            speech: Speech gain (0-1)
            noise: Noise gain (0-1)
            events: Events gain (0-1)
        """
        gains = {
            'speech': np.clip(speech, 0.0, 1.0),
            'noise': np.clip(noise, 0.0, 1.0),
            'events': np.clip(events, 0.0, 1.0)
        }
        
        # Switch to manual mode if not already
        if self.mode != ControlMode.MANUAL:
            self.set_mode(ControlMode.MANUAL)
        
        self._apply_gains(gains, apply_to_mixer=True)
        
        print(f"[CONTROL] Gains updated: speech={speech:.2f}, "
              f"noise={noise:.2f}, events={events:.2f}")
    
    def _apply_gains(self, gains: Dict[str, float], apply_to_mixer: bool = False):
        """
        Internal method to apply gains
        
        Args:
            gains: Gains dictionary
            apply_to_mixer: Whether to send to mixer
        """
        self.current_gains = gains
        
        # Apply to mixer if available
        if apply_to_mixer and self.mixer:
            self.mixer.set_gains(
                gains.get('speech', 1.0),
                gains.get('noise', 1.0),
                gains.get('events', 1.0)
            )
        
        # Notify UI
        if self.on_gains_changed:
            self.on_gains_changed(gains)
    
    def save_current_as_profile(self, name: str, description: str = '') -> Profile:
        """
        Save current gains as a new custom profile
        
        Args:
            name: Name for the new profile
            description: Optional description
        
        Returns:
            Created Profile
        """
        profile = self.profile_manager.create_profile(
            name=name,
            gains=self.current_gains,
            description=description
        )
        
        print(f"[CONTROL] Saved profile: {name}")
        return profile
    
    def get_state(self) -> ControlState:
        """Get current control state"""
        return ControlState(
            mode=self.mode,
            current_profile=self.current_profile,
            current_gains=self.current_gains,
            safety_active=self.safety_override.is_active(),
            last_detections=self.last_detections
        )
    
    def _get_default_profile(self) -> Optional[Profile]:
        """Get default profile"""
        profiles = self.profile_manager.get_all_profiles()
        
        # Look for a default profile
        for profile in profiles:
            if profile.isDefault:
                return profile
        
        # Otherwise return first profile
        return profiles[0] if profiles else None
    
    def _load_saved_settings(self):
        """Load last-used settings from storage"""
        # This would be implemented with settings_store
        # For now, just set defaults
        default_profile = self._get_default_profile()
        if default_profile:
            self.apply_profile(default_profile)
    
    def get_all_profiles(self) -> List[Profile]:
        """Get all available profiles"""
        return self.profile_manager.get_all_profiles()
    
    def get_profile(self, profile_id: str) -> Optional[Profile]:
        """Get specific profile by ID"""
        return self.profile_manager.get_profile(profile_id)
    
    def create_profile(self, name: str, gains: Dict, suppressions: Dict = None,
                      description: str = '') -> Profile:
        """Create a new profile"""
        return self.profile_manager.create_profile(
            name=name,
            gains=gains,
            suppressions=suppressions or {},
            description=description
        )
    
    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile"""
        return self.profile_manager.delete_profile(profile_id)
    
    def update_profile(self, profile_id: str, **kwargs) -> Optional[Profile]:
        """Update a profile"""
        return self.profile_manager.update_profile(profile_id, **kwargs)
    
    def should_bypass_model(self, gains: Dict[str, float]) -> bool:
        """
        Check if we should bypass expensive inference (battery saver)
        
        If all gains are at 100%, we're in passthrough mode.
        Just copy input buffer to output - skip expensive inference!
        
        Args:
            gains: Current gains
        
        Returns:
            True if should bypass model
        """
        PASSTHROUGH_THRESHOLD = 0.99
        
        is_passthrough = (
            gains.get('speech', 0) > PASSTHROUGH_THRESHOLD and
            gains.get('noise', 0) > PASSTHROUGH_THRESHOLD and
            gains.get('events', 0) > PASSTHROUGH_THRESHOLD
        )
        
        return is_passthrough
    
    def is_silent(self, audio_buffer: np.ndarray, threshold: float = 0.01) -> bool:
        """
        Use simple energy detection to check if room is silent
        
        Args:
            audio_buffer: Audio samples
            threshold: Energy threshold
        
        Returns:
            True if audio is silent
        """
        energy = np.mean(np.abs(audio_buffer))
        return energy < threshold
    
    def process_audio_optimization(self, input_buffer: np.ndarray) -> Optional[np.ndarray]:
        """
        Determine if we should skip expensive processing
        
        Returns None if normal processing should happen,
        or the output buffer if we're bypassing/silencing
        
        Args:
            input_buffer: Input audio
        
        Returns:
            None (process normally), copy of input (passthrough), or zeros (silence)
        """
        # Check for silence first
        if self.is_silent(input_buffer):
            print("[AUDIO] Silence detected - skipping inference")
            return np.zeros_like(input_buffer)
        
        # Check for passthrough
        if self.should_bypass_model(self.current_gains):
            print("[AUDIO] Passthrough mode - skipping inference")
            return input_buffer.copy()
        
        # Normal processing
        return None


# Integration Flow Diagram:
#
# ┌─────────────────────────────────────────────────┐
# │                  ControlEngine                  │
# ├─────────────────────────────────────────────────┤
# │                                                 │
# │  Detective ──► on_detection_update()            │
# │                      │                          │
# │                      ▼                          │
# │            ┌─────────────────┐                  │
# │            │ Safety Override │                  │
# │            └────────┬────────┘                  │
# │                     │ (if not triggered)        │
# │                     ▼                           │
# │            ┌─────────────────┐                  │
# │            │   Auto Mode?    │                  │
# │            └────────┬────────┘                  │
# │           Yes       │        No                 │
# │            ▼        │         ▼                 │
# │    AutoController   │    Manual Gains           │
# │            │        │         │                 │
# │            └────────┴─────────┘                 │
# │                     │                           │
# │                     ▼                           │
# │               Apply to Mixer                    │
# │                                                 │
# └─────────────────────────────────────────────────┘
