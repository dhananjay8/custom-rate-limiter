"""Sliding Window Log rate limiting algorithm."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


class SlidingWindowLogAlgorithm(RateLimitAlgorithm):
    """Sliding Window Log algorithm.

    Maintains a log of all request timestamps and counts requests
    within the sliding window. More accurate than fixed window but
    uses more memory.

    Characteristics:
        - Precise rate limiting with no boundary issues
        - O(n) space where n = number of requests in window
        - O(log n) time with sorted data structures
        - Higher memory usage than fixed window
    """

    @property
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        return "sliding_window_log"

    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed using sliding window log.

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
        window_start = now - window
        log_key = f"{client_id}:{endpoint}"

        # Remove expired entries and get current count
        repository.remove_expired_entries(log_key, window_start)
        count = repository.get_request_count(log_key, window_start)

        allowed = count < limit

        if allowed:
            repository.add_request_timestamp(log_key, now)
            count += 1

        remaining = max(0, limit - count)
        reset_at = now + window

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            current_count=count,
        )
