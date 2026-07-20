"""Sliding Window Counter rate limiting algorithm."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


class SlidingWindowCounterAlgorithm(RateLimitAlgorithm):
    """Sliding Window Counter algorithm.

    Combines fixed window counter with sliding window accuracy.
    Uses weighted average of current and previous window counts.

    Characteristics:
        - Good balance between accuracy and memory efficiency
        - O(1) time and space per request
        - Approximation of sliding window log
        - Lower memory than sliding window log
    """

    @property
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        return "sliding_window_counter"

    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed using sliding window counter.

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
        previous_window = current_window - 1

        current_key = f"{client_id}:{endpoint}:{current_window}"
        previous_key = f"{client_id}:{endpoint}:{previous_window}"

        # Get counts for current and previous windows
        current_count = repository.get_counter(current_key)
        previous_count = repository.get_counter(previous_key)

        # Calculate weight of previous window
        elapsed_in_current = now - (current_window * window)
        weight = 1.0 - (elapsed_in_current / window)

        # Weighted count
        weighted_count = previous_count * weight + current_count
        estimated_count = int(weighted_count)

        allowed = estimated_count < limit

        if allowed:
            repository.increment_counter(current_key, window)
            estimated_count += 1

        remaining = max(0, limit - estimated_count)
        reset_at = float((current_window + 1) * window)

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            current_count=estimated_count,
        )
