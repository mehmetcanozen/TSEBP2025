"""Thread-safe ring buffer for audio samples."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Optional

import numpy as np


class RingBuffer:
    """Fixed-capacity float32 ring buffer."""

    def __init__(self, capacity: int = 4800) -> None:
        self._buffer = deque(maxlen=capacity)
        self._lock = Lock()

    def write(self, data: np.ndarray) -> None:
        samples = np.asarray(data, dtype=np.float32).reshape(-1)
        with self._lock:
            self._buffer.extend(samples)

    def read(self, num_samples: int) -> Optional[np.ndarray]:
        with self._lock:
            if len(self._buffer) < num_samples:
                return None
            out = [self._buffer.popleft() for _ in range(num_samples)]
        return np.asarray(out, dtype=np.float32)

    def available(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


__all__ = ["RingBuffer"]
