"""
Settings Store - Persist user settings between sessions
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import platformdirs
import shutil


class SettingsStore:
    """Manages persistent storage of user settings"""
    
    def __init__(self, app_name: str = 'SemanticMixer', app_author: str = 'SemanticMixer'):
        """
        Initialize SettingsStore
        
        Args:
            app_name: Application name
            app_author: Application author
        """
        self.app_name = app_name
        self.app_author = app_author
        
        # Get platform-specific config directory
        config_dir = platformdirs.user_config_dir(app_name, app_author)
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.settings_file = self.config_dir / 'settings.json'
        self.profiles_dir = self.config_dir / 'profiles'
        self.history_file = self.config_dir / 'history.json'
        self.backup_dir = self.config_dir / 'backups'
        
        # Create directories
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Default settings
        self.default_settings = {
            'version': '1.0.0',
            'mode': 'manual',
            'current_profile_id': None,
            'window_geometry': {
                'x': 100,
                'y': 100,
                'width': 800,
                'height': 600
            },
            'last_used_gains': {
                'speech': 1.0,
                'noise': 1.0,
                'events': 1.0
            },
            'ui_preferences': {
                'theme': 'dark',
                'language': 'en'
            }
        }
        
        # Load or create settings
        self.settings = self._load_or_create_settings()
    
    def save_settings(self, settings: Dict[str, Any]):
        """
        Save settings to disk
        
        Args:
            settings: Settings dictionary to save
        """
        try:
            # Create backup before saving
            if self.settings_file.exists():
                backup_file = self.backup_dir / f"settings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy(self.settings_file, backup_file)
            
            # Save new settings
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            
            self.settings = settings
            print(f"[SETTINGS] Settings saved to {self.settings_file}")
        
        except Exception as e:
            print(f"[SETTINGS] Error saving settings: {e}")
            raise
    
    def load_settings(self) -> Dict[str, Any]:
        """
        Load settings from disk
        
        Returns:
            Settings dictionary
        """
        return self.settings.copy()
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a specific setting
        
        Args:
            key: Setting key (supports dot notation: 'window_geometry.x')
            default: Default value if not found
        
        Returns:
            Setting value or default
        """
        if '.' in key:
            # Nested key like 'window_geometry.x'
            parts = key.split('.')
            value = self.settings
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return default
            return value if value is not None else default
        else:
            return self.settings.get(key, default)
    
    def set_setting(self, key: str, value: Any):
        """
        Set a specific setting
        
        Args:
            key: Setting key (supports dot notation)
            value: Value to set
        """
        if '.' in key:
            # Nested key like 'window_geometry.x'
            parts = key.split('.')
            settings = self.settings
            
            for part in parts[:-1]:
                if part not in settings:
                    settings[part] = {}
                settings = settings[part]
            
            settings[parts[-1]] = value
        else:
            self.settings[key] = value
        
        # Auto-save
        self.save_settings(self.settings)
    
    def save_window_geometry(self, x: int, y: int, width: int, height: int):
        """
        Save window geometry
        
        Args:
            x: Window X position
            y: Window Y position
            width: Window width
            height: Window height
        """
        self.set_setting('window_geometry', {
            'x': x,
            'y': y,
            'width': width,
            'height': height
        })
    
    def get_window_geometry(self) -> Dict[str, int]:
        """
        Get saved window geometry
        
        Returns:
            Geometry dictionary with x, y, width, height
        """
        return self.get_setting('window_geometry', self.default_settings['window_geometry'])
    
    def save_mode(self, mode: str):
        """
        Save current control mode
        
        Args:
            mode: 'auto' or 'manual'
        """
        self.set_setting('mode', mode)
    
    def get_mode(self) -> str:
        """
        Get saved control mode
        
        Returns:
            'auto' or 'manual'
        """
        return self.get_setting('mode', 'manual')
    
    def save_current_profile(self, profile_id: Optional[str]):
        """
        Save currently active profile ID
        
        Args:
            profile_id: Profile ID or None
        """
        self.set_setting('current_profile_id', profile_id)
    
    def get_current_profile(self) -> Optional[str]:
        """
        Get last active profile ID
        
        Returns:
            Profile ID or None
        """
        return self.get_setting('current_profile_id')
    
    def save_gains(self, gains: Dict[str, float]):
        """
        Save last used gains
        
        Args:
            gains: Gains dictionary
        """
        self.set_setting('last_used_gains', gains)
    
    def get_gains(self) -> Dict[str, float]:
        """
        Get last used gains
        
        Returns:
            Gains dictionary
        """
        return self.get_setting('last_used_gains', self.default_settings['last_used_gains'])
    
    def save_ui_preferences(self, theme: str = None, language: str = None):
        """
        Save UI preferences
        
        Args:
            theme: 'light', 'dark', or None
            language: Language code or None
        """
        prefs = self.get_setting('ui_preferences', {})
        
        if theme is not None:
            prefs['theme'] = theme
        if language is not None:
            prefs['language'] = language
        
        self.set_setting('ui_preferences', prefs)
    
    def get_ui_preferences(self) -> Dict[str, str]:
        """
        Get UI preferences
        
        Returns:
            UI preferences dictionary
        """
        return self.get_setting('ui_preferences', self.default_settings['ui_preferences'])
    
    def get_profiles_dir(self) -> Path:
        """
        Get profiles directory path
        
        Returns:
            Path to profiles directory
        """
        return self.profiles_dir
    
    def backup(self) -> Path:
        """
        Create timestamped backup of all settings and profiles
        
        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Backup settings
            if self.settings_file.exists():
                shutil.copy(self.settings_file, backup_path / 'settings.json')
            
            # Backup profiles
            if self.profiles_dir.exists():
                shutil.copytree(
                    self.profiles_dir,
                    backup_path / 'profiles',
                    dirs_exist_ok=True
                )
            
            # Backup history
            if self.history_file.exists():
                shutil.copy(self.history_file, backup_path / 'history.json')
            
            print(f"[SETTINGS] Backup created: {backup_path}")
            return backup_path
        
        except Exception as e:
            print(f"[SETTINGS] Error creating backup: {e}")
            raise
    
    def log_usage(self, event: str, data: Dict = None):
        """
        Log usage event for analytics
        
        Args:
            event: Event name
            data: Additional event data
        """
        try:
            # Load existing history
            history = []
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
            
            # Add new event
            event_entry = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'event': event,
                'data': data or {}
            }
            
            history.append(event_entry)
            
            # Keep only last 1000 events
            if len(history) > 1000:
                history = history[-1000:]
            
            # Save history
            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=2)
        
        except Exception as e:
            print(f"[SETTINGS] Error logging usage: {e}")
    
    def _load_or_create_settings(self) -> Dict[str, Any]:
        """Load settings from disk or create new ones"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                
                # Merge with defaults (in case new keys were added)
                merged = self.default_settings.copy()
                merged.update(settings)
                
                return merged
            
            except Exception as e:
                print(f"[SETTINGS] Error loading settings: {e}")
                print("[SETTINGS] Using default settings")
                return self.default_settings.copy()
        else:
            # Create new settings file with defaults
            self.save_settings(self.default_settings.copy())
            return self.default_settings.copy()
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        self.save_settings(self.default_settings.copy())
        print("[SETTINGS] Settings reset to defaults")
    
    def export_settings(self, output_path: Path):
        """
        Export settings to a file
        
        Args:
            output_path: Path to export to
        """
        with open(output_path, 'w') as f:
            json.dump(self.settings, f, indent=2)
        
        print(f"[SETTINGS] Settings exported to {output_path}")
    
    def import_settings(self, input_path: Path):
        """
        Import settings from a file
        
        Args:
            input_path: Path to import from
        """
        try:
            with open(input_path, 'r') as f:
                imported_settings = json.load(f)
            
            # Merge with existing settings
            merged = self.settings.copy()
            merged.update(imported_settings)
            
            self.save_settings(merged)
            print(f"[SETTINGS] Settings imported from {input_path}")
        
        except Exception as e:
            print(f"[SETTINGS] Error importing settings: {e}")
            raise
