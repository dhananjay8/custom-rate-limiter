"""Tests for the resilient repository wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.repositories.memory_repository import MemoryRepository
from app.repositories.resilient_repository import ResilientRepository
from app.resilience.circuit_breaker import CircuitBreaker, CircuitState


class TestResilientRepository:
    """Tests for ResilientRepository with circuit breaker."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.inner_repo = MemoryRepository()
        self.cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
        self.repo = ResilientRepository(
            repository=self.inner_repo,
            circuit_breaker=self.cb,
        )

    def test_passes_through_when_healthy(self) -> None:
        """Operations pass through to inner repo normally."""
        count = self.repo.increment_counter("key1", ttl=60)
        assert count == 1
        assert self.repo.get_counter("key1") == 1

    def test_token_bucket_passthrough(self) -> None:
        """Token bucket operations work through wrapper."""
        self.repo.set_token_bucket("bucket1", 5.0, 1000.0)
        state = self.repo.get_token_bucket("bucket1")
        assert state == (5.0, 1000.0)

    def test_timestamp_passthrough(self) -> None:
        """Timestamp operations work through wrapper."""
        self.repo.add_request_timestamp("ts1", 1000.0)
        count = self.repo.get_request_count("ts1", 999.0)
        assert count == 1

    def test_circuit_open_returns_permissive_defaults(self) -> None:
        """When circuit is open, returns values that allow requests through."""
        # Trip the circuit
        failing_repo = MagicMock()
        failing_repo.increment_counter.side_effect = ConnectionError("Redis down")
        
        repo = ResilientRepository(
            repository=failing_repo,
            circuit_breaker=CircuitBreaker(failure_threshold=3),
        )

        # Trigger failures to trip the circuit
        for _ in range(3):
            repo.increment_counter("key", 60)

        # Now circuit is open - should return permissive default (0)
        result = repo.increment_counter("key", 60)
        assert result == 0

    def test_get_counter_returns_zero_on_failure(self) -> None:
        """Counter returns 0 when storage fails (permissive)."""
        failing_repo = MagicMock()
        failing_repo.get_counter.side_effect = ConnectionError("Redis down")
        
        repo = ResilientRepository(
            repository=failing_repo,
            circuit_breaker=CircuitBreaker(failure_threshold=1),
        )

        result = repo.get_counter("key")
        assert result == 0

    def test_health_check_reflects_circuit_state(self) -> None:
        """Health check returns False when circuit is open."""
        assert self.repo.health_check() is True

        # Trip the circuit (set both state and recent failure time)
        import time

        self.cb._state = CircuitState.OPEN
        self.cb._last_failure_time = time.time()
        assert self.repo.health_check() is False

    def test_clear_bypasses_circuit_breaker(self) -> None:
        """Clear operation goes directly to inner repo."""
        self.repo.increment_counter("key", 60)
        self.repo.clear()
        assert self.inner_repo.get_counter("key") == 0

    def test_inner_repository_accessible(self) -> None:
        """Can access the inner repository."""
        assert self.repo.inner_repository is self.inner_repo

    def test_circuit_breaker_accessible(self) -> None:
        """Can access the circuit breaker."""
        assert self.repo.circuit_breaker is self.cb
