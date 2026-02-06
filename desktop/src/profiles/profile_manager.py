"""
Profile Manager - CRUD operations for user suppression profiles.

Handles loading, saving, and managing both system and user-defined profiles.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from platformdirs import user_data_dir

logger = logging.getLogger(__name__)

APP_NAME = "SemanticMixer"
APP_AUTHOR = "SemanticMixer"

DEFAULT_PROFILES_PATH = (
    Path(__file__).resolve().parents[3] / "shared" / "profiles" / "default_profiles.json"
)


@dataclass
class AutoTrigger:
    """Automatic profile switching trigger."""
    category: str
    threshold: float


@dataclass
class Profile:
    """Suppression profile with metadata."""
    id: str
    name: str
    description: str
    suppressions: Dict[str, bool]
    schema_version: str = "1.0.0"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    auto_triggers: List[AutoTrigger] = field(default_factory=list)
    is_system_profile: bool = False

    @staticmethod
    def from_dict(data: dict) -> Profile:
        """Create Profile from dictionary."""
        triggers = [
            AutoTrigger(**t) if isinstance(t, dict) else t
            for t in data.get("autoTriggers", [])
        ]
        return Profile(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            suppressions=data.get("suppressions", {}),
            schema_version=data.get("schemaVersion", "1.0.0"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            auto_triggers=triggers,
            is_system_profile=data.get("isSystemProfile", False),
        )

    def to_dict(self) -> dict:
        """Convert Profile to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "schemaVersion": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "suppressions": self.suppressions,
            "autoTriggers": [
                {"category": t.category, "threshold": t.threshold}
                for t in self.auto_triggers
            ],
            "isSystemProfile": self.is_system_profile,
        }


class ProfileManager:
    """
    Manage suppression profiles.
    
    Usage:
        manager = ProfileManager()
        profiles = manager.get_all_profiles()
        manager.create_profile("My Profile", {"typing": True, "wind": True})
    """

    def __init__(self, profiles_dir: Optional[Path] = None):
        """
        Initialize profile manager.
        
        Args:
            profiles_dir: Custom directory for user profiles (default: platform-specific app data)
        """
        if profiles_dir is None:
            data_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))
            profiles_dir = data_dir / "profiles"
        
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        
        self.profiles: Dict[str, Profile] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load system and user profiles."""
        # Load system defaults
        if DEFAULT_PROFILES_PATH.exists():
            with DEFAULT_PROFILES_PATH.open("r", encoding="utf-8") as f:
                defaults = json.load(f)
            
            for data in defaults:
                profile = Profile.from_dict(data)
                self.profiles[profile.id] = profile
            
            logger.info(f"Loaded {len(defaults)} system profiles")

        # Load user profiles
        user_count = 0
        for file_path in self.profiles_dir.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                
                profile = Profile.from_dict(data)
                self.profiles[profile.id] = profile
                user_count += 1
            except Exception as e:
                logger.error(f"Failed to load profile {file_path}: {e}")
        
        if user_count > 0:
            logger.info(f"Loaded {user_count} user profiles")

    def get_all_profiles(self) -> List[Profile]:
        """Get all available profiles."""
        return list(self.profiles.values())

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        """Get profile by ID."""
        return self.profiles.get(profile_id)

    def create_profile(
        self,
        name: str,
        suppressions: Dict[str, bool],
        description: str = "",
        auto_triggers: Optional[List[AutoTrigger]] = None,
    ) -> Profile:
        """
        Create a new user profile.
        
        Args:
            name: Profile name
            suppressions: Dictionary of {category: enabled}
            description: Optional description
            auto_triggers: Optional list of auto-switching triggers
        
        Returns:
            Created Profile
        """
        now = datetime.utcnow().isoformat() + "Z"
        profile = Profile(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            suppressions=suppressions,
            created_at=now,
            updated_at=now,
            auto_triggers=auto_triggers or [],
            is_system_profile=False,
        )
        
        self.profiles[profile.id] = profile
        self._save_profile(profile)
        
        logger.info(f"Created profile: {name} ({profile.id})")
        return profile

    def update_profile(
        self,
        profile_id: str,
        name: Optional[str] = None,
        suppressions: Optional[Dict[str, bool]] = None,
        description: Optional[str] = None,
        auto_triggers: Optional[List[AutoTrigger]] = None,
    ) -> Optional[Profile]:
        """
        Update an existing profile.
        
        Cannot update system profiles.
        
        Returns:
            Updated Profile or None if profile not found or is system profile
        """
        profile = self.profiles.get(profile_id)
        if profile is None:
            logger.warning(f"Profile not found: {profile_id}")
            return None
        
        if profile.is_system_profile:
            logger.warning(f"Cannot update system profile: {profile.name}")
            return None
        
        # Update fields
        if name is not None:
            profile.name = name
        if suppressions is not None:
            profile.suppressions = suppressions
        if description is not None:
            profile.description = description
        if auto_triggers is not None:
            profile.auto_triggers = auto_triggers
        
        profile.updated_at = datetime.utcnow().isoformat() + "Z"
        
        self._save_profile(profile)
        logger.info(f"Updated profile: {profile.name} ({profile_id})")
        
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a user profile.
        
        Cannot delete system profiles.
        
        Returns:
            True if deleted, False if not found or is system profile
        """
        profile = self.profiles.get(profile_id)
        if profile is None:
            logger.warning(f"Profile not found: {profile_id}")
            return False
        
        if profile.is_system_profile:
            logger.warning(f"Cannot delete system profile: {profile.name}")
            return False
        
        # Remove from memory
        del self.profiles[profile_id]
        
        # Remove from disk
        file_path = self.profiles_dir / f"{profile_id}.json"
        if file_path.exists():
            file_path.unlink()
        
        logger.info(f"Deleted profile: {profile.name} ({profile_id})")
        return True

    def _save_profile(self, profile: Profile) -> None:
        """Save profile to disk (user profiles only)."""
        if profile.is_system_profile:
            return  # Don't save system profiles
        
        file_path = self.profiles_dir / f"{profile.id}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)


__all__ = ["ProfileManager", "Profile", "AutoTrigger"]
