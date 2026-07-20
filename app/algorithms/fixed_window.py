"""Fixed Window Counter rate limiting algorithm."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


class FixedWindowAlgorithm(RateLimitAlgorithm):
    """Fixed Window Counter algorithm.

    Divides time into fixed windows and counts requests per window.
    Simple O(1) time and space complexity per request.

    Characteristics:
        - Simple and memory efficient
        - Can allow up to 2x burst at window boundaries
        - O(1) per request
    """

    @property
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        return "fixed_window"

    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed using fixed window counter.

        Args:
            repository: Storage backend for rate limit state.
            client_id: Unique identifier for the client.
            endpoint: The endpoint being accessed.
            limit: Maximum number of requests in the window.
            window: Window size in seconds.

        Returns:
            RateLimitResult with the decision.
        """
        now = time.time()
        current_window = int(now // window)
        window_key = f"{client_id}:{endpoint}:{current_window}"
        reset_at = (current_window + 1) * window

        count = repository.increment_counter(window_key, window)

        allowed = count <= limit
        remaining = max(0, limit - count)

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=float(reset_at),
            current_count=count,
        )
