"""In-memory implementation of the rate limit repository."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from app.repositories.base import RateLimitRepository


class MemoryRepository(RateLimitRepository):
    """Thread-safe in-memory storage for rate limit data.

    Uses dictionaries with proper locking for concurrency safety.
    Data is lost on application restart.

    Thread Safety:
        All operations acquire a lock before modifying shared state.
    """

    def __init__(self) -> None:
        """Initialize in-memory storage structures."""
        self._lock = threading.Lock()
        self._counters: dict[str, tuple[int, float]] = {}  # key -> (count, expires_at)
        self._timestamps: dict[str, list[float]] = defaultdict(list)  # key -> [timestamps]
        self._token_buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill)

    def increment_counter(self, key: str, ttl: int) -> int:
        """Increment a counter atomically.

        Args:
            key: Unique key for the counter.
            ttl: Time-to-live in seconds.

        Returns:
            New counter value.
        """
        with self._lock:
            now = time.time()
            if key in self._counters:
                count, expires_at = self._counters[key]
                if now < expires_at:
                    count += 1
                    self._counters[key] = (count, expires_at)
                    return count
            # Key expired or doesn't exist
            self._counters[key] = (1, now + ttl)
            return 1

    def get_counter(self, key: str) -> int:
        """Get current counter value.

        Args:
            key: Unique key for the counter.

        Returns:
            Current count or 0 if expired/missing.
        """
        with self._lock:
            if key in self._counters:
                count, expires_at = self._counters[key]
                if time.time() < expires_at:
                    return count
                del self._counters[key]
            return 0

    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add a timestamp to the request log.

        Args:
            key: Unique key for the timestamp log.
            timestamp: Unix timestamp of the request.
        """
        with self._lock:
            self._timestamps[key].append(timestamp)

    def get_request_count(self, key: str, window_start: float) -> int:
        """Count requests within the window.

        Args:
            key: Unique key for the timestamp log.
            window_start: Start of the window.

        Returns:
            Number of requests in the window.
        """
        with self._lock:
            timestamps = self._timestamps.get(key, [])
            return sum(1 for ts in timestamps if ts >= window_start)

    def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove timestamps before the window start.

        Args:
            key: Unique key for the timestamp log.
            window_start: Remove entries before this time.
        """
        with self._lock:
            if key in self._timestamps:
                self._timestamps[key] = [
                    ts for ts in self._timestamps[key] if ts >= window_start
                ]

    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state.

        Args:
            key: Unique key for the bucket.

        Returns:
            (tokens, last_refill) or None.
        """
        with self._lock:
            return self._token_buckets.get(key)

    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        """Set token bucket state.

        Args:
            key: Unique key for the bucket.
            tokens: Current token count.
            last_refill: Last refill timestamp.
        """
        with self._lock:
            self._token_buckets[key] = (tokens, last_refill)

    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            self._counters.clear()
            self._timestamps.clear()
            self._token_buckets.clear()

    def health_check(self) -> bool:
        """Memory storage is always healthy."""
        return True
