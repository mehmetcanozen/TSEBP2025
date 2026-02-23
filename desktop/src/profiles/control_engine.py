"""
Control Engine - Central coordinator for semantic noise suppression.

Integrates detection, profile management, and suppression logic.
Handles auto-mode, manual-mode, and safety overrides.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional

import numpy as np

from desktop.src.profiles.profile_manager import Profile, ProfileManager

# Lazy imports to avoid loading models at import time
if TYPE_CHECKING:
    from desktop.src.audio.semantic_suppressor import SemanticSuppressor

logger = logging.getLogger(__name__)


class ControlMode(Enum):
    """Control mode for the noise suppression system."""
    AUTO = "auto"  # Automatically select profile based on detections
    MANUAL = "manual"  # User manually selects profile


class SafetyStatus:
    """Safety override status."""
    def __init__(self, active: bool = False, category: str = "", confidence: float = 0.0):
        self.active = active
        self.category = category
        self.confidence = confidence


class ControlEngine:
    """
    Central control logic for semantic noise suppression.
    
    Responsibilities:
    - Coordinate detection → profile selection → suppression
    - Handle auto/manual mode switching
    - Enforce safety overrides (siren/alarm always pass through)
    - Manage passthrough bypass optimization
    
    Usage:
        engine = ControlEngine()
        engine.set_mode(ControlMode.AUTO)
        clean_audio = engine.process_audio(noisy_audio, 44100)
    
    Thread Safety:
        Most methods are thread-safe via internal locking.
        process_audio() can be called from audio thread.
    """

    def __init__(
        self,
        profile_manager: Optional[ProfileManager] = None,
        suppressor: Optional["SemanticSuppressor"] = None,
    ):
        """
        Initialize control engine.
        
        Args:
            profile_manager: Optional pre-initialized ProfileManager
            suppressor: Optional pre-initialized SemanticSuppressor
        """
        self.profile_manager = profile_manager or ProfileManager()
        self._suppressor = suppressor  # Store without initializing
        
        self.mode = ControlMode.MANUAL
        self.current_profile: Optional[Profile] = None
        self.safety_status = SafetyStatus()
        self._pre_safety_profile: Optional[Profile] = None # For restoration after override
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Set default profile (Passthrough)
        passthrough = self.profile_manager.get_profile("default-passthrough")
        if passthrough:
            self.set_profile(passthrough)
        
        logger.info("ControlEngine initialized")

    @property
    def suppressor(self) -> "SemanticSuppressor":
        """Lazy load suppressor only when needed."""
        if self._suppressor is None:
            # Import only when needed
            from desktop.src.audio.semantic_suppressor import SemanticSuppressor
            logger.info("Lazy loading SemanticSuppressor...")
            self._suppressor = SemanticSuppressor()
        return self._suppressor

    def set_mode(self, mode: ControlMode) -> None:
        """Switch between auto and manual mode."""
        with self._lock:
            self.mode = mode
            logger.info(f"Mode set to: {mode.value}")

    def set_profile(self, profile: Profile) -> None:
        """Manually set active profile."""
        with self._lock:
            self.current_profile = profile
            logger.info(f"Profile set to: {profile.name}")

    def set_profile_by_id(self, profile_id: str) -> bool:
        """
        Set profile by ID.
        
        Returns:
            True if profile found and set, False otherwise
        """
        profile = self.profile_manager.get_profile(profile_id)
        if profile:
            self.set_profile(profile)
            return True
        return False

    def process_audio(
        self,
        audio: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        """
        Process audio with semantic suppression based on current profile.
        
        Main entry point for audio processing pipeline.
        
        Args:
            audio: Input audio buffer
            sample_rate: Sample rate
        
        Returns:
            Processed audio
        """
        # Take a snapshot of the current profile and its suppressions under lock,
        # then release the lock before running the (potentially heavy) suppression
        # pipeline to avoid blocking other control operations.
        with self._lock:
            profile = self.current_profile
            if not profile:
                # No profile is passthrough
                return audio

            # Copy suppressions to avoid depending on shared mutable state outside the lock
            suppressions = dict(profile.suppressions) if profile.suppressions else {}

        # Check if passthrough mode (optimization)
        if not suppressions or all(not enabled for enabled in suppressions.values()):
            # No suppressions active, bypass processing
            return audio

        # Get active suppression categories
        active_suppressions = [
            category for category, enabled in suppressions.items()
            if enabled
        ]

        if not active_suppressions:
            return audio

        # Process with suppressor outside the lock to avoid blocking control operations
        try:
            clean_audio = self.suppressor.suppress(
                audio=audio,
                sample_rate=sample_rate,
                suppress_categories=active_suppressions,
                safety_check=True,  # Always enforce safety
            )
            return clean_audio
        except Exception as e:
            logger.error(f"Suppression failed: {e}", exc_info=True)
            # On error, return original audio (fail-safe)
            return audio

    def on_detection_update(self, detections: Dict[str, float]) -> None:
        """
        Called periodically by detection thread with latest sound detections.
        
        In AUTO mode, this triggers profile switching logic.
        In MANUAL mode, this is used for UI updates only.
        
        Args:
            detections: Dictionary of {category: confidence}
        """
        with self._lock:
            # Check safety override first
            safety = self._check_safety_override(detections)
            if safety.active:
                self.safety_status = safety
                logger.warning(
                    f"SAFETY OVERRIDE: {safety.category} detected "
                    f"(confidence: {safety.confidence:.2f})"
                )
                
                # Force passthrough profile
                passthrough = self.profile_manager.get_profile("default-passthrough")
                if passthrough and self.current_profile != passthrough:
                    logger.warning("Switching to Passthrough due to safety override")
                    # Store previous profile only if we aren't already in override
                    if not self.safety_status.active or not self._pre_safety_profile:
                        self._pre_safety_profile = self.current_profile
                    self.current_profile = passthrough
                
                return
            else:
                # Clear safety status if no longer active
                if self.safety_status.active:
                    logger.info("Safety override cleared")
                    self.safety_status = SafetyStatus()
                    
                    # Restore previous profile if possible
                    if self._pre_safety_profile:
                        logger.info(f"Restoring profile: {self._pre_safety_profile.name}")
                        self.current_profile = self._pre_safety_profile
                        self._pre_safety_profile = None
            
            # Auto-mode profile switching
            if self.mode == ControlMode.AUTO:
                new_profile = self._evaluate_auto_mode(detections)
                if new_profile and new_profile != self.current_profile:
                    logger.info(
                        f"Auto-mode switching: {self.current_profile.name if self.current_profile else 'None'} "
                        f"→ {new_profile.name}"
                    )
                    self.current_profile = new_profile

    def _check_safety_override(self, detections: Dict[str, float]) -> SafetyStatus:
        """
        Check if safety override should be triggered.
        
        Returns:
            SafetyStatus indicating if override is active
        """
        CRITICAL_CATEGORIES = ["siren", "alarm"]
        OVERRIDE_THRESHOLD = 0.7
        
        for category in CRITICAL_CATEGORIES:
            confidence = detections.get(category, 0.0)
            if confidence >= OVERRIDE_THRESHOLD:
                return SafetyStatus(
                    active=True,
                    category=category,
                    confidence=confidence,
                )
        
        return SafetyStatus(active=False)

    def _evaluate_auto_mode(self, detections: Dict[str, float]) -> Optional[Profile]:
        """
        Evaluate which profile should be active based on detections.
        
        Uses profile auto_triggers to determine best match.
        
        Returns:
            Best matching Profile or None
        """
        profiles = self.profile_manager.get_all_profiles()
        
        # Score each profile based on its triggers
        best_profile = None
        best_score = 0.0
        
        for profile in profiles:
            if not profile.auto_triggers:
                continue
            
            score = 0.0
            for trigger in profile.auto_triggers:
                confidence = detections.get(trigger.category, 0.0)
                if confidence >= trigger.threshold:
                    score += confidence
            
            if score > best_score:
                best_score = score
                best_profile = profile
        
        return best_profile

    def get_status(self) -> dict:
        """
        Get current engine status for UI display.
        
        Returns:
            Status dictionary
        """
        with self._lock:
            return {
                "mode": self.mode.value,
                "profile": self.current_profile.name if self.current_profile else None,
                "profile_id": self.current_profile.id if self.current_profile else None,
                "safety_active": self.safety_status.active,
                "safety_category": self.safety_status.category,
                "safety_confidence": self.safety_status.confidence,
            }


__all__ = ["ControlEngine", "ControlMode", "SafetyStatus"]
