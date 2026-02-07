"""
Status Bar - Display system metrics (latency, CPU, model info)
"""

import customtkinter as ctk
import psutil
import threading
from typing import Optional, Callable
from theme import Theme, PADDING_NORMAL, FONT_SIZE_SMALL


class StatusBar(ctk.CTkFrame):
    """Bottom status bar showing system metrics"""
    
    def __init__(self, parent, theme_name: str = 'dark', **kwargs):
        super().__init__(parent, **kwargs)
        
        self.theme = Theme.get_theme(theme_name)
        self.configure(
            fg_color=self.theme.bg_primary,
            height=40
        )
        
        # Metrics
        self.latency_ms = 0
        self.cpu_percent = 0
        self.memory_percent = 0
        self.model_name = 'audio_mixer_v1.onnx'
        self.is_running = True
        
        # UI Elements
        self.latency_label: Optional[ctk.CTkLabel] = None
        self.cpu_label: Optional[ctk.CTkLabel] = None
        self.memory_label: Optional[ctk.CTkLabel] = None
        self.model_label: Optional[ctk.CTkLabel] = None
        
        # Callbacks
        self.on_metrics_update: Optional[Callable[[dict], None]] = None
        
        self._create_widgets()
        self._start_metrics_thread()
    
    def _create_widgets(self):
        """Create status bar widgets"""
        # Latency
        self.latency_label = ctk.CTkLabel(
            self,
            text='Latency: -- ms',
            text_color=self.theme.text_secondary,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.latency_label.pack(side='left', padx=15)
        
        # Separator
        sep1 = ctk.CTkLabel(self, text='|', text_color=self.theme.border)
        sep1.pack(side='left')
        
        # CPU
        self.cpu_label = ctk.CTkLabel(
            self,
            text='CPU: -- %',
            text_color=self.theme.text_secondary,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.cpu_label.pack(side='left', padx=15)
        
        # Separator
        sep2 = ctk.CTkLabel(self, text='|', text_color=self.theme.border)
        sep2.pack(side='left')
        
        # Memory
        self.memory_label = ctk.CTkLabel(
            self,
            text='Memory: -- %',
            text_color=self.theme.text_secondary,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.memory_label.pack(side='left', padx=15)
        
        # Separator
        sep3 = ctk.CTkLabel(self, text='|', text_color=self.theme.border)
        sep3.pack(side='left')
        
        # Model
        self.model_label = ctk.CTkLabel(
            self,
            text=f'Model: {self.model_name}',
            text_color=self.theme.text_secondary,
            font=(ctk.CTkFont(), FONT_SIZE_SMALL)
        )
        self.model_label.pack(side='left', padx=15)
    
    def set_latency(self, latency_ms: float):
        """Set latency display"""
        self.latency_ms = latency_ms
        self.latency_label.configure(text=f'Latency: {latency_ms:.1f} ms')
    
    def set_model_name(self, model_name: str):
        """Set model name display"""
        self.model_name = model_name
        self.model_label.configure(text=f'Model: {model_name}')
    
    def _start_metrics_thread(self):
        """Start background thread for metrics"""
        thread = threading.Thread(target=self._update_metrics_loop, daemon=True)
        thread.start()
    
    def _update_metrics_loop(self):
        """Background loop to update metrics"""
        while self.is_running:
            try:
                # Get CPU and memory
                self.cpu_percent = psutil.cpu_percent(interval=1)
                self.memory_percent = psutil.virtual_memory().percent
                
                # Update UI
                self.after(0, self._update_ui)
                
                # Call callback
                if self.on_metrics_update:
                    self.on_metrics_update({
                        'latency': self.latency_ms,
                        'cpu': self.cpu_percent,
                        'memory': self.memory_percent
                    })
            
            except Exception as e:
                print(f"Error updating metrics: {e}")
    
    def _update_ui(self):
        """Update UI with current metrics"""
        cpu_color = self.theme.text_secondary
        if self.cpu_percent > 80:
            cpu_color = self.theme.danger
        elif self.cpu_percent > 60:
            cpu_color = self.theme.warning
        
        self.cpu_label.configure(
            text=f'CPU: {self.cpu_percent:.1f} %',
            text_color=cpu_color
        )
        
        mem_color = self.theme.text_secondary
        if self.memory_percent > 80:
            mem_color = self.theme.danger
        elif self.memory_percent > 60:
            mem_color = self.theme.warning
        
        self.memory_label.configure(
            text=f'Memory: {self.memory_percent:.1f} %',
            text_color=mem_color
        )
    
    def stop(self):
        """Stop the metrics thread"""
        self.is_running = False
