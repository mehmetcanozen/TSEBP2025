"""
UI Controller - Bridge between UI and backend audio processing
"""

import threading
import queue
from typing import Optional, Callable, Dict, List
from enum import Enum


class DetectionUpdate:
    """Detection update message"""
    def __init__(self, detections: Dict[str, float]):
        self.detections = detections


class SafetyAlert:
    """Safety alert message"""
    def __init__(self, category: str, confidence: float):
        self.category = category
        self.confidence = confidence


class UIController:
    """Bridge between UI and audio processing backend"""
    
    def __init__(self):
        """Initialize controller"""
        self.profile_manager = None
        self.control_engine = None
        self.detective = None
        self.mixer = None
        
        # Communication queues
        self.ui_event_queue = queue.Queue()
        self.detection_queue = queue.Queue()
        self.safety_queue = queue.Queue()
        
        # Callbacks from UI components
        self.on_profile_list_update: Optional[Callable[[List[tuple]], None]] = None
        self.on_mode_changed: Optional[Callable[[str], None]] = None
        self.on_detections_update: Optional[Callable[[Dict], None]] = None
        self.on_safety_alert: Optional[Callable[[str, float], None]] = None
        self.on_safety_clear: Optional[Callable[[], None]] = None
        self.on_gains_update: Optional[Callable[[float, float, float], None]] = None
        
        # State
        self.is_running = False
        self.current_mode = 'manual'
    
    def initialize(self, profile_manager, control_engine, detective=None, mixer=None):
        """
        Initialize with backend components
        
        Args:
            profile_manager: ProfileManager instance
            control_engine: ControlEngine instance
            detective: Detective instance (optional)
            mixer: Mixer instance (optional)
        """
        self.profile_manager = profile_manager
        self.control_engine = control_engine
        self.detective = detective
        self.mixer = mixer
        
        # Setup control engine callbacks
        self.control_engine.on_profile_changed = self._on_profile_changed
        self.control_engine.on_mode_changed = self._on_mode_changed
        self.control_engine.on_gains_changed = self._on_gains_changed
        self.control_engine.on_safety_alert = self._on_safety_alert
        self.control_engine.on_detections_updated = self._on_detections_updated
        
        # Send initial profile list
        self._update_profile_list()
    
    def start(self):
        """Start the controller"""
        self.is_running = True
        self._start_event_processor()
    
    def stop(self):
        """Stop the controller"""
        self.is_running = False
    
    # UI Event Handlers
    
    def handle_slider_change(self, speech: float, noise: float, events: float):
        """
        Handle slider change from UI
        
        Args:
            speech: Speech gain (0-1)
            noise: Noise gain (0-1)
            events: Events gain (0-1)
        """
        if self.control_engine:
            # Switch to manual mode if not already
            if self.current_mode != 'manual':
                self.control_engine.set_mode('manual')
            
            # Set gains
            self.control_engine.set_gains(speech, noise, events)
    
    def handle_mode_change(self, mode: str):
        """
        Handle mode change from UI
        
        Args:
            mode: 'auto' or 'manual'
        """
        if self.control_engine:
            from control_engine import ControlMode
            mode_enum = ControlMode.AUTO if mode == 'auto' else ControlMode.MANUAL
            self.control_engine.set_mode(mode_enum)
            self.current_mode = mode
    
    def handle_profile_select(self, profile_id: str):
        """
        Handle profile selection from UI
        
        Args:
            profile_id: ID of profile to select
        """
        if self.control_engine:
            profile = self.profile_manager.get_profile(profile_id)
            if profile:
                self.control_engine.apply_profile(profile)
    
    def handle_save_profile(self, name: str, description: str = ''):
        """
        Handle save profile from UI
        
        Args:
            name: Profile name
            description: Profile description
        """
        if self.control_engine:
            profile = self.control_engine.save_current_as_profile(name, description)
            self._update_profile_list()
    
    def handle_delete_profile(self, profile_id: str):
        """
        Handle profile deletion from UI
        
        Args:
            profile_id: ID of profile to delete
        """
        if self.profile_manager:
            try:
                self.profile_manager.delete_profile(profile_id)
                self._update_profile_list()
            except Exception as e:
                print(f"Error deleting profile: {e}")
    
    def handle_safety_toggle(self, enabled: bool):
        """
        Handle safety override toggle
        
        Args:
            enabled: Whether safety is enabled
        """
        if self.control_engine:
            self.control_engine.safety_override.is_running = enabled
    
    def handle_mute_all(self):
        """Handle mute all button"""
        self.handle_slider_change(0.0, 0.0, 0.0)
    
    def handle_passthrough(self):
        """Handle passthrough button"""
        self.handle_slider_change(1.0, 1.0, 1.0)
    
    # Backend Event Handlers (called by control engine)
    
    def _on_profile_changed(self, profile, reason: str):
        """Called when profile changes"""
        if self.on_profile_list_update:
            self._update_profile_list()
    
    def _on_mode_changed(self, mode):
        """Called when mode changes"""
        from control_engine import ControlMode
        mode_str = 'auto' if mode == ControlMode.AUTO else 'manual'
        self.current_mode = mode_str
        if self.on_mode_changed:
            self.on_mode_changed(mode_str)
    
    def _on_gains_changed(self, gains: Dict):
        """Called when gains change"""
        if self.on_gains_update:
            self.on_gains_update(
                gains.get('speech', 1.0),
                gains.get('noise', 1.0),
                gains.get('events', 1.0)
            )
    
    def _on_safety_alert(self, alert_info: Dict):
        """Called when safety alert triggers"""
        if alert_info and alert_info.get('show_banner'):
            if self.on_safety_alert:
                self.on_safety_alert(
                    alert_info.get('category', 'unknown'),
                    alert_info.get('confidence', 0.0)
                )
    
    def _on_detections_updated(self, detections: Dict):
        """Called when detections update"""
        if self.on_detections_update:
            self.on_detections_update(detections)
    
    # Helper Methods
    
    def _update_profile_list(self):
        """Send updated profile list to UI"""
        if self.profile_manager and self.on_profile_list_update:
            profiles = self.profile_manager.get_all_profiles()
            profile_tuples = [(p.id, p.name) for p in profiles]
            self.on_profile_list_update(profile_tuples)
    
    def _start_event_processor(self):
        """Start background thread for processing events"""
        thread = threading.Thread(target=self._process_events_loop, daemon=True)
        thread.start()
    
    def _process_events_loop(self):
        """Background loop to process queued events"""
        while self.is_running:
            try:
                # Check for detection updates
                if not self.detection_queue.empty():
                    update = self.detection_queue.get_nowait()
                    if isinstance(update, DetectionUpdate):
                        self._on_detections_updated(update.detections)
                
                # Check for safety alerts
                if not self.safety_queue.empty():
                    alert = self.safety_queue.get_nowait()
                    if isinstance(alert, SafetyAlert):
                        self._on_safety_alert({
                            'category': alert.category,
                            'confidence': alert.confidence,
                            'show_banner': True
                        })
            
            except queue.Empty:
                pass
            except Exception as e:
                print(f"Error processing events: {e}")
            
            # Small sleep to avoid busy waiting
            threading.Event().wait(0.01)
    
    def get_current_gains(self) -> tuple:
        """Get current mixer gains"""
        if self.control_engine:
            gains = self.control_engine.current_gains
            return (
                gains.get('speech', 1.0),
                gains.get('noise', 1.0),
                gains.get('events', 1.0)
            )
        return (1.0, 1.0, 1.0)
    
    def get_current_mode(self) -> str:
        """Get current control mode"""
        return self.current_mode
    
    def get_profile_list(self) -> List[tuple]:
        """Get list of available profiles"""
        if self.profile_manager:
            profiles = self.profile_manager.get_all_profiles()
            return [(p.id, p.name) for p in profiles]
        return []
