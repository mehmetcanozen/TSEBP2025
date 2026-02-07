"""
Mixer Frame - Gain control sliders for Speech, Noise, Events
"""

import customtkinter as ctk
from typing import Callable, Optional
from theme import Theme, PADDING_NORMAL, CORNER_RADIUS, FONT_SIZE_HEADING, FONT_SIZE_SMALL


class GainSlider(ctk.CTkFrame):
    """Single gain slider for a mixer category"""
    
    def __init__(self, parent, label: str, color: str, theme: Theme, 
                 on_change: Optional[Callable[[float], None]] = None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = theme
        self.label = label
        self.color = color
        self.on_change = on_change
        self.value = 1.0
        
        self.configure(fg_color='transparent')
        
        # Label
        label_widget = ctk.CTkLabel(
            self,
            text=label,
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        label_widget.pack(pady=(0, PADDING_NORMAL))
        
        # Slider (vertical)
        self.slider = ctk.CTkSlider(
            self,
            from_=0,
            to=1,
            orientation='vertical',
            width=50,
            height=150,
            button_color=color,
            button_hover_color=color,
            progress_color=color,
            fg_color=self.theme.border,
            command=self._on_slider_changed
        )
        self.slider.pack(padx=10)
        self.slider.set(1.0)
        
        # Percentage display
        self.percent_label = ctk.CTkLabel(
            self,
            text='100%',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING, 'bold')
        )
        self.percent_label.pack(pady=(PADDING_NORMAL, 0))
    
    def _on_slider_changed(self, value: float):
        """Handle slider change"""
        self.value = value
        self.percent_label.configure(text=f'{int(value * 100)}%')
        if self.on_change:
            self.on_change(value)
    
    def set_value(self, value: float):
        """Set slider value"""
        self.slider.set(value)
    
    def get_value(self) -> float:
        """Get slider value"""
        return self.value


class MixerFrame(ctk.CTkFrame):
    """Frame containing mixer sliders for gain control"""
    
    def __init__(self, parent, theme_name: str = 'dark', **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = Theme.get_theme(theme_name)
        self.configure(
            fg_color=self.theme.bg_secondary,
            corner_radius=CORNER_RADIUS
        )
        
        # Callbacks
        self.on_speech_change: Optional[Callable[[float], None]] = None
        self.on_noise_change: Optional[Callable[[float], None]] = None
        self.on_events_change: Optional[Callable[[float], None]] = None
        self.on_mute_all: Optional[Callable[[], None]] = None
        self.on_passthrough: Optional[Callable[[], None]] = None
        
        # Sliders
        self.speech_slider: Optional[GainSlider] = None
        self.noise_slider: Optional[GainSlider] = None
        self.events_slider: Optional[GainSlider] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create mixer interface"""
        # Header
        header = ctk.CTkLabel(
            self,
            text='🎚️ MIXER',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING, 'bold')
        )
        header.pack(fill='x', padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        # Sliders frame
        sliders_frame = ctk.CTkFrame(self, fg_color='transparent')
        sliders_frame.pack(fill='both', expand=True, padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        # Speech slider
        self.speech_slider = GainSlider(
            sliders_frame,
            label='Speech',
            color=self.theme.slider_speech,
            theme=self.theme,
            on_change=self._on_speech_changed
        )
        self.speech_slider.pack(side='left', expand=True, padx=10)
        
        # Noise slider
        self.noise_slider = GainSlider(
            sliders_frame,
            label='Background',
            color=self.theme.slider_noise,
            theme=self.theme,
            on_change=self._on_noise_changed
        )
        self.noise_slider.pack(side='left', expand=True, padx=10)
        
        # Events slider
        self.events_slider = GainSlider(
            sliders_frame,
            label='Events',
            color=self.theme.slider_events,
            theme=self.theme,
            on_change=self._on_events_changed
        )
        self.events_slider.pack(side='left', expand=True, padx=10)
        
        # Control buttons
        buttons_frame = ctk.CTkFrame(self, fg_color='transparent')
        buttons_frame.pack(fill='x', padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        mute_btn = ctk.CTkButton(
            buttons_frame,
            text='🔇 Mute All',
            command=self._on_mute_all_clicked,
            fg_color=self.theme.danger,
            text_color=self.theme.text,
            corner_radius=CORNER_RADIUS,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        mute_btn.pack(side='left', padx=5)
        
        passthrough_btn = ctk.CTkButton(
            buttons_frame,
            text='🔊 Passthrough',
            command=self._on_passthrough_clicked,
            fg_color=self.theme.success,
            text_color=self.theme.bg_primary,
            corner_radius=CORNER_RADIUS,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        passthrough_btn.pack(side='left', padx=5)
    
    def _on_speech_changed(self, value: float):
        """Handle speech slider change"""
        if self.on_speech_change:
            self.on_speech_change(value)
    
    def _on_noise_changed(self, value: float):
        """Handle noise slider change"""
        if self.on_noise_change:
            self.on_noise_change(value)
    
    def _on_events_changed(self, value: float):
        """Handle events slider change"""
        if self.on_events_change:
            self.on_events_change(value)
    
    def _on_mute_all_clicked(self):
        """Handle mute all button"""
        self.set_gains(0.0, 0.0, 0.0)
        if self.on_mute_all:
            self.on_mute_all()
    
    def _on_passthrough_clicked(self):
        """Handle passthrough button"""
        self.set_gains(1.0, 1.0, 1.0)
        if self.on_passthrough:
            self.on_passthrough()
    
    def set_gains(self, speech: float, noise: float, events: float):
        """Set all sliders to specific values"""
        if self.speech_slider:
            self.speech_slider.set_value(speech)
        if self.noise_slider:
            self.noise_slider.set_value(noise)
        if self.events_slider:
            self.events_slider.set_value(events)
    
    def get_gains(self) -> tuple:
        """Get current slider values"""
        speech = self.speech_slider.get_value() if self.speech_slider else 1.0
        noise = self.noise_slider.get_value() if self.noise_slider else 1.0
        events = self.events_slider.get_value() if self.events_slider else 1.0
        return (speech, noise, events)
