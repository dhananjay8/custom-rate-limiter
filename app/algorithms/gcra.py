"""Generic Cell Rate Algorithm (GCRA) for rate limiting.

GCRA is a scheduling-based algorithm that determines whether a request
should be allowed by maintaining a "theoretical arrival time" (TAT).
It is mathematically equivalent to a token bucket but uses only a single
timestamp value per key, making it memory-efficient and atomic-friendly.

Industry Usage:
    - Stripe API rate limiting
    - Shopify API throttling
    - GitHub API (variant)
    - ATM networks (ITU-T I.371, Traffic Policing)
    - Telecom GCRA/Virtual Scheduling

References:
    - ITU-T Recommendation I.371 (Traffic control and congestion control)
    - Stripe Engineering Blog: "Scaling API rate limiters"
    - RFC 2698 (A Two Rate Three Color Marker)

Also known as:
    - Virtual Scheduling Algorithm
    - Continuous Token Bucket
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


class GCRAAlgorithm(RateLimitAlgorithm):
    """Generic Cell Rate Algorithm implementation.

    GCRA tracks a single value per key: the Theoretical Arrival Time (TAT),
    which represents the earliest time the next request should arrive.

    Key concepts:
        - Emission interval (T): minimum time between requests = window / limit
        - Burst tolerance (τ): maximum deviation allowed = T * (limit - 1)
        - TAT: the next expected "ideal" arrival time

    Decision logic:
        - If now >= TAT - τ: allow, update TAT = max(now, TAT) + T
        - Otherwise: reject (request arrived too early)

    Characteristics:
        - Single timestamp storage per key (extremely memory-efficient)
        - Mathematically equivalent to token bucket
        - Naturally supports burst tolerance
        - O(1) time and space per request
        - Atomic-friendly (single CAS on TAT value)
        - No background cleanup required
    """

    @property
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        return "gcra"

    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed using GCRA.

        Args:
            repository: Storage backend for rate limit state.
            client_id: Unique identifier for the client.
            endpoint: The endpoint being accessed.
            limit: Maximum requests allowed in the window (burst capacity).
            window: Window size in seconds.

        Returns:
            RateLimitResult with the decision.
        """
        now = time.time()
        tat_key = f"{client_id}:{endpoint}:gcra"

        # Emission interval: minimum spacing between requests
        emission_interval = window / limit

        # Burst tolerance (τ): how far ahead TAT can be from now
        # Allows `limit` requests in a burst
        burst_tolerance = emission_interval * (limit - 1)

        # Get current TAT (stored as tokens=TAT, last_refill=0 in the bucket store)
        bucket_state = repository.get_token_bucket(tat_key)

        if bucket_state is None:
            # First request ever: set TAT to now + emission_interval
            new_tat = now + emission_interval
            repository.set_token_bucket(tat_key, new_tat, 0.0)

            remaining = limit - 1
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=now + window,
                current_count=1,
            )

        tat, _ = bucket_state

        # Allow window: from (TAT - burst_tolerance) to infinity
        allow_at = tat - burst_tolerance

        if now >= allow_at:
            # Request is within the conforming window — ALLOW
            new_tat = max(tat, now) + emission_interval
            repository.set_token_bucket(tat_key, new_tat, 0.0)

            # Remaining: how many more requests fit before TAT exceeds burst limit
            time_until_full = (now + burst_tolerance + emission_interval) - new_tat
            remaining = max(0, int(time_until_full / emission_interval))

            # Current count estimation
            current_count = limit - remaining

            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=now + window,
                current_count=current_count,
            )

        # Request arrived too early — REJECT
        retry_after = allow_at - now

        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            reset_at=now + retry_after,
            current_count=limit,
        )
