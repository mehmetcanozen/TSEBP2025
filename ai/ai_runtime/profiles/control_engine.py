"""
Control Engine - Central coordinator for semantic noise suppression.

Integrates detection, profile management, and suppression logic.
Handles auto-mode and manual-mode.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional, Callable

import numpy as np

from ai.ai_runtime.profiles.profile_manager import Profile, ProfileManager

# Lazy imports to avoid loading models at import time
if TYPE_CHECKING:
    from ai.ai_runtime.suppression import SemanticSuppressor

logger = logging.getLogger(__name__)


class ControlMode(Enum):
    """Control mode for the noise suppression system."""
    AUTO = "auto"  # Automatically select profile based on detections
    MANUAL = "manual"  # User manually selects profile


class ControlEngine:
    """
    Central control logic for semantic noise suppression.

    Responsibilities:
    - Coordinate detection -> profile selection -> suppression
    - Handle auto/manual mode switching
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
        self._gains_override: Optional[Dict[str, float]] = None

        # Callbacks for UI updates
        self.on_profile_changed: Optional[Callable[[Profile, str], None]] = None
        self.on_gains_changed: Optional[Callable[[Dict], None]] = None
        self.on_mode_changed: Optional[Callable[[ControlMode], None]] = None
        self.on_detections_updated: Optional[Callable[[Dict], None]] = None

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
            from ai.ai_runtime.suppression import SemanticSuppressor
            logger.info("Lazy loading SemanticSuppressor...")
            self._suppressor = SemanticSuppressor()
        return self._suppressor

    def set_mode(self, mode: ControlMode) -> None:
        """Switch between auto and manual mode."""
        with self._lock:
            self.mode = mode
            logger.info(f"Mode set to: {mode.value}")
            if self.on_mode_changed:
                self.on_mode_changed(mode)

    def set_profile(self, profile: Profile) -> None:
        """Manually set active profile."""
        with self._lock:
            self.current_profile = profile
            self._gains_override = None
            logger.info(f"Profile set to: {profile.name}")
            if self.on_profile_changed:
                self.on_profile_changed(profile, "manual")
            if self.on_gains_changed:
                self.on_gains_changed(dict(profile.gains) if profile.gains else {})

    def apply_profile(self, profile: Profile) -> None:
        """Apply a profile (alias for set_profile for UI compatibility)."""
        self.set_profile(profile)

    def set_gains(self, speech: float, noise: float, events: float) -> None:
        """Set manual gain override (used when user adjusts sliders in manual mode)."""
        with self._lock:
            self._gains_override = {
                "speech": float(speech),
                "noise": float(noise),
                "events": float(events),
            }
            if self.on_gains_changed:
                self.on_gains_changed(self._gains_override)

    @property
    def current_gains(self) -> Dict[str, float]:
        """Get current gains (override or from profile)."""
        with self._lock:
            if self._gains_override:
                return dict(self._gains_override)
            if self.current_profile and self.current_profile.gains:
                return dict(self.current_profile.gains)
            return {"speech": 1.0, "noise": 1.0, "events": 1.0}

    def save_current_as_profile(self, name: str, description: str = "") -> Optional[Profile]:
        """Save current profile state as a new user profile."""
        with self._lock:
            profile = self.current_profile
            gains = self._gains_override or (profile.gains if profile else None) or {}
            suppressions = dict(profile.suppressions) if profile else {}
        return self.profile_manager.create_profile(
            name=name,
            gains=gains,
            suppressions=suppressions,
            description=description,
            suppression_params=(
                dict(profile.suppression_params)
                if profile and profile.suppression_params
                else None
            ),
        )

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
            kwargs = {
                "audio": audio,
                "sample_rate": sample_rate,
                "suppress_categories": active_suppressions,
            }
            if profile.suppression_params:
                allowed = {
                    "separator_backend",
                    "masking_method",
                    "detection_threshold",
                    "aggressiveness",
                    "audiosep_hive15cat_model_path",
                    "audiosep_hive15cat_device",
                    "audiosep_hive15cat_realtime_hop_seconds",
                    "codecsep_dnrv2_15cat_model_path",
                    "codecsep_dnrv2_15cat_runtime",
                    "codecsep_dnrv2_15cat_device",
                    "codecsep_dnrv2_15cat_realtime_hop_seconds",
                    "codecsep_checkpoint_path",
                    "codecsep_device",
                    "codecsep_prompt_overrides",
                    "codecsep_negative_prompts",
                    "codecsep_preserve_prompts",
                    "codecsep_mode",
                    "codecsep_query_strategy",
                    "codecsep_multistep_steps",
                    "codecsep_stereo_mode",
                    "codecsep_fixed_merge_policy",
                    "codecsep_product_categories",
                    "codecsep_hive_class_ids",
                    "universal_prompts",
                    "suppress_all",
                }
                for k, v in profile.suppression_params.items():
                    if k in allowed:
                        kwargs[k] = v
            clean_audio = self.suppressor.suppress(**kwargs)
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
            # Trigger UI updates if callback registered
            if self.on_detections_updated:
                self.on_detections_updated(detections)

            # Auto-mode profile switching
            if self.mode == ControlMode.AUTO:
                new_profile = self._evaluate_auto_mode(detections)
                if new_profile and new_profile != self.current_profile:
                    logger.info(
                        f"Auto-mode switching: {self.current_profile.name if self.current_profile else 'None'} "
                        f"-> {new_profile.name}"
                    )
                    self.current_profile = new_profile
                    if self.on_profile_changed:
                        self.on_profile_changed(new_profile, "auto")

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
            }


__all__ = ["ControlEngine", "ControlMode"]
