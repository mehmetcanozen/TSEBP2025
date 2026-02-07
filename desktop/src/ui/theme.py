"""
Theme definitions for Semantic Mixer UI
Supports dark, light, and high contrast themes
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class ThemeColors:
    """Theme color palette"""
    bg_primary: str
    bg_secondary: str
    accent: str
    text: str
    text_secondary: str
    success: str
    warning: str
    danger: str
    slider_speech: str
    slider_noise: str
    slider_events: str
    border: str


class Theme:
    """Theme manager for the application"""
    
    DARK = ThemeColors(
        bg_primary='#1a1a2e',
        bg_secondary='#16213e',
        accent='#0f3460',
        text='#e8e8e8',
        text_secondary='#b0b0b0',
        success='#4ecca3',
        warning='#ff9a00',
        danger='#ff2e63',
        slider_speech='#4ecca3',      # Green
        slider_noise='#808080',        # Gray
        slider_events='#ff9a00',       # Orange
        border='#333333'
    )
    
    LIGHT = ThemeColors(
        bg_primary='#f5f5f5',
        bg_secondary='#ffffff',
        accent='#0066cc',
        text='#1a1a1a',
        text_secondary='#666666',
        success='#0099cc',
        warning='#ff9900',
        danger='#cc0000',
        slider_speech='#0099cc',       # Blue
        slider_noise='#999999',        # Gray
        slider_events='#ff6600',       # Orange
        border='#cccccc'
    )
    
    HIGH_CONTRAST = ThemeColors(
        bg_primary='#000000',
        bg_secondary='#ffffff',
        accent='#ffff00',
        text='#ffffff',
        text_secondary='#cccccc',
        success='#00ff00',
        warning='#ffff00',
        danger='#ff0000',
        slider_speech='#00ff00',
        slider_noise='#cccccc',
        slider_events='#ffff00',
        border='#ffffff'
    )
    
    @staticmethod
    def get_theme(name: str) -> ThemeColors:
        """Get theme by name"""
        themes = {
            'dark': Theme.DARK,
            'light': Theme.LIGHT,
            'high_contrast': Theme.HIGH_CONTRAST
        }
        return themes.get(name, Theme.DARK)
    
    @staticmethod
    def get_all_themes() -> Dict[str, str]:
        """Get all available themes"""
        return {
            'dark': 'Dark Mode',
            'light': 'Light Mode',
            'high_contrast': 'High Contrast'
        }


# Font sizes
FONT_SIZE_TITLE = 20
FONT_SIZE_HEADING = 16
FONT_SIZE_NORMAL = 14
FONT_SIZE_SMALL = 12
FONT_SIZE_TINY = 10

# Font names
FONT_FAMILY_PRIMARY = 'Helvetica'
FONT_FAMILY_MONO = 'Courier'

# Spacing
PADDING_SMALL = 5
PADDING_NORMAL = 10
PADDING_LARGE = 20

# Border radius
CORNER_RADIUS = 8

# Animation
ANIMATION_DURATION = 200  # ms
