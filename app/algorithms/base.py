"""Base interface for rate limiting algorithms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


@dataclass(frozen=True)
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: float
    current_count: int

    @property
    def retry_after(self) -> float:
        """Seconds until the rate limit resets."""
        import time

        return max(0.0, self.reset_at - time.time())


class RateLimitAlgorithm(ABC):
    """Abstract base class for all rate limiting algorithms.

    Every algorithm must implement allow_request() which determines
    whether a given request should be allowed or rejected.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        ...

    @abstractmethod
    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Determine if a request should be allowed.

        Args:
            repository: Storage backend for rate limit state.
            client_id: Unique identifier for the client.
            endpoint: The endpoint being accessed.
            limit: Maximum number of requests in the window.
            window: Window size in seconds.

        Returns:
            RateLimitResult indicating whether the request is allowed.
        """
        ...
