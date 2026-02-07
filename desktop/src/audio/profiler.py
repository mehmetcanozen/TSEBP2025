"""
Performance profiler for real-time audio processing.
Tracks latency, throughput, and operation-level bottlenecks.
"""

import time
import numpy as np
from collections import defaultdict, deque
from typing import Dict, Optional
import json
from pathlib import Path


class PerformanceProfiler:
    """Track latency, throughput, and bottlenecks for optimization."""
    
    def __init__(self, window_size: int = 100, enabled: bool = True):
        """
        Initialize profiler.
        
        Args:
            window_size: Number of samples to keep for rolling statistics
            enabled: Whether profiling is active (disable in production)
        """
        self.enabled = enabled
        self.window_size = window_size
        self.timings = defaultdict(lambda: deque(maxlen=window_size))
        self.counts = defaultdict(int)
        self._active_ops = {}  # Track nested operations
    
    def start(self, operation: str) -> float:
        """
        Start timing an operation.
        
        Args:
            operation: Name of the operation being timed
            
        Returns:
            Start timestamp (for manual recording if needed)
        """
        if not self.enabled:
            return 0.0
        
        start_time = time.perf_counter()
        self._active_ops[operation] = start_time
        return start_time
    
    def end(self, operation: str):
        """
        End timing an operation and record the duration.
        
        Args:
            operation: Name of the operation being timed
        """
        if not self.enabled:
            return
        
        if operation not in self._active_ops:
            return
        
        start_time = self._active_ops.pop(operation)
        duration_ms = (time.perf_counter() - start_time) * 1000
        self.record(operation, duration_ms)
    
    def record(self, operation: str, duration_ms: float):
        """
        Record a timing measurement manually.
        
        Args:
            operation: Name of the operation
            duration_ms: Duration in milliseconds
        """
        if not self.enabled:
            return
        
        self.timings[operation].append(duration_ms)
        self.counts[operation] += 1
    
    def get_stats(self, operation: Optional[str] = None) -> Dict:
        """
        Get statistics for one or all operations.
        
        Args:
            operation: Specific operation name, or None for all operations
            
        Returns:
            Dictionary with mean, median, p95, p99, min, max stats
        """
        if operation:
            if operation not in self.timings or not self.timings[operation]:
                return {}
            return self._compute_stats(operation, self.timings[operation])
        
        # Return stats for all operations
        stats = {}
        for op, times in self.timings.items():
            if times:
                stats[op] = self._compute_stats(op, times)
        return stats
    
    def _compute_stats(self, operation: str, times: deque) -> Dict:
        """Compute statistical summary for an operation."""
        arr = np.array(times)
        return {
            'operation': operation,
            'count': self.counts[operation],
            'mean_ms': float(np.mean(arr)),
            'median_ms': float(np.median(arr)),
            'p95_ms': float(np.percentile(arr, 95)),
            'p99_ms': float(np.percentile(arr, 99)),
            'min_ms': float(np.min(arr)),
            'max_ms': float(np.max(arr)),
            'std_ms': float(np.std(arr)),
        }
    
    def report(self, sort_by: str = 'mean_ms') -> str:
        """
        Generate a formatted performance report.
        
        Args:
            sort_by: Metric to sort by ('mean_ms', 'p95_ms', 'count', etc.)
            
        Returns:
            Formatted string report
        """
        stats = self.get_stats()
        if not stats:
            return "No profiling data available."
        
        # Sort operations by specified metric
        sorted_ops = sorted(
            stats.items(),
            key=lambda x: x[1].get(sort_by, 0),
            reverse=True
        )
        
        # Build report
        lines = [
            "=" * 80,
            "PERFORMANCE PROFILE REPORT",
            "=" * 80,
            f"{'Operation':<30} {'Count':>8} {'Mean':>10} {'P95':>10} {'P99':>10} {'Max':>10}",
            "-" * 80,
        ]
        
        for op, stat in sorted_ops:
            lines.append(
                f"{op:<30} {stat['count']:>8} "
                f"{stat['mean_ms']:>9.2f}ms {stat['p95_ms']:>9.2f}ms "
                f"{stat['p99_ms']:>9.2f}ms {stat['max_ms']:>9.2f}ms"
            )
        
        lines.append("=" * 80)
        return "\n".join(lines)
    
    def export_json(self, filepath: str):
        """
        Export profiling data to JSON file.
        
        Args:
            filepath: Path to output JSON file
        """
        stats = self.get_stats()
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(stats, f, indent=2)
    
    def reset(self):
        """Clear all profiling data."""
        self.timings.clear()
        self.counts.clear()
        self._active_ops.clear()
    
    def __enter__(self):
        """Context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Print report on exit."""
        if self.enabled:
            print(self.report())


class OperationTimer:
    """Context manager for timing operations with the profiler."""
    
    def __init__(self, profiler: PerformanceProfiler, operation: str):
        self.profiler = profiler
        self.operation = operation
    
    def __enter__(self):
        self.profiler.start(self.operation)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.end(self.operation)


# Global profiler instance (can be disabled in production)
_global_profiler = PerformanceProfiler(enabled=False)


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return _global_profiler


def profile_operation(operation: str):
    """
    Decorator to profile a function.
    
    Usage:
        @profile_operation('waveformer_inference')
        def separate_audio(audio):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with OperationTimer(_global_profiler, operation):
                return func(*args, **kwargs)
        return wrapper
    return decorator
