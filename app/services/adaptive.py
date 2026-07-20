"""Adaptive rate limiting based on system load.

Dynamically adjusts effective rate limits based on current system metrics
(CPU usage, memory pressure, response latency). Under high load, limits
are tightened to protect the system; under low load, limits can be relaxed.

Industry Usage:
    - Netflix: Adaptive concurrency limits
    - AWS API Gateway: Throttling based on account-level usage
    - Google Cloud: Dynamic quota management
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from app.logging.structured import get_logger


class LoadLevel(str, Enum):
    """System load level classification."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SystemMetrics:
    """Current system metrics snapshot."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    avg_response_ms: float = 0.0
    active_requests: int = 0
    timestamp: float = field(default_factory=time.time)


class AdaptiveRateLimiter:
    """Adjusts rate limits dynamically based on system load.

    Load Factor Multipliers:
        - LOW load: 1.2x (relax limits by 20%)
        - NORMAL load: 1.0x (no change)
        - HIGH load: 0.7x (tighten by 30%)
        - CRITICAL load: 0.4x (tighten by 60%)

    System metrics considered:
        - CPU usage percentage
        - Memory usage percentage
        - Average response latency
        - Active concurrent request count

    Thread-safe: all state updates are guarded by a lock.
    """

    # Load level thresholds
    _LOAD_THRESHOLDS = {
        LoadLevel.LOW: {"cpu_max": 30, "memory_max": 40, "latency_max": 50},
        LoadLevel.NORMAL: {"cpu_max": 60, "memory_max": 70, "latency_max": 200},
        LoadLevel.HIGH: {"cpu_max": 85, "memory_max": 85, "latency_max": 500},
        # CRITICAL: anything above HIGH
    }

    # Multipliers for each load level
    _LOAD_MULTIPLIERS = {
        LoadLevel.LOW: 1.2,
        LoadLevel.NORMAL: 1.0,
        LoadLevel.HIGH: 0.7,
        LoadLevel.CRITICAL: 0.4,
    }

    def __init__(
        self,
        enabled: bool = True,
        sample_interval: float = 5.0,
        min_multiplier: float = 0.3,
        max_multiplier: float = 1.5,
    ) -> None:
        """Initialize adaptive rate limiter.

        Args:
            enabled: Whether adaptive limiting is active.
            sample_interval: How often to re-evaluate system metrics (seconds).
            min_multiplier: Minimum allowed multiplier (floor).
            max_multiplier: Maximum allowed multiplier (ceiling).
        """
        self._enabled = enabled
        self._sample_interval = sample_interval
        self._min_multiplier = min_multiplier
        self._max_multiplier = max_multiplier

        self._lock = threading.Lock()
        self._current_metrics = SystemMetrics()
        self._current_load = LoadLevel.NORMAL
        self._current_multiplier = 1.0
        self._last_sample_time = 0.0
        self._response_times: list[float] = []
        self._active_requests = 0
        self._logger = get_logger()

    @property
    def enabled(self) -> bool:
        """Whether adaptive limiting is active."""
        return self._enabled

    @property
    def current_multiplier(self) -> float:
        """Current rate limit multiplier."""
        if not self._enabled:
            return 1.0
        self._maybe_update_metrics()
        return self._current_multiplier

    @property
    def current_load(self) -> LoadLevel:
        """Current system load level."""
        return self._current_load

    def get_effective_limit(self, base_limit: int) -> int:
        """Calculate effective limit after applying adaptive multiplier.

        Args:
            base_limit: The configured base rate limit.

        Returns:
            Adjusted limit (always at least 1).
        """
        if not self._enabled:
            return base_limit
        return max(1, int(base_limit * self.current_multiplier))

    def record_request_start(self) -> None:
        """Record that a request has started processing."""
        with self._lock:
            self._active_requests += 1

    def record_request_end(self, response_time_ms: float) -> None:
        """Record that a request has finished processing.

        Args:
            response_time_ms: Time taken to process the request in milliseconds.
        """
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._response_times.append(response_time_ms)
            # Keep only last 100 samples
            if len(self._response_times) > 100:
                self._response_times = self._response_times[-100:]

    def _maybe_update_metrics(self) -> None:
        """Re-evaluate system metrics if sample interval has elapsed."""
        now = time.time()
        if now - self._last_sample_time < self._sample_interval:
            return

        with self._lock:
            if now - self._last_sample_time < self._sample_interval:
                return  # Double-check under lock

            self._last_sample_time = now
            self._current_metrics = self._collect_metrics()
            self._current_load = self._classify_load(self._current_metrics)
            new_multiplier = self._LOAD_MULTIPLIERS[self._current_load]

            # Smooth transition (exponential moving average)
            self._current_multiplier = (
                0.7 * self._current_multiplier + 0.3 * new_multiplier
            )
            # Clamp to bounds
            self._current_multiplier = max(
                self._min_multiplier,
                min(self._max_multiplier, self._current_multiplier),
            )

    def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        cpu_percent = self._get_cpu_usage()
        memory_percent = self._get_memory_usage()
        avg_response = (
            sum(self._response_times) / len(self._response_times)
            if self._response_times
            else 0.0
        )

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            avg_response_ms=avg_response,
            active_requests=self._active_requests,
        )

    def _classify_load(self, metrics: SystemMetrics) -> LoadLevel:
        """Classify system load based on metrics."""
        if (
            metrics.cpu_percent <= self._LOAD_THRESHOLDS[LoadLevel.LOW]["cpu_max"]
            and metrics.memory_percent <= self._LOAD_THRESHOLDS[LoadLevel.LOW]["memory_max"]
            and metrics.avg_response_ms <= self._LOAD_THRESHOLDS[LoadLevel.LOW]["latency_max"]
        ):
            return LoadLevel.LOW

        if (
            metrics.cpu_percent <= self._LOAD_THRESHOLDS[LoadLevel.NORMAL]["cpu_max"]
            and metrics.memory_percent <= self._LOAD_THRESHOLDS[LoadLevel.NORMAL]["memory_max"]
            and metrics.avg_response_ms <= self._LOAD_THRESHOLDS[LoadLevel.NORMAL]["latency_max"]
        ):
            return LoadLevel.NORMAL

        if (
            metrics.cpu_percent <= self._LOAD_THRESHOLDS[LoadLevel.HIGH]["cpu_max"]
            and metrics.memory_percent <= self._LOAD_THRESHOLDS[LoadLevel.HIGH]["memory_max"]
            and metrics.avg_response_ms <= self._LOAD_THRESHOLDS[LoadLevel.HIGH]["latency_max"]
        ):
            return LoadLevel.HIGH

        return LoadLevel.CRITICAL

    @staticmethod
    def _get_cpu_usage() -> float:
        """Get current CPU usage percentage (cross-platform)."""
        try:
            load_avg = os.getloadavg()[0]
            cpu_count = os.cpu_count() or 1
            return min(100.0, (load_avg / cpu_count) * 100)
        except (OSError, AttributeError):
            return 50.0  # Default moderate assumption

    @staticmethod
    def _get_memory_usage() -> float:
        """Get current memory usage percentage."""
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem_total = int(lines[0].split()[1])
            mem_available = int(lines[2].split()[1])
            return ((mem_total - mem_available) / mem_total) * 100
        except (FileNotFoundError, IndexError, ValueError):
            # macOS or systems without /proc
            try:
                import subprocess

                result = subprocess.run(
                    ["vm_stat"], capture_output=True, text=True, timeout=2
                )
                # Rough estimation from vm_stat output
                lines = result.stdout.split("\n")
                page_size = 16384  # typical macOS page size
                free = 0
                for line in lines:
                    if "Pages free" in line:
                        free = int(line.split(":")[1].strip().rstrip(".")) * page_size
                        break
                # If we can't determine, assume moderate usage
                return 50.0 if free == 0 else min(100.0, max(0.0, 100.0 - (free / (8 * 1024**3) * 100)))
            except Exception:
                return 50.0

    def get_status(self) -> dict:
        """Get adaptive limiter status for monitoring."""
        return {
            "enabled": self._enabled,
            "current_load": self._current_load.value,
            "current_multiplier": round(self._current_multiplier, 3),
            "metrics": {
                "cpu_percent": round(self._current_metrics.cpu_percent, 1),
                "memory_percent": round(self._current_metrics.memory_percent, 1),
                "avg_response_ms": round(self._current_metrics.avg_response_ms, 2),
                "active_requests": self._current_metrics.active_requests,
            },
        }
