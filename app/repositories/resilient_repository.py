"""Resilient repository wrapper with circuit breaker pattern.

Wraps any RateLimitRepository with a circuit breaker. When the underlying
storage fails, falls back to permissive mode (allows all requests through)
rather than rejecting users due to infrastructure issues.
"""

from __future__ import annotations

from typing import Any

from app.logging.structured import get_logger
from app.repositories.base import RateLimitRepository
from app.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen


class ResilientRepository(RateLimitRepository):
    """Repository wrapper that adds circuit breaker resilience.

    When the underlying storage backend fails repeatedly, the circuit
    opens and all operations return permissive defaults:
        - increment_counter → returns 0 (no count, so never hits limit)
        - get_counter → returns 0
        - get_request_count → returns 0
        - get_token_bucket → returns None (triggers fresh bucket init)

    This implements a "fail-open" strategy: when rate limiting infrastructure
    is down, we allow traffic through rather than blocking users.

    Args:
        repository: The actual storage backend to wrap.
        circuit_breaker: Circuit breaker instance (shared or dedicated).
    """

    def __init__(
        self,
        repository: RateLimitRepository,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """Initialize resilient repository."""
        self._repository = repository
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._logger = get_logger()

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Access the circuit breaker for status checks."""
        return self._circuit_breaker

    @property
    def inner_repository(self) -> RateLimitRepository:
        """Access the wrapped repository."""
        return self._repository

    def increment_counter(self, key: str, ttl: int) -> int:
        """Increment counter with circuit breaker protection."""
        try:
            return self._circuit_breaker.execute(
                self._repository.increment_counter, key, ttl
            )
        except CircuitBreakerOpen:
            self._logger.debug(f"Circuit open: allowing request (counter bypass) for {key}")
            return 0
        except Exception as e:
            self._logger.error(f"Storage error in increment_counter: {e}")
            return 0

    def get_counter(self, key: str) -> int:
        """Get counter with circuit breaker protection."""
        try:
            return self._circuit_breaker.execute(self._repository.get_counter, key)
        except (CircuitBreakerOpen, Exception):
            return 0

    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add timestamp with circuit breaker protection."""
        try:
            self._circuit_breaker.execute(
                self._repository.add_request_timestamp, key, timestamp
            )
        except (CircuitBreakerOpen, Exception):
            pass

    def get_request_count(self, key: str, window_start: float) -> int:
        """Get request count with circuit breaker protection."""
        try:
            return self._circuit_breaker.execute(
                self._repository.get_request_count, key, window_start
            )
        except (CircuitBreakerOpen, Exception):
            return 0

    def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove expired entries with circuit breaker protection."""
        try:
            self._circuit_breaker.execute(
                self._repository.remove_expired_entries, key, window_start
            )
        except (CircuitBreakerOpen, Exception):
            pass

    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get token bucket with circuit breaker protection."""
        try:
            return self._circuit_breaker.execute(
                self._repository.get_token_bucket, key
            )
        except (CircuitBreakerOpen, Exception):
            return None

    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        """Set token bucket with circuit breaker protection."""
        try:
            self._circuit_breaker.execute(
                self._repository.set_token_bucket, key, tokens, last_refill
            )
        except (CircuitBreakerOpen, Exception):
            pass

    def clear(self) -> None:
        """Clear all data (bypasses circuit breaker for admin ops)."""
        try:
            self._repository.clear()
        except Exception as e:
            self._logger.error(f"Failed to clear repository: {e}")

    def health_check(self) -> bool:
        """Health check that includes circuit breaker state."""
        if self._circuit_breaker.state.value == "open":
            return False
        try:
            return self._repository.health_check()
        except Exception:
            return False
