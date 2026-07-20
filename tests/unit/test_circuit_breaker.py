"""Tests for the circuit breaker pattern."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState


class TestCircuitBreaker:
    """Tests for circuit breaker state transitions and behavior."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.cb = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=5.0,
            success_threshold=2,
        )

    def test_initial_state_closed(self) -> None:
        """Circuit starts in CLOSED state."""
        assert self.cb.state == CircuitState.CLOSED
        assert self.cb.is_closed is True

    def test_success_keeps_closed(self) -> None:
        """Successful operations keep the circuit closed."""
        result = self.cb.execute(lambda: 42)
        assert result == 42
        assert self.cb.state == CircuitState.CLOSED

    def test_failures_below_threshold(self) -> None:
        """Failures below threshold keep circuit closed."""
        for _ in range(2):
            with pytest.raises(ValueError):
                self.cb.execute(self._failing_operation)
        assert self.cb.state == CircuitState.CLOSED

    def test_failures_open_circuit(self) -> None:
        """Failures at threshold open the circuit."""
        for _ in range(3):
            with pytest.raises(ValueError):
                self.cb.execute(self._failing_operation)
        assert self.cb.state == CircuitState.OPEN

    def test_open_circuit_raises(self) -> None:
        """Open circuit raises CircuitBreakerOpen."""
        self._trip_circuit()
        with pytest.raises(CircuitBreakerOpen):
            self.cb.execute(lambda: 42)

    def test_half_open_after_timeout(self) -> None:
        """Circuit transitions to HALF_OPEN after recovery timeout."""
        self._trip_circuit()
        base_time = time.time()

        with patch("time.time", return_value=base_time + 6):
            assert self.cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        """Successful calls in HALF_OPEN close the circuit."""
        self._trip_circuit()
        base_time = time.time()

        with patch("time.time", return_value=base_time + 6):
            # Need success_threshold (2) successes
            self.cb.execute(lambda: 1)
            self.cb.execute(lambda: 2)
            assert self.cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        """Failure in HALF_OPEN reopens the circuit."""
        self._trip_circuit()
        base_time = time.time()

        with patch("time.time", return_value=base_time + 6):
            assert self.cb.state == CircuitState.HALF_OPEN
            with pytest.raises(ValueError):
                self.cb.execute(self._failing_operation)
            assert self.cb.state == CircuitState.OPEN

    def test_reset(self) -> None:
        """Manual reset closes the circuit."""
        self._trip_circuit()
        self.cb.reset()
        assert self.cb.state == CircuitState.CLOSED

    def test_get_status(self) -> None:
        """Status returns meaningful data."""
        status = self.cb.get_status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 3

    def _trip_circuit(self) -> None:
        """Helper to trip the circuit breaker."""
        for _ in range(3):
            with pytest.raises(ValueError):
                self.cb.execute(self._failing_operation)

    @staticmethod
    def _failing_operation() -> None:
        raise ValueError("simulated failure")
