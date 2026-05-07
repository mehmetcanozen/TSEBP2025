"""Process resource monitoring helpers for evaluation workers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from subprocess import Popen
from typing import Any


@dataclass
class ResourceSummary:
    peak_rss_mb: float = 0.0
    average_cpu_percent: float = 0.0
    cpu_time_seconds: float = 0.0
    sample_count: int = 0
    monitor_status: str = "ok"

    def to_row(self) -> dict[str, Any]:
        return {
            "peak_rss_mb": self.peak_rss_mb,
            "average_cpu_percent": self.average_cpu_percent,
            "cpu_time_seconds": self.cpu_time_seconds,
            "sample_count": self.sample_count,
            "monitor_status": self.monitor_status,
        }


def monitor_process(process: Popen, interval_seconds: float = 0.25) -> ResourceSummary:
    """Poll a worker process tree until it exits."""

    try:
        import psutil  # type: ignore
    except Exception as exc:  # pragma: no cover - fallback when psutil is absent
        process.wait()
        return ResourceSummary(monitor_status=f"psutil unavailable: {type(exc).__name__}")

    try:
        root = psutil.Process(process.pid)
    except psutil.Error:
        process.wait()
        return ResourceSummary(monitor_status="process exited before first sample")
    peak_rss = 0
    cpu_values: list[float] = []
    cpu_time_seconds = 0.0
    try:
        root.cpu_percent(interval=None)
    except Exception:
        pass

    while process.poll() is None:
        processes = [root]
        try:
            processes.extend(root.children(recursive=True))
        except psutil.Error:
            pass

        rss = 0
        cpu_percent = 0.0
        cpu_time = 0.0
        for item in processes:
            try:
                memory = item.memory_info()
                times = item.cpu_times()
                rss += int(memory.rss)
                cpu_percent += float(item.cpu_percent(interval=None))
                cpu_time += float(times.user + times.system)
            except psutil.Error:
                continue
        peak_rss = max(peak_rss, rss)
        cpu_values.append(cpu_percent)
        cpu_time_seconds = max(cpu_time_seconds, cpu_time)
        time.sleep(max(float(interval_seconds), 0.05))

    process.wait()
    return ResourceSummary(
        peak_rss_mb=peak_rss / (1024.0 * 1024.0),
        average_cpu_percent=sum(cpu_values) / max(len(cpu_values), 1),
        cpu_time_seconds=cpu_time_seconds,
        sample_count=len(cpu_values),
    )
