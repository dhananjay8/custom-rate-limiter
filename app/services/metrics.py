"""Metrics service for tracking application performance."""

from __future__ import annotations

import time
from typing import Any


class AppMetrics:
    """Application-level metrics tracking."""

    def __init__(self) -> None:
        """Initialize application metrics."""
        self._start_time = time.time()

    @property
    def uptime_seconds(self) -> float:
        """Get application uptime in seconds."""
        return time.time() - self._start_time

    def get_health_info(self) -> dict[str, Any]:
        """Get health information.

        Returns:
            Dictionary with health status details.
        """
        return {
            "uptime_seconds": round(self.uptime_seconds, 2),
            "started_at": self._start_time,
        }
