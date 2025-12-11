"""Gain smoothing utilities to avoid zipper noise."""

from __future__ import annotations

from typing import Dict, Mapping


class GainSmoother:
    """
    Exponential smoothing for gain changes with a soft floor.
    Keeps a 10% floor on noise to reduce watery artifacts.
    """

    def __init__(self, smoothing: float = 0.9, noise_floor: float = 0.1) -> None:
        if not 0.0 <= smoothing <= 1.0:
            raise ValueError("smoothing must be in [0, 1].")
        if not 0.0 <= noise_floor <= 1.0:
            raise ValueError("noise_floor must be in [0, 1].")
        self.smoothing = smoothing
        self.noise_floor = noise_floor
        self.current = {"speech": 1.0, "noise": noise_floor, "events": 0.5}

    def smooth(self, target_gains: Mapping[str, float]) -> Dict[str, float]:
        """Apply exponential smoothing and clamp noise floor."""
        for key, target in target_gains.items():
            prev = self.current.get(key, 0.0)
            smoothed = (self.smoothing * prev) + ((1 - self.smoothing) * target)
            if key == "noise":
                smoothed = max(smoothed, self.noise_floor)
            self.current[key] = smoothed
        return dict(self.current)


__all__ = ["GainSmoother"]
