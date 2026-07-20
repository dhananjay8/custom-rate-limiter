"""Leaky Bucket rate limiting algorithm.

The Leaky Bucket enforces a constant output rate regardless of burst input.
Requests are processed (leaked) at a fixed rate. If the bucket overflows,
requests are rejected.

Industry Usage:
    - NGINX (ngx_http_limit_req_module)
    - Network traffic shaping (QoS)
    - Telecom (ITU-T I.371)
    - Cisco IOS rate limiting

References:
    - Turner, J. (1986). "New directions in communications"
    - ITU-T Recommendation I.371
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


class LeakyBucketAlgorithm(RateLimitAlgorithm):
    """Leaky Bucket algorithm implementation.

    Conceptually, requests fill a bucket that leaks at a constant rate.
    The bucket has a maximum capacity (burst size). When the bucket is full,
    incoming requests are rejected.

    Unlike Token Bucket which allows bursts, Leaky Bucket enforces a strict
    constant drain rate, providing smooth traffic shaping.

    Characteristics:
        - Enforces constant output rate
        - No burst allowance beyond queue capacity
        - O(1) per request
        - Memory: single counter + timestamp per key
        - Deterministic behavior under load
    """

    @property
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        return "leaky_bucket"

    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed using leaky bucket semantics.

        The bucket has capacity equal to `limit`. It drains at a rate of
        `limit / window` requests per second. If adding a request would
        overflow the bucket, it is rejected.

        Args:
            repository: Storage backend for rate limit state.
            client_id: Unique identifier for the client.
            endpoint: The endpoint being accessed.
            limit: Bucket capacity (maximum queue depth).
            window: Time in seconds to fully drain the bucket.

        Returns:
            RateLimitResult with the decision.
        """
        now = time.time()
        bucket_key = f"{client_id}:{endpoint}:leaky"

        # Drain rate: requests leaked per second
        drain_rate = limit / window

        bucket_state = repository.get_token_bucket(bucket_key)

        if bucket_state is None:
            # First request: bucket starts with 1 unit of water
            water_level = 1.0
            repository.set_token_bucket(bucket_key, water_level, now)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit - 1,
                reset_at=now + window,
                current_count=1,
            )

        last_water_level, last_check = bucket_state

        # Calculate how much water has leaked since last check
        elapsed = now - last_check
        leaked = elapsed * drain_rate
        current_water = max(0.0, last_water_level - leaked)

        # Try to add one unit of water
        if current_water + 1.0 <= limit:
            # Bucket has room
            current_water += 1.0
            repository.set_token_bucket(bucket_key, current_water, now)
            remaining = max(0, int(limit - current_water))
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                reset_at=now + window,
                current_count=int(current_water),
            )

        # Bucket overflow — reject
        repository.set_token_bucket(bucket_key, current_water, now)
        # Time until enough water leaks for one new request
        time_until_space = (current_water + 1.0 - limit) / drain_rate

        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            reset_at=now + time_until_space,
            current_count=int(current_water),
        )
