"""Redis implementation of the rate limit repository.

Provides distributed rate limiting via Redis. Supports both standalone
Redis and Redis Cluster. Uses Lua scripts for atomic operations.

Industry Usage:
    - Stripe, Cloudflare, GitHub, Discord
    - Any multi-node deployment requiring shared state
"""

from __future__ import annotations

import time
from typing import Any

from app.repositories.base import RateLimitRepository


class RedisRepository(RateLimitRepository):
    """Redis-based distributed storage for rate limit data.

    Uses Redis atomic operations (INCR, EXPIRE, Lua scripts) to ensure
    correctness under concurrent access across multiple application instances.

    Features:
        - Atomic increment with TTL via Lua script
        - Sorted sets for timestamp logs (efficient range queries)
        - Hash fields for token bucket state
        - Connection pooling for performance
        - Automatic reconnection on failure
    """

    # Lua script for atomic increment with TTL
    _INCREMENT_SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
        redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    return current
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        key_prefix: str = "ratelimit:",
        connection_pool_size: int = 10,
    ) -> None:
        """Initialize Redis repository.

        Args:
            url: Redis connection URL.
            key_prefix: Prefix for all Redis keys to avoid collisions.
            connection_pool_size: Maximum number of connections in the pool.
        """
        try:
            import redis
        except ImportError as e:
            raise ImportError(
                "redis package is required for Redis storage backend. "
                "Install with: pip install redis"
            ) from e

        self._prefix = key_prefix
        self._client: redis.Redis = redis.Redis.from_url(
            url,
            max_connections=connection_pool_size,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        self._increment_script = self._client.register_script(self._INCREMENT_SCRIPT)

    def _key(self, key: str) -> str:
        """Create a prefixed Redis key."""
        return f"{self._prefix}{key}"

    def increment_counter(self, key: str, ttl: int) -> int:
        """Atomically increment a counter with TTL using Lua script.

        Args:
            key: Unique key for the counter.
            ttl: Time-to-live in seconds for auto-expiry.

        Returns:
            The new counter value after increment.
        """
        result = self._increment_script(keys=[self._key(key)], args=[ttl])
        return int(result)

    def get_counter(self, key: str) -> int:
        """Get the current value of a counter.

        Args:
            key: Unique key for the counter.

        Returns:
            Current counter value, or 0 if not found/expired.
        """
        value = self._client.get(self._key(key))
        return int(value) if value is not None else 0

    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add a request timestamp using a Redis sorted set.

        The score is the timestamp itself, enabling efficient range queries.

        Args:
            key: Unique key for the timestamp log.
            timestamp: Unix timestamp of the request.
        """
        redis_key = self._key(f"ts:{key}")
        self._client.zadd(redis_key, {str(timestamp): timestamp})

    def get_request_count(self, key: str, window_start: float) -> int:
        """Count requests within the window using sorted set range.

        Args:
            key: Unique key for the timestamp log.
            window_start: Start of the current window (unix timestamp).

        Returns:
            Number of requests within the window.
        """
        redis_key = self._key(f"ts:{key}")
        return self._client.zcount(redis_key, window_start, "+inf")

    def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove entries older than the window start from sorted set.

        Args:
            key: Unique key for the timestamp log.
            window_start: Entries before this time are expired.
        """
        redis_key = self._key(f"ts:{key}")
        self._client.zremrangebyscore(redis_key, "-inf", window_start)

    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get current token bucket state from Redis hash.

        Args:
            key: Unique key for the token bucket.

        Returns:
            Tuple of (tokens, last_refill_timestamp) or None if not initialized.
        """
        redis_key = self._key(f"bucket:{key}")
        data = self._client.hgetall(redis_key)
        if not data:
            return None
        return (float(data["tokens"]), float(data["last_refill"]))

    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        """Set token bucket state in Redis hash.

        Args:
            key: Unique key for the token bucket.
            tokens: Current number of tokens.
            last_refill: Timestamp of last refill calculation.
        """
        redis_key = self._key(f"bucket:{key}")
        self._client.hset(redis_key, mapping={"tokens": str(tokens), "last_refill": str(last_refill)})

    def clear(self) -> None:
        """Clear all rate limit data (keys with our prefix only)."""
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=f"{self._prefix}*", count=100)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break

    def health_check(self) -> bool:
        """Check if Redis is accessible.

        Returns:
            True if Redis responds to PING.
        """
        try:
            return self._client.ping()
        except Exception:
            return False

    def close(self) -> None:
        """Close the Redis connection pool."""
        self._client.close()
