"""
Keyboard Shortcuts - Define and handle keyboard shortcuts
"""

from typing import Callable, Dict, Optional


class KeyboardShortcuts:
    """Manage keyboard shortcuts"""
    
    # Default shortcuts
    SHORTCUTS = {
        'space': {
            'action': 'toggle_mute',
            'description': 'Toggle Mute All',
            'key': '<space>'
        },
        'p': {
            'action': 'passthrough',
            'description': 'Passthrough Mode',
            'key': '<p>'
        },
        'a': {
            'action': 'auto_mode',
            'description': 'Switch to Auto Mode',
            'key': '<a>'
        },
        'm': {
            'action': 'manual_mode',
            'description': 'Switch to Manual Mode',
            'key': '<m>'
        },
        '1': {
            'action': 'profile_1',
            'description': 'Select Profile 1',
            'key': '<1>'
        },
        '2': {
            'action': 'profile_2',
            'description': 'Select Profile 2',
            'key': '<2>'
        },
        '3': {
            'action': 'profile_3',
            'description': 'Select Profile 3',
            'key': '<3>'
        },
        'Control_L-s': {
            'action': 'save_profile',
            'description': 'Save Current as New Profile',
            'key': '<Control-s>'
        },
        'Escape': {
            'action': 'close_dialog',
            'description': 'Close Dialog',
            'key': '<Escape>'
        },
    }
    
    def __init__(self):
        """Initialize shortcuts"""
        self.handlers: Dict[str, Callable] = {}
    
    def register_handler(self, action: str, handler: Callable):
        """
        Register a handler for an action
        
        Args:
            action: Action name (e.g., 'toggle_mute')
            handler: Callable to execute
        """
        self.handlers[action] = handler
    
    def handle_shortcut(self, action: str):
        """
        Handle a keyboard shortcut
        
        Args:
            action: Action to handle
        """
        if action in self.handlers:
            try:
                self.handlers[action]()
            except Exception as e:
                print(f"Error handling shortcut {action}: {e}")
    
    def bind_to_window(self, window):
        """
        Bind all shortcuts to a window
        
        Args:
            window: tkinter window
        """
        for key_name, shortcut in self.SHORTCUTS.items():
            key_sequence = shortcut['key']
            action = shortcut['action']
            
            # Create lambda to capture action
            window.bind(key_sequence, lambda e, a=action: self.handle_shortcut(a))
    
    def get_shortcuts_help(self) -> str:
        """Get formatted help text for shortcuts"""
        help_text = "Keyboard Shortcuts:\n\n"
        for key, shortcut in self.SHORTCUTS.items():
            help_text += f"  {shortcut['key']:15} → {shortcut['description']}\n"
        return help_text
    
    @staticmethod
    def format_shortcut(key: str) -> str:
        """Format shortcut key for display"""
        key_map = {
            '<space>': 'Space',
            '<Control-s>': 'Ctrl+S',
            '<Escape>': 'Esc',
            '<a>': 'A',
            '<m>': 'M',
            '<p>': 'P',
        }
        return key_map.get(key, key)
