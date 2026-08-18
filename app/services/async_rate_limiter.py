"""Async facade over the synchronous rate limiter service.

Offloads synchronous ``RateLimiterService.check_rate_limit`` calls to a
thread-pool executor, allowing async web frameworks or consumers to await
rate limit decisions without blocking the event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.algorithms.base import RateLimitResult
from app.services.rate_limiter import RateLimiterService


class AsyncRateLimiterService:
    """Async API for rate limiting backed by a thread-pool executor.

    This is the first step toward a fully non-blocking implementation:
    it keeps the existing battle-tested synchronous algorithms and storage
    drivers while exposing ``async def`` entrypoints for async callers.

    Args:
        rate_limiter: The synchronous ``RateLimiterService`` to wrap.
    """

    def __init__(self, rate_limiter: RateLimiterService) -> None:
        """Initialize the async facade."""
        self._rate_limiter = rate_limiter

    async def check_rate_limit(
        self,
        client_id: str,
        endpoint: str,
        method: str = "GET",
        request_weight: int | None = None,
        shadow: bool = False,
    ) -> RateLimitResult:
        """Check a request asynchronously.

        Args:
            client_id: Authenticated client.
            endpoint: Endpoint name.
            method: HTTP method.
            request_weight: Optional override cost.
            shadow: If True, run a non-enforcing preview.

        Returns:
            ``RateLimitResult`` from the wrapped service.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._rate_limiter.check_rate_limit,
            client_id,
            endpoint,
            method,
            request_weight,
            shadow,
        )

    @property
    def metrics(self) -> dict[str, Any]:
        """Expose current metrics synchronously."""
        return self._rate_limiter.metrics.get_metrics()
