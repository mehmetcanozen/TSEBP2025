"""
Profile Manager - Load, save, and manage user profiles
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import jsonschema
import platformdirs


class Profile:
    """Profile data class"""
    
    def __init__(self, data: Dict):
        self.id = data.get('id', str(uuid.uuid4()))
        self.name = data.get('name', 'Untitled')
        self.description = data.get('description', '')
        self.gains = data.get('gains', {'speech': 1.0, 'noise': 1.0, 'events': 1.0})
        self.suppressions = data.get('suppressions', {})
        self.autoTriggers = data.get('autoTriggers', [])
        self.learnedPriority = data.get('learnedPriority', 0)
        self.isDefault = data.get('isDefault', False)
        self.isSystemProfile = data.get('isSystemProfile', False)
        self.created_at = data.get('created_at', datetime.utcnow().isoformat() + 'Z')
        self.updated_at = data.get('updated_at', datetime.utcnow().isoformat() + 'Z')
        self.schemaVersion = data.get('schemaVersion', '1.0.0')
    
    def to_dict(self) -> Dict:
        """Convert profile to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'gains': self.gains,
            'suppressions': self.suppressions,
            'autoTriggers': self.autoTriggers,
            'learnedPriority': self.learnedPriority,
            'isDefault': self.isDefault,
            'isSystemProfile': self.isSystemProfile,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'schemaVersion': self.schemaVersion
        }
    
    def __repr__(self) -> str:
        return f"Profile(id={self.id}, name={self.name})"


class ProfileManager:
    """Manages loading, saving, and CRUD operations for profiles"""
    
    def __init__(self, profiles_dir: Optional[Path] = None, schema_path: Optional[Path] = None):
        """
        Initialize ProfileManager
        
        Args:
            profiles_dir: Directory to store user profiles. Defaults to platform-specific location
            schema_path: Path to profile_schema.json for validation
        """
        # Set up profiles directory
        if profiles_dir is None:
            app_config_dir = platformdirs.user_config_dir('SemanticMixer', 'SemanticMixer')
            profiles_dir = Path(app_config_dir) / 'profiles'
        
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        
        # Load schema for validation
        self.schema = None
        if schema_path and Path(schema_path).exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        
        # Load profiles
        self.profiles: Dict[str, Profile] = {}
        self._load_profiles()
    
    def _load_profiles(self):
        """Load default and user profiles"""
        # Load default profiles from bundled JSON
        self.profiles = self._load_default_profiles()
        
        # Load user-created profiles from disk
        user_profiles = self._load_user_profiles()
        self.profiles.update(user_profiles)
    
    def _load_default_profiles(self) -> Dict[str, Profile]:
        """Load built-in default profiles"""
        default_profiles = {}
        
        # Try to load from default_profiles.json
        try:
            # This would be bundled with the app
            default_data = [
                {
                    "id": "default-focus",
                    "name": "Focus Mode",
                    "description": "Block distractions, keep important sounds",
                    "gains": {"speech": 0.3, "noise": 0.0, "events": 0.2},
                    "suppressions": {"typing": True, "traffic": True, "wind": True},
                    "autoTriggers": [],
                    "learnedPriority": 0,
                    "isDefault": True,
                    "isSystemProfile": True,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "schemaVersion": "1.0.0"
                },
                {
                    "id": "default-commute",
                    "name": "Commute Mode",
                    "description": "Reduce engine noise, keep announcements",
                    "gains": {"speech": 1.0, "noise": 0.1, "events": 0.5},
                    "suppressions": {"traffic": True, "wind": True},
                    "autoTriggers": [{"category": "traffic", "threshold": 0.6}],
                    "learnedPriority": 0,
                    "isDefault": False,
                    "isSystemProfile": True,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "schemaVersion": "1.0.0"
                },
                {
                    "id": "default-passthrough",
                    "name": "Passthrough",
                    "description": "Hear everything (no processing)",
                    "gains": {"speech": 1.0, "noise": 1.0, "events": 1.0},
                    "suppressions": {},
                    "autoTriggers": [],
                    "learnedPriority": 0,
                    "isDefault": False,
                    "isSystemProfile": True,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "schemaVersion": "1.0.0"
                }
            ]
            
            for profile_data in default_data:
                profile = Profile(profile_data)
                default_profiles[profile.id] = profile
        
        except Exception as e:
            print(f"Warning: Could not load default profiles: {e}")
        
        return default_profiles
    
    def _load_user_profiles(self) -> Dict[str, Profile]:
        """Load user-created profiles from disk"""
        user_profiles = {}
        
        if not self.profiles_dir.exists():
            return user_profiles
        
        for profile_file in self.profiles_dir.glob('*.json'):
            try:
                with open(profile_file, 'r') as f:
                    data = json.load(f)
                
                # Validate if schema available
                if self.schema:
                    try:
                        jsonschema.validate(instance=data, schema=self.schema)
                    except jsonschema.ValidationError as e:
                        print(f"Warning: Profile {profile_file} failed validation: {e}")
                        continue
                
                profile = Profile(data)
                user_profiles[profile.id] = profile
            
            except Exception as e:
                print(f"Error loading profile {profile_file}: {e}")
        
        return user_profiles
    
    def get_all_profiles(self) -> List[Profile]:
        """Get all available profiles"""
        return list(self.profiles.values())
    
    def get_profile(self, profile_id: str) -> Optional[Profile]:
        """Get specific profile by ID"""
        return self.profiles.get(profile_id)
    
    def create_profile(self, name: str, gains: Dict, suppressions: Dict = None,
                       description: str = '') -> Profile:
        """
        Create a new profile
        
        Args:
            name: Profile name
            gains: Dictionary with 'speech', 'noise', 'events' keys (0-1 range)
            suppressions: Dictionary of sound categories to suppress
            description: Optional description
        
        Returns:
            Created Profile object
        """
        if suppressions is None:
            suppressions = {}
        
        profile_data = {
            'id': str(uuid.uuid4()),
            'name': name,
            'description': description,
            'gains': gains,
            'suppressions': suppressions,
            'autoTriggers': [],
            'learnedPriority': 0,
            'isDefault': False,
            'isSystemProfile': False,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'schemaVersion': '1.0.0'
        }
        
        # Validate
        if self.schema:
            try:
                jsonschema.validate(instance=profile_data, schema=self.schema)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Profile validation failed: {e}")
        
        profile = Profile(profile_data)
        
        # Save to disk
        self._save_profile_to_disk(profile)
        
        # Add to memory
        self.profiles[profile.id] = profile
        
        return profile
    
    def update_profile(self, profile_id: str, **kwargs) -> Optional[Profile]:
        """
        Update profile fields
        
        Args:
            profile_id: ID of profile to update
            **kwargs: Fields to update (name, gains, suppressions, etc.)
        
        Returns:
            Updated Profile or None if not found
        """
        profile = self.profiles.get(profile_id)
        if not profile:
            return None
        
        # Can't update system profiles
        if profile.isSystemProfile:
            raise PermissionError(f"Cannot update system profile: {profile.name}")
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.updated_at = datetime.utcnow().isoformat() + 'Z'
        
        # Validate and save
        if self.schema:
            try:
                jsonschema.validate(instance=profile.to_dict(), schema=self.schema)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Profile validation failed: {e}")
        
        self._save_profile_to_disk(profile)
        
        return profile
    
    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a profile
        
        Args:
            profile_id: ID of profile to delete
        
        Returns:
            True if deleted, False if not found
        """
        profile = self.profiles.get(profile_id)
        if not profile:
            return False
        
        # Can't delete system profiles
        if profile.isSystemProfile:
            raise PermissionError(f"Cannot delete system profile: {profile.name}")
        
        # Remove from disk
        profile_file = self.profiles_dir / f"{profile.id}.json"
        if profile_file.exists():
            profile_file.unlink()
        
        # Remove from memory
        del self.profiles[profile_id]
        
        return True
    
    def apply_profile(self, profile: Profile) -> Dict:
        """
        Convert profile to gain vector for Mixer
        
        Args:
            profile: Profile to apply
        
        Returns:
            Dictionary with gains: {"speech": 0.3, "noise": 0.0, "events": 0.2}
        """
        return {
            'speech': profile.gains.get('speech', 1.0),
            'noise': profile.gains.get('noise', 1.0),
            'events': profile.gains.get('events', 1.0)
        }
    
    def _save_profile_to_disk(self, profile: Profile):
        """Save profile to disk"""
        profile_file = self.profiles_dir / f"{profile.id}.json"
        
        with open(profile_file, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)
    
    def get_profiles_by_name(self, name: str) -> List[Profile]:
        """Get profiles by name (case-insensitive)"""
        name_lower = name.lower()
        return [p for p in self.profiles.values() if p.name.lower() == name_lower]
    
    def get_system_profiles(self) -> List[Profile]:
        """Get only system profiles"""
        return [p for p in self.profiles.values() if p.isSystemProfile]
    
    def get_user_profiles(self) -> List[Profile]:
        """Get only user-created profiles"""
        return [p for p in self.profiles.values() if not p.isSystemProfile]
