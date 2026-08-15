"""Chaos and failover tests for storage backend outages.

These tests simulate Redis and SQLite failures and verify that the
circuit breaker fail-open strategy keeps the API responsive.
"""

from __future__ import annotations

import pytest
from _pytest.monkeypatch import MonkeyPatch
from flask.testing import FlaskClient

from app.config.settings import Settings, StorageBackend
from app.factory import create_app
from app.repositories.base import RateLimitRepository
from app.repositories.resilient_repository import ResilientRepository
from app.resilience.circuit_breaker import CircuitBreaker


class FailingRedisRepository(RateLimitRepository):
    """Simulates a Redis backend that is unreachable."""

    def increment_counter(self, key: str, ttl: int) -> int:
        raise ConnectionError("Redis connection refused")

    def get_counter(self, key: str) -> int:
        raise ConnectionError("Redis connection refused")

    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        raise ConnectionError("Redis connection refused")

    def get_request_count(self, key: str, window_start: float) -> int:
        raise ConnectionError("Redis connection refused")

    def remove_expired_entries(self, key: str, window_start: float) -> None:
        raise ConnectionError("Redis connection refused")

    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        raise ConnectionError("Redis connection refused")

    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        raise ConnectionError("Redis connection refused")

    def clear(self) -> None:
        pass

    def health_check(self) -> bool:
        return False


class FailingSQLiteRepository(RateLimitRepository):
    """Simulates a SQLite backend that is locked/corrupted."""

    def increment_counter(self, key: str, ttl: int) -> int:
        raise ConnectionError("SQLite database is locked")

    def get_counter(self, key: str) -> int:
        raise ConnectionError("SQLite database is locked")

    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        raise ConnectionError("SQLite database is locked")

    def get_request_count(self, key: str, window_start: float) -> int:
        raise ConnectionError("SQLite database is locked")

    def remove_expired_entries(self, key: str, window_start: float) -> None:
        raise ConnectionError("SQLite database is locked")

    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        raise ConnectionError("SQLite database is locked")

    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        raise ConnectionError("SQLite database is locked")

    def clear(self) -> None:
        pass

    def health_check(self) -> bool:
        return False


def _client_with_failing_repo(
    failing_repo: RateLimitRepository, monkeypatch: MonkeyPatch
) -> FlaskClient:
    """Create an app whose repository is a resilient wrapper around a failing backend."""

    def _create_resilient_repo(settings: Settings) -> ResilientRepository:
        return ResilientRepository(
            repository=failing_repo,
            circuit_breaker=CircuitBreaker(failure_threshold=2),
        )

    monkeypatch.setattr(
        "app.repositories.factory.RepositoryFactory.create", _create_resilient_repo
    )

    settings = Settings(
        app_env="testing",
        log_level="DEBUG",
        rate_limit_storage=StorageBackend.MEMORY,
        circuit_breaker_enabled=True,
        coalescing_enabled=False,
        adaptive_enabled=False,
    )
    app = create_app(settings=settings)
    app.config["TESTING"] = True
    return app.test_client()


class TestRedisOutage:
    """Failover tests that simulate a Redis outage."""

    def test_app_stays_available_when_redis_fails(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Circuit breaker opens and API remains available (fail-open)."""
        client = _client_with_failing_repo(FailingRedisRepository(), monkeypatch)

        for _ in range(5):
            response = client.get(
                "/foo", headers={"Authorization": "Bearer client-basic"}
            )
            assert response.status_code == 200

    def test_health_reports_degraded_during_redis_outage(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """/health returns 503 when storage is degraded."""
        client = _client_with_failing_repo(FailingRedisRepository(), monkeypatch)

        # Trigger failures to open the circuit
        for _ in range(3):
            client.get("/foo", headers={"Authorization": "Bearer client-basic"})

        response = client.get("/health")
        assert response.status_code == 503
        assert response.json["status"] == "degraded"


class TestSQLiteOutage:
    """Failover tests that simulate a SQLite outage."""

    def test_app_stays_available_when_sqlite_fails(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Circuit breaker opens and API remains available (fail-open)."""
        client = _client_with_failing_repo(FailingSQLiteRepository(), monkeypatch)

        for _ in range(5):
            response = client.get(
                "/foo", headers={"Authorization": "Bearer client-basic"}
            )
            assert response.status_code == 200

    def test_circuit_breaker_opens_during_sqlite_outage(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Circuit breaker transitions to open after repeated SQLite failures."""
        client = _client_with_failing_repo(FailingSQLiteRepository(), monkeypatch)

        for _ in range(3):
            client.get("/foo", headers={"Authorization": "Bearer client-basic"})

        response = client.get("/admin/circuit-breaker")
        data = response.json
        assert data["enabled"] is True
        assert data["state"] == "open"
