"""
Mode Frame - Control mode selection and profile management
"""

import customtkinter as ctk
from typing import Callable, Optional, List
from theme import Theme, PADDING_NORMAL, CORNER_RADIUS, FONT_SIZE_HEADING, FONT_SIZE_SMALL


class ModeFrame(ctk.CTkFrame):
    """Frame for mode selection (Auto/Manual) and profile management"""
    
    def __init__(self, parent, theme_name: str = 'dark', **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = Theme.get_theme(theme_name)
        self.configure(
            fg_color=self.theme.bg_secondary,
            corner_radius=CORNER_RADIUS
        )
        
        # Callbacks
        self.on_mode_change: Optional[Callable[[str], None]] = None
        self.on_profile_select: Optional[Callable[[str], None]] = None
        self.on_save_profile: Optional[Callable[[], None]] = None
        
        # State
        self.current_mode = 'manual'
        self.profiles: List[tuple] = []  # [(id, name), ...]
        self.current_profile_id: Optional[str] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create all UI elements"""
        # Left side: Mode buttons
        left_frame = ctk.CTkFrame(self, fg_color='transparent')
        left_frame.pack(side='left', fill='both', expand=False, padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        mode_label = ctk.CTkLabel(
            left_frame,
            text='Mode:',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING)
        )
        mode_label.pack(side='left', padx=(0, PADDING_NORMAL))
        
        # Mode buttons with segmented button style
        button_frame = ctk.CTkFrame(left_frame, fg_color='transparent')
        button_frame.pack(side='left')
        
        self.auto_btn = ctk.CTkButton(
            button_frame,
            text='🤖 AUTO',
            width=80,
            height=35,
            command=self._on_auto_clicked,
            fg_color=self.theme.accent,
            text_color=self.theme.text,
            corner_radius=CORNER_RADIUS,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        self.auto_btn.pack(side='left', padx=2)
        
        self.manual_btn = ctk.CTkButton(
            button_frame,
            text='✋ MANUAL',
            width=80,
            height=35,
            command=self._on_manual_clicked,
            fg_color=self.theme.bg_primary,
            text_color=self.theme.text,
            corner_radius=CORNER_RADIUS,
            border_width=2,
            border_color=self.theme.accent,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        self.manual_btn.pack(side='left', padx=2)
        
        # Right side: Profile selector
        right_frame = ctk.CTkFrame(self, fg_color='transparent')
        right_frame.pack(side='right', fill='both', expand=True, padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        profile_label = ctk.CTkLabel(
            right_frame,
            text='Profile:',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING)
        )
        profile_label.pack(side='left', padx=(0, PADDING_NORMAL))
        
        # Profile dropdown
        self.profile_dropdown = ctk.CTkComboBox(
            right_frame,
            width=200,
            height=35,
            command=self._on_profile_selected,
            fg_color=self.theme.bg_primary,
            text_color=self.theme.text,
            button_color=self.theme.accent,
            dropdown_fg_color=self.theme.bg_secondary,
            dropdown_text_color=self.theme.text,
            border_color=self.theme.accent,
            border_width=1,
            corner_radius=CORNER_RADIUS,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.profile_dropdown.pack(side='left', padx=5)
        self.profile_dropdown.set('No profiles')
        
        # Save profile button
        self.save_btn = ctk.CTkButton(
            right_frame,
            text='💾 Save as New',
            width=120,
            height=35,
            command=self._on_save_clicked,
            fg_color=self.theme.success,
            text_color=self.theme.bg_primary,
            corner_radius=CORNER_RADIUS,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        self.save_btn.pack(side='left', padx=5)
        
        # Update button states
        self._update_button_states()
    
    def _on_auto_clicked(self):
        """Handle auto mode button click"""
        self.current_mode = 'auto'
        self._update_button_states()
        if self.on_mode_change:
            self.on_mode_change('auto')
    
    def _on_manual_clicked(self):
        """Handle manual mode button click"""
        self.current_mode = 'manual'
        self._update_button_states()
        if self.on_mode_change:
            self.on_mode_change('manual')
    
    def _on_profile_selected(self, value: str):
        """Handle profile selection"""
        # Find profile ID by name
        for profile_id, profile_name in self.profiles:
            if profile_name == value:
                self.current_profile_id = profile_id
                if self.on_profile_select:
                    self.on_profile_select(profile_id)
                break
    
    def _on_save_clicked(self):
        """Handle save profile button click"""
        if self.on_save_profile:
            self.on_save_profile()
    
    def _update_button_states(self):
        """Update button visual states based on current mode"""
        if self.current_mode == 'auto':
            self.auto_btn.configure(
                fg_color=self.theme.success,
                border_width=0
            )
            self.manual_btn.configure(
                fg_color=self.theme.bg_primary,
                border_width=2,
                border_color=self.theme.accent
            )
        else:
            self.auto_btn.configure(
                fg_color=self.theme.bg_primary,
                border_width=2,
                border_color=self.theme.accent
            )
            self.manual_btn.configure(
                fg_color=self.theme.success,
                border_width=0
            )
    
    def set_mode(self, mode: str):
        """Set the current mode"""
        self.current_mode = mode
        self._update_button_states()
    
    def get_mode(self) -> str:
        """Get the current mode"""
        return self.current_mode
    
    def update_profiles(self, profiles: List[tuple]):
        """
        Update the profile list
        
        Args:
            profiles: List of (id, name) tuples
        """
        self.profiles = profiles
        
        profile_names = [name for _, name in profiles]
        self.profile_dropdown.configure(values=profile_names)
        
        if profile_names:
            self.profile_dropdown.set(profile_names[0])
            self.current_profile_id = profiles[0][0]
        else:
            self.profile_dropdown.set('No profiles')
            self.current_profile_id = None
    
    def set_profile(self, profile_id: str):
        """Set the current profile"""
        for pid, name in self.profiles:
            if pid == profile_id:
                self.profile_dropdown.set(name)
                self.current_profile_id = profile_id
                break
    
    def get_selected_profile(self) -> Optional[str]:
        """Get the currently selected profile ID"""
        return self.current_profile_id

