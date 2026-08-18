"""TTL cache for dynamic configuration snapshots.

Provides a simple in-memory cache with configurable TTL and size limit,
plus explicit invalidation so updates are reflected immediately.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class ConfigCache(Generic[T]):
    """In-memory cache with TTL and size bound.

    Args:
        ttl_seconds: Time-to-live for cached values.
        max_size: Maximum number of entries to retain.
    """

    def __init__(self, ttl_seconds: float = 1.0, max_size: int = 128) -> None:
        """Initialize the cache."""
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._cache: dict[str, tuple[float, T]] = {}
        self._lock = threading.Lock()

    def get_or_load(self, key: str, loader: Callable[[], T]) -> T:
        """Return a cached value or load and store it if missing/stale.

        Args:
            key: Cache key.
            loader: Callable that returns the fresh value.

        Returns:
            The cached or freshly loaded value.
        """
        with self._lock:
            now = time.time()
            cached = self._cache.get(key)
            if cached is not None and now - cached[0] <= self._ttl:
                return cached[1]

            value = loader()
            self._cache[key] = (now, value)

            # Evict oldest if over size
            while len(self._cache) > self._max_size:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest]

            return value

    def set(self, key: str, value: T) -> None:
        """Store a value directly, bypassing TTL checks."""
        with self._lock:
            self._cache[key] = (time.time(), value)

    def invalidate(self, key: str | None = None) -> None:
        """Invalidate a specific key or the entire cache."""
        with self._lock:
            if key is None:
                self._cache.clear()
            else:
                self._cache.pop(key, None)

    def get_status(self) -> dict[str, Any]:
        """Get cache status for diagnostics."""
        with self._lock:
            return {
                "enabled": True,
                "ttl_seconds": self._ttl,
                "max_size": self._max_size,
                "current_size": len(self._cache),
                "keys": list(self._cache.keys()),
            }
