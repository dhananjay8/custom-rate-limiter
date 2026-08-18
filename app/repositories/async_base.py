"""Async rate limit storage interface.

Defines the contract for non-blocking storage backends that can be used with
an async-first rate limiter service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AsyncRateLimitRepository(ABC):
    """Abstract async repository for rate limit state."""

    @abstractmethod
    async def increment_counter(self, key: str, ttl: int) -> int:
        """Increment a counter and return the new value."""
        ...

    @abstractmethod
    async def get_counter(self, key: str) -> int:
        """Get the current counter value."""
        ...

    @abstractmethod
    async def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add a request timestamp (for sliding window log)."""
        ...

    @abstractmethod
    async def get_request_count(self, key: str, window_start: float) -> int:
        """Count timestamps after ``window_start``."""
        ...

    @abstractmethod
    async def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove timestamps before ``window_start``."""
        ...

    @abstractmethod
    async def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state or None if not set."""
        ...

    @abstractmethod
    async def set_token_bucket(
        self, key: str, tokens: float, last_refill: float
    ) -> None:
        """Set token bucket state."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Clear all rate limit state."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check storage health."""
        ...

    def get_config(self) -> dict[str, Any]:
        """Repository metadata for diagnostics."""
        return {"type": self.__class__.__name__}
