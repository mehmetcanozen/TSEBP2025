"""Latency profiling utilities for audio processing performance monitoring."""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, Optional

import numpy as np


class LatencyProfiler:
    """
    Track inference and processing latency for performance monitoring.
    
    This profiler will be used in:
    - DevPlan5: Status bar display (real-time latency)
    - DevPlan7: Benchmarking and performance validation
    """

    def __init__(self, window_size: int = 100) -> None:
        """
        Initialize the latency profiler.
        
        Args:
            window_size: Number of measurements to keep for rolling statistics.
        """
        self.latencies = deque(maxlen=window_size)
        self._start_time: Optional[float] = None

    def start(self) -> None:
        """Start timing a new operation."""
        self._start_time = time.perf_counter()

    def stop(self) -> float:
        """
        Stop timing and record the measurement.
        
        Returns:
            The elapsed time in milliseconds.
        """
        if self._start_time is None:
            raise RuntimeError("Profiler was not started. Call start() first.")
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000
        self.latencies.append(elapsed_ms)
        self._start_time = None
        return elapsed_ms

    def record(self, start_time: float) -> float:
        """
        Record a measurement using an external start time.
        
        Args:
            start_time: The start time from time.perf_counter().
            
        Returns:
            The elapsed time in milliseconds.
        """
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.latencies.append(elapsed_ms)
        return elapsed_ms

    def stats(self) -> Dict[str, float]:
        """
        Get latency statistics.
        
        Returns:
            Dictionary with avg, p95, p99, min, and max latencies in ms.
        """
        if not self.latencies:
            return {"avg": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0}
        
        arr = np.array(self.latencies)
        return {
            "avg": float(np.mean(arr)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }

    def last(self) -> float:
        """Get the most recent latency measurement in ms."""
        return self.latencies[-1] if self.latencies else 0.0

    def reset(self) -> None:
        """Clear all recorded measurements."""
        self.latencies.clear()
        self._start_time = None


__all__ = ["LatencyProfiler"]
