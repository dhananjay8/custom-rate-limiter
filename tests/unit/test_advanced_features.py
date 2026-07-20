"""Tests for advanced features: adaptive, weighted, coalescing, quota sharing."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.algorithms.base import RateLimitResult
from app.services.adaptive import AdaptiveRateLimiter, LoadLevel
from app.services.coalescing import RequestCoalescer
from app.services.quota_sharing import QuotaManager
from app.services.weighted import WeightedRateLimiter


class TestAdaptiveRateLimiter:
    """Tests for adaptive rate limiting."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.adaptive = AdaptiveRateLimiter(enabled=True, sample_interval=0.0)

    def test_disabled_returns_multiplier_1(self) -> None:
        """Disabled adaptive limiter returns multiplier of 1.0."""
        disabled = AdaptiveRateLimiter(enabled=False)
        assert disabled.current_multiplier == 1.0
        assert disabled.get_effective_limit(100) == 100

    def test_effective_limit_calculation(self) -> None:
        """Effective limit is base * multiplier."""
        # Use a long sample interval so _maybe_update_metrics doesn't recalculate
        adaptive = AdaptiveRateLimiter(enabled=True, sample_interval=9999.0)
        adaptive._current_multiplier = 0.7
        adaptive._last_sample_time = time.time()
        assert adaptive.get_effective_limit(100) == 70

    def test_effective_limit_minimum_one(self) -> None:
        """Effective limit is at least 1."""
        self.adaptive._current_multiplier = 0.01
        assert self.adaptive.get_effective_limit(1) == 1

    def test_record_request_metrics(self) -> None:
        """Recording requests updates response time tracking."""
        self.adaptive.record_request_start()
        self.adaptive.record_request_end(50.0)
        assert len(self.adaptive._response_times) == 1

    def test_response_time_buffer_limited(self) -> None:
        """Response time buffer is capped at 100 samples."""
        for i in range(150):
            self.adaptive.record_request_end(float(i))
        assert len(self.adaptive._response_times) == 100

    def test_get_status(self) -> None:
        """Status returns complete information."""
        status = self.adaptive.get_status()
        assert "enabled" in status
        assert "current_load" in status
        assert "current_multiplier" in status
        assert "metrics" in status


class TestWeightedRateLimiter:
    """Tests for weighted rate limiting."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.weighted = WeightedRateLimiter()
        self.weighted.configure_endpoint("foo", default_cost=1, method_costs={
            "GET": 1,
            "POST": 5,
            "DELETE": 10,
        })

    def test_get_cost_known_method(self) -> None:
        """Returns configured cost for known methods."""
        assert self.weighted.get_cost("foo", "GET") == 1
        assert self.weighted.get_cost("foo", "POST") == 5
        assert self.weighted.get_cost("foo", "DELETE") == 10

    def test_get_cost_default(self) -> None:
        """Returns default cost for unknown methods."""
        assert self.weighted.get_cost("foo", "PATCH") == 1

    def test_get_cost_unknown_endpoint(self) -> None:
        """Returns 1 for unconfigured endpoints."""
        assert self.weighted.get_cost("unknown", "GET") == 1

    def test_method_stored_as_configured(self) -> None:
        """Method lookup uses uppercase conversion in get_cost."""
        self.weighted.configure_endpoint("bar", method_costs={"GET": 2})
        assert self.weighted.get_cost("bar", "GET") == 2

    def test_get_config(self) -> None:
        """Config returns all endpoint weights."""
        config = self.weighted.get_config()
        assert "foo" in config
        assert config["foo"]["method_costs"]["POST"] == 5


class TestRequestCoalescer:
    """Tests for request coalescing."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.coalescer = RequestCoalescer(window_ms=50.0, max_coalesce=5, enabled=True)

    def test_disabled_returns_none(self) -> None:
        """Disabled coalescer always returns None."""
        disabled = RequestCoalescer(enabled=False)
        disabled.cache_result("c1", "foo", self._make_result())
        assert disabled.get_cached("c1", "foo") is None

    def test_cache_miss(self) -> None:
        """Returns None for uncached key."""
        assert self.coalescer.get_cached("c1", "foo") is None

    def test_cache_hit(self) -> None:
        """Returns cached result within window."""
        result = self._make_result()
        self.coalescer.cache_result("c1", "foo", result)
        cached = self.coalescer.get_cached("c1", "foo")
        assert cached is not None
        assert cached.allowed is True

    def test_cache_expiry(self) -> None:
        """Expired cache returns None."""
        result = self._make_result()
        self.coalescer.cache_result("c1", "foo", result)

        with patch("time.time", return_value=time.time() + 1):
            cached = self.coalescer.get_cached("c1", "foo")
            assert cached is None

    def test_max_coalesce_limit(self) -> None:
        """Cache evicts after max_coalesce hits."""
        result = self._make_result()
        self.coalescer.cache_result("c1", "foo", result)

        for _ in range(5):
            self.coalescer.get_cached("c1", "foo")

        # 6th should miss (saturated)
        cached = self.coalescer.get_cached("c1", "foo")
        assert cached is None

    def test_get_stats(self) -> None:
        """Stats reports hits and misses."""
        self.coalescer.get_cached("c1", "foo")  # miss
        result = self._make_result()
        self.coalescer.cache_result("c1", "foo", result)
        self.coalescer.get_cached("c1", "foo")  # hit

        stats = self.coalescer.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_clear(self) -> None:
        """Clear removes all cached entries."""
        self.coalescer.cache_result("c1", "foo", self._make_result())
        self.coalescer.clear()
        assert self.coalescer.get_cached("c1", "foo") is None

    @staticmethod
    def _make_result() -> RateLimitResult:
        return RateLimitResult(
            allowed=True, limit=10, remaining=9, reset_at=time.time() + 60, current_count=1
        )


class TestQuotaManager:
    """Tests for shared quota pool management."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.manager = QuotaManager()
        self.manager.create_pool(
            pool_id="team",
            total_limit=100,
            window=60,
            members={"client-a", "client-b"},
        )

    def test_create_pool(self) -> None:
        """Pool is created with correct settings."""
        status = self.manager.get_pool_status("team")
        assert status is not None
        assert status["total_limit"] == 100
        assert status["used"] == 0
        assert set(status["members"]) == {"client-a", "client-b"}

    def test_check_pool_quota_allows(self) -> None:
        """Quota check allows when pool has capacity."""
        allowed, remaining = self.manager.check_pool_quota("client-a", cost=1)
        assert allowed is True
        assert remaining == 99

    def test_check_pool_quota_exhausted(self) -> None:
        """Quota check rejects when pool is exhausted."""
        for _ in range(100):
            self.manager.check_pool_quota("client-a", cost=1)

        allowed, remaining = self.manager.check_pool_quota("client-b", cost=1)
        assert allowed is False
        assert remaining == 0

    def test_shared_consumption(self) -> None:
        """Multiple clients consume from the same pool."""
        for _ in range(50):
            self.manager.check_pool_quota("client-a", cost=1)
        for _ in range(50):
            self.manager.check_pool_quota("client-b", cost=1)

        # Pool should be exhausted
        allowed, _ = self.manager.check_pool_quota("client-a", cost=1)
        assert allowed is False

    def test_non_pool_client_allowed(self) -> None:
        """Client not in any pool gets no pool constraint."""
        allowed, remaining = self.manager.check_pool_quota("client-x", cost=1)
        assert allowed is True
        assert remaining == -1  # No pool constraint

    def test_add_member(self) -> None:
        """Members can be added to existing pools."""
        result = self.manager.add_member("team", "client-c")
        assert result is True
        pool = self.manager.get_pool_for_client("client-c")
        assert pool is not None
        assert pool.pool_id == "team"

    def test_weighted_cost(self) -> None:
        """Pool correctly handles weighted costs."""
        allowed, remaining = self.manager.check_pool_quota("client-a", cost=10)
        assert allowed is True
        assert remaining == 90

    def test_reset_pool(self) -> None:
        """Pool usage resets correctly."""
        for _ in range(50):
            self.manager.check_pool_quota("client-a", cost=1)
        self.manager.reset_pool("team")
        status = self.manager.get_pool_status("team")
        assert status["used"] == 0

    def test_reset_all(self) -> None:
        """All pools reset correctly."""
        self.manager.check_pool_quota("client-a", cost=50)
        self.manager.reset_all()
        status = self.manager.get_pool_status("team")
        assert status["used"] == 0

    def test_get_all_pools(self) -> None:
        """Returns all pool statuses."""
        pools = self.manager.get_all_pools()
        assert "team" in pools
