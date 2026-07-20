"""Request coalescing for rate limit checks.

When multiple concurrent requests arrive for the same client+endpoint
within a very short window, they can be coalesced into a single rate
limit check to reduce backend pressure.

Industry Usage:
    - CDN cache stampede protection (Cloudflare, Fastly)
    - Database query deduplication
    - Thundering herd mitigation
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from app.algorithms.base import RateLimitResult


@dataclass
class CoalescedResult:
    """A cached rate limit result for coalescing."""

    result: RateLimitResult
    timestamp: float
    request_count: int = 1


class RequestCoalescer:
    """Coalesces concurrent rate limit checks for the same key.

    If multiple requests for the same client+endpoint arrive within the
    coalescing window, only the first triggers an actual rate limit check.
    Subsequent requests in the window reuse the cached result.

    This reduces storage backend load under high concurrency without
    significantly affecting rate limit accuracy.

    Trade-offs:
        - Reduces backend calls by up to N-1 for N concurrent requests
        - Slight inaccuracy: coalesced requests share the same count
        - Window must be very small (typically 10-50ms) to maintain accuracy
    """

    def __init__(
        self,
        window_ms: float = 25.0,
        max_coalesce: int = 10,
        enabled: bool = True,
    ) -> None:
        """Initialize request coalescer.

        Args:
            window_ms: Coalescing window in milliseconds.
            max_coalesce: Maximum requests to coalesce before forcing a new check.
            enabled: Whether coalescing is active.
        """
        self._window_ms = window_ms
        self._max_coalesce = max_coalesce
        self._enabled = enabled
        self._cache: dict[str, CoalescedResult] = {}
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    @property
    def enabled(self) -> bool:
        """Whether coalescing is active."""
        return self._enabled

    def get_cached(self, client_id: str, endpoint: str) -> RateLimitResult | None:
        """Get a cached result if within the coalescing window.

        Args:
            client_id: The client making the request.
            endpoint: The endpoint being accessed.

        Returns:
            Cached RateLimitResult if available and fresh, None otherwise.
        """
        if not self._enabled:
            return None

        key = f"{client_id}:{endpoint}"
        now = time.time()

        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                self._stats["misses"] += 1
                return None

            age_ms = (now - cached.timestamp) * 1000
            if age_ms > self._window_ms or cached.request_count >= self._max_coalesce:
                # Expired or saturated
                del self._cache[key]
                self._stats["evictions"] += 1
                self._stats["misses"] += 1
                return None

            # Cache hit — reuse result but decrement remaining
            cached.request_count += 1
            self._stats["hits"] += 1

            # Adjust remaining count for the coalesced request
            adjusted_remaining = max(0, cached.result.remaining - cached.request_count + 1)
            return RateLimitResult(
                allowed=cached.result.allowed,
                limit=cached.result.limit,
                remaining=adjusted_remaining,
                reset_at=cached.result.reset_at,
                current_count=cached.result.current_count + cached.request_count - 1,
            )

    def cache_result(
        self, client_id: str, endpoint: str, result: RateLimitResult
    ) -> None:
        """Cache a rate limit result for potential coalescing.

        Args:
            client_id: The client making the request.
            endpoint: The endpoint being accessed.
            result: The rate limit result to cache.
        """
        if not self._enabled:
            return

        key = f"{client_id}:{endpoint}"
        with self._lock:
            self._cache[key] = CoalescedResult(
                result=result,
                timestamp=time.time(),
                request_count=1,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get coalescing statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
            return {
                "enabled": self._enabled,
                "window_ms": self._window_ms,
                "max_coalesce": self._max_coalesce,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "evictions": self._stats["evictions"],
                "hit_rate_percent": round(hit_rate, 1),
                "cached_keys": len(self._cache),
            }

    def clear(self) -> None:
        """Clear all cached results."""
        with self._lock:
            self._cache.clear()
