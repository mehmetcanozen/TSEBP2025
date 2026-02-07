"""
Safety Frame - Display safety override status and alerts
"""

import customtkinter as ctk
from typing import Optional, Callable
from theme import Theme, PADDING_NORMAL, CORNER_RADIUS, FONT_SIZE_HEADING, FONT_SIZE_SMALL


class SafetyFrame(ctk.CTkFrame):
    """Frame showing safety override status"""
    
    def __init__(self, parent, theme_name: str = 'dark', **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = Theme.get_theme(theme_name)
        self.configure(
            fg_color=self.theme.bg_secondary,
            corner_radius=CORNER_RADIUS
        )
        
        # Callbacks
        self.on_safety_toggle: Optional[Callable[[bool], None]] = None
        
        # State
        self.safety_enabled = True
        self.alert_active = False
        self.alert_category: Optional[str] = None
        
        # UI Elements
        self.status_indicator: Optional[ctk.CTkLabel] = None
        self.status_label: Optional[ctk.CTkLabel] = None
        self.alert_label: Optional[ctk.CTkLabel] = None
        self.toggle_switch: Optional[ctk.CTkSwitch] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create safety display"""
        # Header frame
        header_frame = ctk.CTkFrame(self, fg_color='transparent')
        header_frame.pack(fill='x', padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        # Title
        title = ctk.CTkLabel(
            header_frame,
            text='🛡️ SAFETY OVERRIDE',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING, 'bold')
        )
        title.pack(side='left')
        
        # Toggle switch
        self.toggle_switch = ctk.CTkSwitch(
            header_frame,
            text='Enabled',
            command=self._on_safety_toggle,
            text_color=self.theme.text,
            fg_color=self.theme.success,
            progress_color=self.theme.success,
            button_color=self.theme.text
        )
        self.toggle_switch.pack(side='right', padx=PADDING_NORMAL)
        self.toggle_switch.select()
        
        # Status frame
        status_frame = ctk.CTkFrame(self, fg_color='transparent')
        status_frame.pack(fill='x', padx=PADDING_NORMAL, pady=(0, PADDING_NORMAL))
        
        # Status indicator (colored dot)
        self.status_indicator = ctk.CTkLabel(
            status_frame,
            text='🟢',
            text_color=self.theme.success,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING)
        )
        self.status_indicator.pack(side='left', padx=10)
        
        # Status text
        self.status_label = ctk.CTkLabel(
            status_frame,
            text='Status: NORMAL',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.status_label.pack(side='left')
        
        # Alert panel (hidden by default)
        self.alert_panel = ctk.CTkFrame(
            self,
            fg_color=self.theme.danger,
            corner_radius=CORNER_RADIUS
        )
        
        alert_content = ctk.CTkFrame(self.alert_panel, fg_color='transparent')
        alert_content.pack(fill='both', expand=True, padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        alert_title = ctk.CTkLabel(
            alert_content,
            text='⚠️ SAFETY ALERT ACTIVE',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING, 'bold')
        )
        alert_title.pack(fill='x', pady=(0, PADDING_NORMAL))
        
        self.alert_label = ctk.CTkLabel(
            alert_content,
            text='Siren detected - Critical audio is prioritized',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL),
            wraplength=400
        )
        self.alert_label.pack(fill='x')
        
        # Hide alert panel initially
        self._hide_alert()
    
    def _on_safety_toggle(self):
        """Handle safety toggle"""
        self.safety_enabled = self.toggle_switch.get()
        if self.on_safety_toggle:
            self.on_safety_toggle(self.safety_enabled)
    
    def _hide_alert(self):
        """Hide the alert panel"""
        self.alert_panel.pack_forget()
    
    def _show_alert(self):
        """Show the alert panel"""
        self.alert_panel.pack(fill='x', padx=PADDING_NORMAL, pady=PADDING_NORMAL)
    
    def show_alert(self, category: str, confidence: float):
        """
        Show a safety alert
        
        Args:
            category: Sound category (siren, alarm)
            confidence: Detection confidence (0-1)
        """
        self.alert_active = True
        self.alert_category = category
        
        # Update status
        self.status_indicator.configure(text='🔴')
        self.status_label.configure(
            text=f'⚠️ ALERT: {category.upper()} ({int(confidence * 100)}%)',
            text_color=self.theme.danger
        )
        
        # Update alert message
        message = f'{category.capitalize()} detected at {int(confidence * 100)}% confidence - All critical sounds are being prioritized'
        self.alert_label.configure(text=message)
        
        # Show alert panel
        self._show_alert()
        
        # Flash the indicator
        self._flash_indicator()
    
    def _flash_indicator(self):
        """Flash the status indicator"""
        colors = ['🔴', '🟥']
        self.status_indicator.configure(text=colors[0])
        self.after(200, lambda: self.status_indicator.configure(text=colors[1]))
        self.after(400, lambda: self.status_indicator.configure(text=colors[0]))
        self.after(600, lambda: self.status_indicator.configure(text=colors[1]))
    
    def clear_alert(self):
        """Clear the alert"""
        self.alert_active = False
        self.alert_category = None
        
        # Reset status
        self.status_indicator.configure(
            text='🟢',
            text_color=self.theme.success
        )
        self.status_label.configure(
            text='Status: NORMAL',
            text_color=self.theme.text
        )
        
        # Hide alert panel
        self._hide_alert()
    
    def is_enabled(self) -> bool:
        """Check if safety override is enabled"""
        return self.safety_enabled
    
    def set_enabled(self, enabled: bool):
        """Set safety override enabled state"""
        self.safety_enabled = enabled
        if enabled:
            self.toggle_switch.select()
        else:
            self.toggle_switch.deselect()
