"""Batch processing utilities for offline suppression."""

from __future__ import annotations

__all__ = ["BatchProcessor"]


def __getattr__(name: str):
    if name == "BatchProcessor":
        from .batch_processor import BatchProcessor

        return BatchProcessor
    raise AttributeError(name)
