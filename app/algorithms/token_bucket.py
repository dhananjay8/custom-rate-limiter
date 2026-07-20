"""Token Bucket rate limiting algorithm."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult

if TYPE_CHECKING:
    from app.repositories.base import RateLimitRepository


class TokenBucketAlgorithm(RateLimitAlgorithm):
    """Token Bucket algorithm.

    Maintains a bucket of tokens that refill at a constant rate.
    Each request consumes one token. Allows bursts up to bucket capacity.

    Characteristics:
        - Allows controlled bursts
        - Smooth rate limiting
        - O(1) per request
        - Used by AWS, NGINX, Envoy, Kong, Cloudflare
    """

    @property
    def name(self) -> str:
        """Human-readable name of the algorithm."""
        return "token_bucket"

    def allow_request(
        self,
        repository: RateLimitRepository,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> RateLimitResult:
        """Check if request is allowed using token bucket.

        Args:
            repository: Storage backend for rate limit state.
            client_id: Unique identifier for the client.
            endpoint: The endpoint being accessed.
            limit: Maximum tokens (bucket capacity).
            window: Time in seconds to fully refill the bucket.

        Returns:
            RateLimitResult with the decision.
        """
        now = time.time()
        bucket_key = f"{client_id}:{endpoint}:bucket"

        # Refill rate: tokens per second
        refill_rate = limit / window

        # Get current bucket state
        bucket_state = repository.get_token_bucket(bucket_key)

        if bucket_state is None:
            # First request: initialize bucket with full tokens minus 1
            tokens = limit - 1
            repository.set_token_bucket(bucket_key, tokens, now)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=tokens,
                reset_at=now + window,
                current_count=1,
            )

        last_tokens, last_refill = bucket_state

        # Calculate tokens to add based on elapsed time
        elapsed = now - last_refill
        new_tokens = elapsed * refill_rate
        tokens = min(limit, last_tokens + new_tokens)

        allowed = tokens >= 1.0

        if allowed:
            tokens -= 1.0

        repository.set_token_bucket(bucket_key, tokens, now)

        remaining = max(0, int(tokens))
        current_count = limit - int(tokens)
        # Time until one token refills
        reset_at = now + (1.0 / refill_rate) if not allowed else now + window

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            current_count=current_count,
        )
