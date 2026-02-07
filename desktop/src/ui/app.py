"""
Main Application - Semantic Mixer desktop application
"""

import customtkinter as ctk
import tkinter as tk
from typing import Optional
from pathlib import Path

from theme import Theme, PADDING_NORMAL, CORNER_RADIUS
from mode_frame import ModeFrame
from detection_frame import DetectionFrame
from mixer_frame import MixerFrame
from safety_frame import SafetyFrame
from status_bar import StatusBar
from shortcuts import KeyboardShortcuts
from ui_controller import UIController


class SaveProfileDialog(ctk.CTkToplevel):
    """Dialog for saving a new profile"""
    
    def __init__(self, parent, callback):
        super().__init__(parent)
        
        self.callback = callback
        self.result = None
        
        self.title('Save Profile')
        self.geometry('400x250')
        self.resizable(False, False)
        
        # Name input
        ctk.CTkLabel(self, text='Profile Name:', text_color='white').pack(pady=10)
        
        self.name_input = ctk.CTkEntry(self, width=300, height=40)
        self.name_input.pack(pady=5)
        self.name_input.focus()
        
        # Description input
        ctk.CTkLabel(self, text='Description (optional):', text_color='white').pack(pady=(20, 10))
        
        self.desc_input = ctk.CTkTextbox(self, width=300, height=80)
        self.desc_input.pack(pady=5)
        
        # Buttons
        button_frame = ctk.CTkFrame(self, fg_color='transparent')
        button_frame.pack(pady=20)
        
        save_btn = ctk.CTkButton(
            button_frame,
            text='Save',
            width=100,
            command=self._on_save,
            fg_color='#4ecca3'
        )
        save_btn.pack(side='left', padx=10)
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text='Cancel',
            width=100,
            command=self._on_cancel,
            fg_color='#ff2e63'
        )
        cancel_btn.pack(side='left', padx=10)
    
    def _on_save(self):
        """Handle save button"""
        name = self.name_input.get().strip()
        if not name:
            ctk.CTkLabel(self, text='Profile name is required!', text_color='red').pack()
            return
        
        description = self.desc_input.get('1.0', 'end').strip()
        self.callback(name, description)
        self.destroy()
    
    def _on_cancel(self):
        """Handle cancel button"""
        self.destroy()


class SemanticMixerApp(ctk.CTk):
    """Main application window for Semantic Mixer"""
    
    def __init__(self, ui_controller: UIController, theme_name: str = 'dark'):
        super().__init__()
        
        self.ui_controller = ui_controller
        self.theme_name = theme_name
        self.theme = Theme.get_theme(theme_name)
        
        # Window configuration
        self.title('Semantic Noise Mixer')
        self.geometry('900x1000')
        self.minsize(800, 800)
        
        # Set theme
        ctk.set_appearance_mode(theme_name)
        ctk.set_default_color_theme('blue')
        
        # Configure window colors
        self.configure(fg_color=self.theme.bg_primary)
        
        # Setup keyboard shortcuts
        self.shortcuts = KeyboardShortcuts()
        self._setup_shortcuts()
        
        # Create UI frames
        self.mode_frame: Optional[ModeFrame] = None
        self.detection_frame: Optional[DetectionFrame] = None
        self.mixer_frame: Optional[MixerFrame] = None
        self.safety_frame: Optional[SafetyFrame] = None
        self.status_bar: Optional[StatusBar] = None
        
        # Handle window close
        self.protocol('WM_DELETE_WINDOW', self.on_closing)
        
        # Create widgets
        self._create_widgets()
        
        # Setup UI controller callbacks
        self._setup_ui_callbacks()
        
        # Initialize UI with current state
        self._initialize_ui_state()
    
    def _create_widgets(self):
        """Create all UI components"""
        # Main container with padding
        main_frame = ctk.CTkFrame(self, fg_color=self.theme.bg_primary)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Mode frame
        self.mode_frame = ModeFrame(main_frame, theme_name=self.theme_name)
        self.mode_frame.pack(fill='x', pady=10)
        
        # Detection frame
        self.detection_frame = DetectionFrame(main_frame, theme_name=self.theme_name)
        self.detection_frame.pack(fill='x', pady=10)
        
        # Mixer frame
        self.mixer_frame = MixerFrame(main_frame, theme_name=self.theme_name)
        self.mixer_frame.pack(fill='both', expand=True, pady=10)
        
        # Safety frame
        self.safety_frame = SafetyFrame(main_frame, theme_name=self.theme_name)
        self.safety_frame.pack(fill='x', pady=10)
        
        # Status bar
        self.status_bar = StatusBar(self, theme_name=self.theme_name)
        self.status_bar.pack(fill='x', side='bottom')
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Register handlers
        self.shortcuts.register_handler('toggle_mute', self._on_mute_all)
        self.shortcuts.register_handler('passthrough', self._on_passthrough)
        self.shortcuts.register_handler('auto_mode', self._on_auto_mode)
        self.shortcuts.register_handler('manual_mode', self._on_manual_mode)
        self.shortcuts.register_handler('save_profile', self._on_save_profile)
        
        # Bind to window
        self.shortcuts.bind_to_window(self)
    
    def _setup_ui_callbacks(self):
        """Setup callbacks between UI and controller"""
        # Mode frame callbacks
        if self.mode_frame:
            self.mode_frame.on_mode_change = self.ui_controller.handle_mode_change
            self.mode_frame.on_profile_select = self.ui_controller.handle_profile_select
            self.mode_frame.on_save_profile = self._on_save_profile
        
        # Mixer frame callbacks
        if self.mixer_frame:
            self.mixer_frame.on_speech_change = self._on_slider_change
            self.mixer_frame.on_noise_change = self._on_slider_change
            self.mixer_frame.on_events_change = self._on_slider_change
            self.mixer_frame.on_mute_all = self._on_mute_all
            self.mixer_frame.on_passthrough = self._on_passthrough
        
        # Safety frame callbacks
        if self.safety_frame:
            self.safety_frame.on_safety_toggle = self.ui_controller.handle_safety_toggle
        
        # UI controller callbacks
        self.ui_controller.on_profile_list_update = self._on_profile_list_update
        self.ui_controller.on_mode_changed = self._on_mode_changed
        self.ui_controller.on_gains_update = self._on_gains_update
        self.ui_controller.on_detections_update = self._on_detections_update
        self.ui_controller.on_safety_alert = self._on_safety_alert
        self.ui_controller.on_safety_clear = self._on_safety_clear
    
    def _initialize_ui_state(self):
        """Initialize UI with current controller state"""
        # Get current gains
        speech, noise, events = self.ui_controller.get_current_gains()
        self.mixer_frame.set_gains(speech, noise, events)
        
        # Get current mode
        mode = self.ui_controller.get_current_mode()
        self.mode_frame.set_mode(mode)
        
        # Get profile list
        profiles = self.ui_controller.get_profile_list()
        self.mode_frame.update_profiles(profiles)
    
    # UI Event Handlers
    
    def _on_slider_change(self, value: float):
        """Handle slider change"""
        speech, noise, events = self.mixer_frame.get_gains()
        self.ui_controller.handle_slider_change(speech, noise, events)
    
    def _on_mute_all(self):
        """Handle mute all"""
        self.ui_controller.handle_mute_all()
    
    def _on_passthrough(self):
        """Handle passthrough"""
        self.ui_controller.handle_passthrough()
    
    def _on_auto_mode(self):
        """Handle auto mode shortcut"""
        self.mode_frame.set_mode('auto')
        self.ui_controller.handle_mode_change('auto')
    
    def _on_manual_mode(self):
        """Handle manual mode shortcut"""
        self.mode_frame.set_mode('manual')
        self.ui_controller.handle_mode_change('manual')
    
    def _on_save_profile(self):
        """Handle save profile"""
        dialog = SaveProfileDialog(self, self._save_profile_confirmed)
    
    def _save_profile_confirmed(self, name: str, description: str):
        """Handle confirmed save profile"""
        self.ui_controller.handle_save_profile(name, description)
    
    # Controller Event Handlers
    
    def _on_profile_list_update(self, profiles):
        """Handle profile list update"""
        self.mode_frame.update_profiles(profiles)
    
    def _on_mode_changed(self, mode: str):
        """Handle mode changed"""
        self.mode_frame.set_mode(mode)
    
    def _on_gains_update(self, speech: float, noise: float, events: float):
        """Handle gains update"""
        self.mixer_frame.set_gains(speech, noise, events)
    
    def _on_detections_update(self, detections: dict):
        """Handle detection update"""
        self.detection_frame.update_detections(detections)
    
    def _on_safety_alert(self, category: str, confidence: float):
        """Handle safety alert"""
        self.safety_frame.show_alert(category, confidence)
    
    def _on_safety_clear(self):
        """Handle safety alert clear"""
        self.safety_frame.clear_alert()
    
    def on_closing(self):
        """Handle window close"""
        if self.status_bar:
            self.status_bar.stop()
        
        if self.ui_controller:
            self.ui_controller.stop()
        
        self.destroy()


def main():
    """Main entry point"""
    # Initialize controller (would be connected to real backend)
    controller = UIController()
    
    # For testing without backend:
    # controller.initialize(None, None)
    
    # Create application
    app = SemanticMixerApp(controller, theme_name='dark')
    
    # Start controller
    controller.start()
    
    # Run
    app.mainloop()


if __name__ == '__main__':
    main()

