"""Latency profiling utilities for audio processing performance monitoring."""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, Optional

import numpy as np


class LatencyProfiler:
    """
    Track inference and processing latency for performance monitoring.
    """

    def __init__(self, window_size: int = 100) -> None:
        self.latencies = deque(maxlen=window_size)
        self._start_time: Optional[float] = None

    def start(self) -> None:
        self._start_time = time.perf_counter()

    def stop(self) -> float:
        if self._start_time is None:
            raise RuntimeError("Profiler was not started. Call start() first.")
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000
        self.latencies.append(elapsed_ms)
        self._start_time = None
        return elapsed_ms

    def record(self, start_time: float) -> float:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self.latencies.append(elapsed_ms)
        return elapsed_ms

    def stats(self) -> Dict[str, float]:
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
        return self.latencies[-1] if self.latencies else 0.0

    def reset(self) -> None:
        self.latencies.clear()
        self._start_time = None


__all__ = ["LatencyProfiler"]
