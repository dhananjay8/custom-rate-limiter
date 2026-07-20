"""Rate limit quota sharing between related clients.

Allows multiple sub-accounts to share a parent quota pool. Each sub-account
can have its own individual limit, but all sub-accounts also draw from a
shared pool.

Industry Usage:
    - AWS: Organization-level service quotas shared across accounts
    - Stripe: Connected accounts sharing platform limits
    - Google Cloud: Folder/Project quota inheritance
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from app.logging.structured import get_logger


@dataclass
class QuotaPool:
    """A shared quota pool that multiple clients can draw from.

    Attributes:
        pool_id: Unique identifier for the pool.
        total_limit: Total shared limit for the pool per window.
        window: Window size in seconds.
        members: Set of client IDs in this pool.
        used: Current usage across all members.
    """

    pool_id: str
    total_limit: int
    window: int
    members: set[str] = field(default_factory=set)
    used: int = 0
    last_reset: float = 0.0


class QuotaManager:
    """Manages shared quota pools for rate limiting.

    Supports hierarchical quota sharing where:
    1. Each client has an individual limit (per-client cap)
    2. All clients in a pool share a total pool limit
    3. A request is allowed only if BOTH individual AND pool limits allow

    Example:
        Pool "enterprise" with total_limit=1000:
            - client-team-a: individual limit 200
            - client-team-b: individual limit 300
            - client-team-c: individual limit 500
        Total pool usage cannot exceed 1000, regardless of individual limits.
    """

    def __init__(self) -> None:
        """Initialize quota manager."""
        self._lock = threading.Lock()
        self._pools: dict[str, QuotaPool] = {}
        self._client_to_pool: dict[str, str] = {}
        self._logger = get_logger()

    def create_pool(
        self,
        pool_id: str,
        total_limit: int,
        window: int,
        members: set[str] | None = None,
    ) -> QuotaPool:
        """Create a new shared quota pool.

        Args:
            pool_id: Unique identifier for the pool.
            total_limit: Total shared limit per window.
            window: Window size in seconds.
            members: Initial set of client IDs.

        Returns:
            The created QuotaPool.
        """
        with self._lock:
            pool = QuotaPool(
                pool_id=pool_id,
                total_limit=total_limit,
                window=window,
                members=members or set(),
            )
            self._pools[pool_id] = pool
            for member in pool.members:
                self._client_to_pool[member] = pool_id
            self._logger.info(f"Created quota pool '{pool_id}' with limit {total_limit}")
            return pool

    def add_member(self, pool_id: str, client_id: str) -> bool:
        """Add a client to a quota pool.

        Args:
            pool_id: Pool to add the client to.
            client_id: Client to add.

        Returns:
            True if added successfully.
        """
        with self._lock:
            pool = self._pools.get(pool_id)
            if pool is None:
                return False
            pool.members.add(client_id)
            self._client_to_pool[client_id] = pool_id
            return True

    def check_pool_quota(self, client_id: str, cost: int = 1) -> tuple[bool, int]:
        """Check if a client's shared pool has available quota.

        Args:
            client_id: The client making the request.
            cost: Number of units this request costs.

        Returns:
            Tuple of (allowed, pool_remaining).
            If client is not in any pool, returns (True, -1) indicating no pool constraint.
        """
        with self._lock:
            pool_id = self._client_to_pool.get(client_id)
            if pool_id is None:
                return True, -1  # No pool constraint

            pool = self._pools.get(pool_id)
            if pool is None:
                return True, -1

            import time

            now = time.time()
            # Reset pool if window has elapsed
            if now - pool.last_reset >= pool.window:
                pool.used = 0
                pool.last_reset = now

            remaining = pool.total_limit - pool.used
            if remaining >= cost:
                pool.used += cost
                return True, remaining - cost
            return False, 0

    def get_pool_for_client(self, client_id: str) -> QuotaPool | None:
        """Get the quota pool a client belongs to.

        Args:
            client_id: The client to look up.

        Returns:
            The QuotaPool or None.
        """
        pool_id = self._client_to_pool.get(client_id)
        if pool_id is None:
            return None
        return self._pools.get(pool_id)

    def get_pool_status(self, pool_id: str) -> dict[str, Any] | None:
        """Get status of a quota pool.

        Args:
            pool_id: Pool to get status for.

        Returns:
            Status dictionary or None if pool not found.
        """
        pool = self._pools.get(pool_id)
        if pool is None:
            return None
        return {
            "pool_id": pool.pool_id,
            "total_limit": pool.total_limit,
            "used": pool.used,
            "remaining": pool.total_limit - pool.used,
            "window": pool.window,
            "members": list(pool.members),
            "utilization_percent": round(pool.used / pool.total_limit * 100, 1) if pool.total_limit > 0 else 0,
        }

    def get_all_pools(self) -> dict[str, dict[str, Any]]:
        """Get status of all quota pools."""
        return {
            pool_id: self.get_pool_status(pool_id)
            for pool_id in self._pools
            if self.get_pool_status(pool_id) is not None
        }

    def reset_pool(self, pool_id: str) -> bool:
        """Reset a pool's usage counter.

        Args:
            pool_id: Pool to reset.

        Returns:
            True if pool was found and reset.
        """
        with self._lock:
            pool = self._pools.get(pool_id)
            if pool is None:
                return False
            pool.used = 0
            return True

    def reset_all(self) -> None:
        """Reset all pool usage counters."""
        with self._lock:
            for pool in self._pools.values():
                pool.used = 0
