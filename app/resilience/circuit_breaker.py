"""Circuit Breaker pattern for storage backend resilience.

Prevents cascading failures when the storage backend (Redis, SQLite) becomes
unavailable. Falls back to permissive mode (allow all) when the circuit is open.

States:
    CLOSED  → Normal operation, requests go through to storage
    OPEN    → Storage is unhealthy, all requests bypass rate limiting
    HALF_OPEN → Testing if storage has recovered

References:
    - Martin Fowler: "CircuitBreaker" pattern
    - Michael Nygard: "Release It!" (Stability Patterns)
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable, TypeVar

from app.logging.structured import get_logger

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when circuit is open and operation is bypassed."""

    pass


class CircuitBreaker:
    """Circuit Breaker for storage backend operations.

    When consecutive failures exceed the threshold, the circuit opens and
    operations are bypassed (fail-open strategy for rate limiting means
    requests are ALLOWED through rather than rejected).

    After a recovery timeout, the circuit transitions to half-open state
    where a single test request determines if the backend has recovered.

    Args:
        failure_threshold: Number of consecutive failures to trip the circuit.
        recovery_timeout: Seconds to wait before attempting recovery.
        success_threshold: Successful calls in half-open state to close circuit.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        """Initialize circuit breaker."""
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()
        self._logger = get_logger()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    self._logger.info("Circuit breaker transitioning to HALF_OPEN")
            return self._state

    @property
    def is_closed(self) -> bool:
        """Whether the circuit is in normal operation."""
        return self.state == CircuitState.CLOSED

    def execute(self, operation: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute an operation through the circuit breaker.

        Args:
            operation: The function to execute.
            *args: Positional arguments for the operation.
            **kwargs: Keyword arguments for the operation.

        Returns:
            The result of the operation.

        Raises:
            CircuitBreakerOpen: If the circuit is open and the operation is bypassed.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpen(
                f"Circuit is OPEN. Recovery in "
                f"{self._recovery_timeout - (time.time() - self._last_failure_time):.1f}s"
            )

        try:
            result = operation(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise

    def _record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._state = CircuitState.CLOSED
                    self._logger.info("Circuit breaker CLOSED (recovered)")

    def _record_failure(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._logger.warning("Circuit breaker re-OPENED from HALF_OPEN")
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._logger.warning(
                    f"Circuit breaker OPENED after {self._failure_count} failures"
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0

    def get_status(self) -> dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout": self._recovery_timeout,
            "last_failure_time": self._last_failure_time,
        }
