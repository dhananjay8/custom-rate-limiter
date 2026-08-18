"""In-memory async rate limit repository.

Provides an async-native, non-blocking storage backend backed by Python dicts
and per-key ``asyncio.Lock`` instances. This is useful for high-concurrency
async workloads or as a reference implementation for async storage drivers.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from app.repositories.async_base import AsyncRateLimitRepository


class AsyncMemoryRepository(AsyncRateLimitRepository):
    """Async in-memory repository for rate limiting state."""

    def __init__(self) -> None:
        """Initialize the async in-memory storage."""
        self._counters: dict[str, int] = {}
        self._counter_locks: dict[str, asyncio.Lock] = {}
        self._timestamps: dict[str, deque[float]] = {}
        self._timestamp_locks: dict[str, asyncio.Lock] = {}
        self._token_buckets: dict[str, tuple[float, float]] = {}
        self._token_locks: dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()

    def _get_counter_lock(self, key: str) -> asyncio.Lock:
        if key not in self._counter_locks:
            self._counter_locks[key] = asyncio.Lock()
        return self._counter_locks[key]

    def _get_timestamp_lock(self, key: str) -> asyncio.Lock:
        if key not in self._timestamp_locks:
            self._timestamp_locks[key] = asyncio.Lock()
        return self._timestamp_locks[key]

    def _get_token_lock(self, key: str) -> asyncio.Lock:
        if key not in self._token_locks:
            self._token_locks[key] = asyncio.Lock()
        return self._token_locks[key]

    async def increment_counter(self, key: str, ttl: int) -> int:
        """Increment a counter and return the new value."""
        async with self._get_counter_lock(key):
            self._counters[key] = self._counters.get(key, 0) + 1
            return self._counters[key]

    async def get_counter(self, key: str) -> int:
        """Get the current counter value."""
        async with self._get_counter_lock(key):
            return self._counters.get(key, 0)

    async def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add a request timestamp."""
        async with self._get_timestamp_lock(key):
            if key not in self._timestamps:
                self._timestamps[key] = deque()
            self._timestamps[key].append(timestamp)

    async def get_request_count(self, key: str, window_start: float) -> int:
        """Count timestamps after ``window_start``."""
        async with self._get_timestamp_lock(key):
            ts = self._timestamps.get(key, deque())
            return sum(1 for t in ts if t >= window_start)

    async def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove timestamps before ``window_start``."""
        async with self._get_timestamp_lock(key):
            ts = self._timestamps.get(key, deque())
            while ts and ts[0] < window_start:
                ts.popleft()

    async def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state or None."""
        async with self._get_token_lock(key):
            return self._token_buckets.get(key)

    async def set_token_bucket(
        self, key: str, tokens: float, last_refill: float
    ) -> None:
        """Set token bucket state."""
        async with self._get_token_lock(key):
            self._token_buckets[key] = (tokens, last_refill)

    async def clear(self) -> None:
        """Clear all state."""
        async with self._lock:
            self._counters.clear()
            self._counter_locks.clear()
            self._timestamps.clear()
            self._timestamp_locks.clear()
            self._token_buckets.clear()
            self._token_locks.clear()

    async def health_check(self) -> bool:
        """In-memory is always healthy if accessible."""
        return True

    def get_config(self) -> dict[str, Any]:
        """Repository metadata for diagnostics."""
        return {"type": "async_memory"}
