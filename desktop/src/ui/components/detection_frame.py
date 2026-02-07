"""
Detection Frame - Display real-time detected sounds
"""

import customtkinter as ctk
from typing import Dict, Optional
from theme import Theme, PADDING_NORMAL, CORNER_RADIUS, FONT_SIZE_HEADING, FONT_SIZE_SMALL


class DetectionCard(ctk.CTkFrame):
    """Single detection card showing icon, label, and progress bar"""
    
    def __init__(self, parent, icon: str, label: str, theme: Theme, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = theme
        self.icon = icon
        self.label = label
        self.confidence = 0.0
        self.is_critical = False  # For siren/alarm
        
        self.configure(
            fg_color=self.theme.bg_secondary,
            corner_radius=CORNER_RADIUS
        )
        
        # Title with icon and label
        title_frame = ctk.CTkFrame(self, fg_color='transparent')
        title_frame.pack(fill='x', padx=PADDING_NORMAL, pady=(PADDING_NORMAL, 0))
        
        icon_label = ctk.CTkLabel(
            title_frame,
            text=icon,
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING)
        )
        icon_label.pack(side='left')
        
        name_label = ctk.CTkLabel(
            title_frame,
            text=label,
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL, 'bold')
        )
        name_label.pack(side='left', padx=10)
        
        # Progress bar frame
        bar_frame = ctk.CTkFrame(self, fg_color='transparent')
        bar_frame.pack(fill='x', padx=PADDING_NORMAL, pady=5)
        
        # Progress bar (custom)
        self.progress_bar = ctk.CTkProgressBar(
            bar_frame,
            height=8,
            fg_color=self.theme.border,
            progress_color=self._get_bar_color(),
            corner_radius=4
        )
        self.progress_bar.pack(fill='x')
        self.progress_bar.set(0.0)
        
        # Percentage label
        self.percent_label = ctk.CTkLabel(
            bar_frame,
            text='0%',
            text_color=self.theme.text_secondary,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.percent_label.pack(pady=(3, 0))
    
    def _get_bar_color(self) -> str:
        """Get color for progress bar"""
        if self.is_critical:
            return self.theme.danger
        elif self.label.lower() in ['speech']:
            return self.theme.slider_speech
        elif self.label.lower() in ['background', 'noise', 'wind', 'traffic']:
            return self.theme.slider_noise
        else:
            return self.theme.slider_events
    
    def update_confidence(self, confidence: float):
        """Update detection confidence"""
        self.confidence = max(0.0, min(1.0, confidence))
        self.progress_bar.set(self.confidence)
        self.percent_label.configure(text=f'{int(self.confidence * 100)}%')
        
        # Update color if critical
        if self.label.lower() in ['siren', 'alarm']:
            self.is_critical = self.confidence > 0.5
            self.progress_bar.configure(
                progress_color=self._get_bar_color()
            )
            if self.is_critical:
                self._flash()
    
    def _flash(self):
        """Flash the card when critical sound is detected"""
        # Alternate color
        colors = [self.theme.danger, self.theme.bg_secondary]
        self.configure(fg_color=colors[0])
        self.after(200, lambda: self.configure(fg_color=colors[1]))
        self.after(400, lambda: self.configure(fg_color=colors[0]))
        self.after(600, lambda: self.configure(fg_color=self.theme.bg_secondary))


class DetectionFrame(ctk.CTkFrame):
    """Frame displaying all detected sounds in real-time"""
    
    # Detection categories with icons
    DETECTION_ICONS = {
        'speech': ('🎤', 'Speech'),
        'wind': ('💨', 'Wind'),
        'traffic': ('🚗', 'Traffic'),
        'typing': ('⌨️', 'Typing'),
        'siren': ('🚨', 'Siren'),
        'alarm': ('🔔', 'Alarm'),
        'door': ('🚪', 'Door'),
        'phone': ('📱', 'Phone'),
    }
    
    def __init__(self, parent, theme_name: str = 'dark', **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = Theme.get_theme(theme_name)
        self.configure(
            fg_color=self.theme.bg_secondary,
            corner_radius=CORNER_RADIUS
        )
        
        self.detection_cards: Dict[str, DetectionCard] = {}
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create detection display"""
        # Header
        header = ctk.CTkLabel(
            self,
            text='🎵 LIVE DETECTION',
            text_color=self.theme.text,
            font=(ctk.CTkFont(), FONT_SIZE_HEADING, 'bold')
        )
        header.pack(fill='x', padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        # Detection grid
        grid_frame = ctk.CTkFrame(self, fg_color='transparent')
        grid_frame.pack(fill='both', expand=True, padx=PADDING_NORMAL, pady=PADDING_NORMAL)
        
        # Create detection cards in a 2x4 grid
        col = 0
        row = 0
        cols_per_row = 2
        
        for category, (icon, label) in self.DETECTION_ICONS.items():
            card = DetectionCard(
                grid_frame,
                icon=icon,
                label=label,
                theme=self.theme,
                height=100,
                width=200
            )
            
            card.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
            self.detection_cards[category] = card
            
            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1
        
        # Configure grid weights
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
    
    def update_detections(self, detections: Dict[str, float]):
        """
        Update detection display with new values
        
        Args:
            detections: Dictionary of category -> confidence (0-1)
        """
        for category, confidence in detections.items():
            if category in self.detection_cards:
                self.detection_cards[category].update_confidence(confidence)
        
        # Update categories not in detections to 0
        for category, card in self.detection_cards.items():
            if category not in detections:
                card.update_confidence(0.0)
    
    def clear_all(self):
        """Clear all detections"""
        for card in self.detection_cards.values():
            card.update_confidence(0.0)
