"""
Safety Override - Handle critical sound detection and override user settings
"""

from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum
import time


class SafetyStatus(Enum):
    """Safety override status"""
    NORMAL = "normal"
    OVERRIDE_ACTIVE = "override_active"
    OVERRIDE_FADING = "override_fading"


@dataclass
class SafetyAlert:
    """Safety alert information"""
    active: bool
    category: Optional[str]  # e.g., "siren", "alarm"
    confidence: float
    timestamp: float


class SafetyOverride:
    """Handles critical sound detection and safety overrides"""
    
    # Constants
    CRITICAL_CATEGORIES = ["siren", "alarm"]
    OVERRIDE_THRESHOLD = 0.7
    DUCK_AMOUNT = 0.2  # Reduce other audio to 20%
    HOLD_TIME = 5.0  # Hold override for 5 seconds after critical sound disappears
    
    def __init__(self, enable_alerts: bool = True):
        """
        Initialize SafetyOverride
        
        Args:
            enable_alerts: Whether to trigger alert notifications
        """
        self.enable_alerts = enable_alerts
        self.status = SafetyStatus.NORMAL
        self.current_alert: Optional[SafetyAlert] = None
        self.override_start_time: Optional[float] = None
        self.last_critical_detection_time: Optional[float] = None
    
    def check(self, detections: Dict[str, float]) -> SafetyAlert:
        """
        Check if critical sound is detected
        
        Args:
            detections: Current detection results
                       e.g. {"siren": 0.85, "alarm": 0.3, "speech": 0.6}
        
        Returns:
            SafetyAlert with detection status
        """
        current_time = time.time()
        active_alert = None
        highest_confidence = 0.0
        
        # Check for critical sounds
        for category in self.CRITICAL_CATEGORIES:
            confidence = detections.get(category, 0.0)
            
            if confidence >= self.OVERRIDE_THRESHOLD:
                if confidence > highest_confidence:
                    highest_confidence = confidence
                    active_alert = SafetyAlert(
                        active=True,
                        category=category,
                        confidence=confidence,
                        timestamp=current_time
                    )
                
                # Update last detection time
                self.last_critical_detection_time = current_time
        
        # If no active alert now, check if we're in hold time
        if active_alert is None:
            if self.last_critical_detection_time is not None:
                time_since_last = current_time - self.last_critical_detection_time
                
                if time_since_last < self.HOLD_TIME:
                    # Still in hold time
                    active_alert = SafetyAlert(
                        active=True,
                        category=None,  # Alert fading
                        confidence=1.0 - (time_since_last / self.HOLD_TIME),
                        timestamp=current_time
                    )
                    self.status = SafetyStatus.OVERRIDE_FADING
                else:
                    # Hold time expired
                    active_alert = SafetyAlert(
                        active=False,
                        category=None,
                        confidence=0.0,
                        timestamp=current_time
                    )
                    self.status = SafetyStatus.NORMAL
        else:
            # Alert is active
            self.status = SafetyStatus.OVERRIDE_ACTIVE
            if self.enable_alerts and self.override_start_time is None:
                # First time alert triggers - trigger notifications
                self._trigger_alerts(active_alert)
            
            self.override_start_time = current_time
        
        self.current_alert = active_alert
        return active_alert
    
    def apply_override(self, current_gains: Dict[str, float], 
                       detections: Dict[str, float]) -> Dict[str, float]:
        """
        Apply safety override to gains if critical sound detected
        
        Args:
            current_gains: Current user gains {"speech": 0.3, "noise": 0.0, "events": 0.2}
            detections: Current detections for checking critical sounds
        
        Returns:
            Modified gains with safety override applied if needed
        """
        # Check for critical sounds
        alert = self.check(detections)
        
        if not alert.active:
            # No override needed
            return current_gains
        
        # Find which critical sound to boost
        critical_sound = None
        for category in self.CRITICAL_CATEGORIES:
            if detections.get(category, 0.0) >= self.OVERRIDE_THRESHOLD:
                critical_sound = category
                break
        
        if critical_sound is None:
            # In hold time, just return original gains
            return current_gains
        
        # Apply override: boost critical, duck others
        modified_gains = current_gains.copy()
        
        # Boost the critical sound category
        if critical_sound == "siren" or critical_sound == "alarm":
            # These are "events" category sounds
            modified_gains['events'] = 1.0
        
        # Duck other sounds to DUCK_AMOUNT
        for key in modified_gains:
            if key != 'events':
                modified_gains[key] = min(
                    modified_gains[key],
                    self.DUCK_AMOUNT
                )
        
        return modified_gains
    
    def _trigger_alerts(self, alert: SafetyAlert):
        """
        Trigger alert notifications
        
        Args:
            alert: SafetyAlert to trigger
        """
        if alert.category:
            self._flash_window()
            self._play_alert_sound()
            self._log_override_event(alert)
    
    def _flash_window(self):
        """Flash window red (desktop implementation)"""
        # This would be implemented in the UI layer
        pass
    
    def _play_alert_sound(self):
        """Play alert sound (optional)"""
        # This would be implemented in the audio layer
        pass
    
    def _log_override_event(self, alert: SafetyAlert):
        """Log the override event"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', 
                                 time.localtime(alert.timestamp))
        print(f"[SAFETY] Override triggered: {alert.category} "
              f"({alert.confidence:.0%}) at {timestamp}")
    
    def reset(self):
        """Reset override state"""
        self.status = SafetyStatus.NORMAL
        self.current_alert = None
        self.override_start_time = None
        self.last_critical_detection_time = None
    
    def is_active(self) -> bool:
        """Check if override is currently active"""
        if self.current_alert is None:
            return False
        return self.current_alert.active
    
    def get_status_string(self) -> str:
        """Get human-readable status"""
        if not self.is_active():
            return "Normal"
        
        if self.current_alert.category:
            return f"⚠️ SAFETY ALERT: {self.current_alert.category.upper()} detected ({self.current_alert.confidence:.0%})"
        else:
            return f"⚠️ Safety override fading... ({self.current_alert.confidence:.0%})"
    
    def get_alert_info(self) -> Optional[Dict]:
        """Get current alert information for UI display"""
        if not self.current_alert or not self.current_alert.active:
            return None
        
        return {
            'type': 'critical_sound',
            'category': self.current_alert.category,
            'confidence': self.current_alert.confidence,
            'message': self.get_status_string(),
            'show_banner': self.current_alert.category is not None  # Show banner for active alerts
        }


# State Machine for reference:
# 
# ┌──────────────────────────────────────────┐
# │  NORMAL  ─────(siren detected)─────►  OVERRIDE_ACTIVE
# │    ▲                                    │
# │    │                                    ▼
# │    │                              OVERRIDE_FADING
# │    │                                    │
# │    └─────(5 sec hold time)───────────────┘
# └──────────────────────────────────────────┘
