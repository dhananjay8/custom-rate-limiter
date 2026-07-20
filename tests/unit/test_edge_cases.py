"""Edge case and boundary condition tests."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from app.algorithms.fixed_window import FixedWindowAlgorithm
from app.algorithms.sliding_window_log import SlidingWindowLogAlgorithm
from app.algorithms.token_bucket import TokenBucketAlgorithm
from app.config.settings import AlgorithmType, Settings, StorageBackend
from app.factory import create_app
from app.repositories.memory_repository import MemoryRepository


class TestBoundaryConditions:
    """Tests for boundary conditions in rate limiting."""

    def test_exactly_at_limit(self) -> None:
        """Request exactly at the limit boundary."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        # Make exactly limit-1 requests
        for _ in range(9):
            algo.allow_request(repo, "client-1", "foo", limit=10, window=60)

        # This is the 10th (exactly at limit)
        result = algo.allow_request(repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is True
        assert result.remaining == 0

        # This is the 11th (over limit)
        result = algo.allow_request(repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is False

    def test_high_request_volume(self) -> None:
        """High volume of requests beyond the limit."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        allowed = 0
        rejected = 0
        for _ in range(1000):
            result = algo.allow_request(repo, "client-1", "foo", limit=10, window=60)
            if result.allowed:
                allowed += 1
            else:
                rejected += 1

        assert allowed == 10
        assert rejected == 990

    def test_very_small_window(self) -> None:
        """Very small window (1 second) works correctly."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        result = algo.allow_request(repo, "client-1", "foo", limit=5, window=1)
        assert result.allowed is True

    def test_very_large_limit(self) -> None:
        """Very large limit works correctly."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        for _ in range(1000):
            result = algo.allow_request(repo, "client-1", "foo", limit=100000, window=60)
            assert result.allowed is True

    def test_multiple_endpoints_isolation(self) -> None:
        """Rate limits are completely isolated per endpoint."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        # Exhaust foo
        for _ in range(5):
            algo.allow_request(repo, "client-1", "foo", limit=5, window=60)

        # Bar should be unaffected
        result = algo.allow_request(repo, "client-1", "bar", limit=5, window=60)
        assert result.allowed is True

    def test_rapid_window_transitions(self) -> None:
        """Rapid transitions between windows."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        # At end of window
        with patch("time.time", return_value=59.9):
            for _ in range(5):
                algo.allow_request(repo, "client-1", "foo", limit=5, window=60)
            result = algo.allow_request(repo, "client-1", "foo", limit=5, window=60)
            assert result.allowed is False

        # Just past window boundary
        with patch("time.time", return_value=60.0):
            result = algo.allow_request(repo, "client-1", "foo", limit=5, window=60)
            assert result.allowed is True


class TestSlidingWindowEdgeCases:
    """Edge cases specific to sliding window algorithm."""

    def test_requests_at_exact_window_boundary(self) -> None:
        """Requests at exact window boundary are handled correctly."""
        repo = MemoryRepository()
        algo = SlidingWindowLogAlgorithm()

        # Add request at exactly the window start
        with patch("time.time", return_value=1000.0):
            algo.allow_request(repo, "client-1", "bar", limit=5, window=60)

        # Check at exactly 60 seconds later
        with patch("time.time", return_value=1060.0):
            # The request at 1000.0 should be expired (window_start = 1060 - 60 = 1000)
            # 1000.0 >= 1000.0, so it's still in window
            result = algo.allow_request(repo, "client-1", "bar", limit=5, window=60)
            assert result.allowed is True

    def test_many_expired_entries_cleaned(self) -> None:
        """Many expired entries are cleaned up."""
        repo = MemoryRepository()
        algo = SlidingWindowLogAlgorithm()

        # Add 100 requests at time 1000
        with patch("time.time", return_value=1000.0):
            for _ in range(100):
                repo.add_request_timestamp("client-1:bar", 1000.0)

        # At time 1061, all should be expired
        with patch("time.time", return_value=1061.0):
            result = algo.allow_request(repo, "client-1", "bar", limit=5, window=60)
            assert result.allowed is True


class TestTokenBucketEdgeCases:
    """Edge cases specific to token bucket algorithm."""

    def test_full_refill_after_long_idle(self) -> None:
        """Bucket fully refills after long idle period."""
        repo = MemoryRepository()
        algo = TokenBucketAlgorithm()

        # Consume all tokens
        with patch("time.time", return_value=1000.0):
            for _ in range(10):
                algo.allow_request(repo, "client-1", "foo", limit=10, window=60)

        # Wait for full refill
        with patch("time.time", return_value=1100.0):
            result = algo.allow_request(repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True
            # Should have nearly full bucket
            assert result.remaining >= 8

    def test_zero_tokens_precise_refill(self) -> None:
        """Token bucket with precise refill timing."""
        repo = MemoryRepository()
        algo = TokenBucketAlgorithm()

        # Consume all tokens (10 tokens, 10/60 per second)
        with patch("time.time", return_value=1000.0):
            for _ in range(10):
                algo.allow_request(repo, "client-1", "foo", limit=10, window=60)

            # No tokens left
            result = algo.allow_request(repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is False

        # Wait just enough for 1 token (6 seconds at 10/60 = 1 token)
        with patch("time.time", return_value=1006.0):
            result = algo.allow_request(repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True


class TestStorageSwitching:
    """Tests for switching between storage backends."""

    def test_memory_to_sqlite_consistency(self) -> None:
        """Both storage backends produce consistent results."""
        from app.repositories.sqlite_repository import SQLiteRepository

        mem_repo = MemoryRepository()
        sqlite_repo = SQLiteRepository(db_path=":memory:")
        algo = FixedWindowAlgorithm()

        # Same sequence of requests on both
        mem_results = []
        sqlite_results = []

        for _ in range(15):
            mem_result = algo.allow_request(mem_repo, "client-1", "foo", limit=10, window=60)
            sqlite_result = algo.allow_request(sqlite_repo, "client-1", "foo", limit=10, window=60)
            mem_results.append(mem_result.allowed)
            sqlite_results.append(sqlite_result.allowed)

        assert mem_results == sqlite_results


class TestMultipleClientsSimultaneous:
    """Tests for multiple clients making requests simultaneously."""

    def test_clients_do_not_interfere(self) -> None:
        """Multiple clients making requests don't affect each other."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        # Client 1 hits limit
        for _ in range(10):
            algo.allow_request(repo, "client-basic", "foo", limit=10, window=60)

        # Client 2 should be unaffected
        for _ in range(10):
            result = algo.allow_request(repo, "client-premium", "foo", limit=100, window=60)
            assert result.allowed is True

    def test_same_client_different_endpoints(self) -> None:
        """Same client, different endpoints have independent limits."""
        repo = MemoryRepository()
        algo = FixedWindowAlgorithm()

        # Hit foo limit
        for _ in range(10):
            algo.allow_request(repo, "client-basic", "foo", limit=10, window=60)

        result = algo.allow_request(repo, "client-basic", "foo", limit=10, window=60)
        assert result.allowed is False

        # Bar is still available
        result = algo.allow_request(repo, "client-basic", "bar", limit=20, window=60)
        assert result.allowed is True


class TestAPIEdgeCases:
    """Edge case tests at the API level."""

    def test_empty_bearer_token(self) -> None:
        """Empty Bearer token."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.MEMORY,
        )
        app = create_app(settings=settings)
        client = app.test_client()

        response = client.get("/foo", headers={"Authorization": "Bearer "})
        assert response.status_code in (401, 403)

    def test_whitespace_in_token(self) -> None:
        """Token with extra whitespace."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.MEMORY,
        )
        app = create_app(settings=settings)
        client = app.test_client()

        response = client.get("/foo", headers={"Authorization": "Bearer  client-basic"})
        # Should handle gracefully (either accept trimmed or reject)
        assert response.status_code in (200, 401, 403)

    def test_very_long_token(self) -> None:
        """Very long token string."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.MEMORY,
        )
        app = create_app(settings=settings)
        client = app.test_client()

        long_token = "x" * 10000
        response = client.get("/foo", headers={"Authorization": f"Bearer {long_token}"})
        assert response.status_code == 403
