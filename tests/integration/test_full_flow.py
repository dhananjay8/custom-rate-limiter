"""Integration tests for full request flow."""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.config.settings import AlgorithmType, Settings, StorageBackend
from app.factory import create_app


class TestFullFlowMemory:
    """Integration tests with memory storage backend."""

    @pytest.fixture
    def app(self) -> Flask:
        """Create app with memory storage."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.MEMORY,
            foo_algorithm=AlgorithmType.FIXED_WINDOW,
            bar_algorithm=AlgorithmType.SLIDING_WINDOW_LOG,
            client_basic_foo_limit=5,
            client_basic_foo_window=60,
            client_basic_bar_limit=10,
            client_basic_bar_window=60,
            client_premium_foo_limit=50,
            client_premium_foo_window=60,
            client_premium_bar_limit=100,
            client_premium_bar_window=60,
            adaptive_enabled=False,
            coalescing_enabled=False,
            circuit_breaker_enabled=False,
        )
        application = create_app(settings=settings)
        application.config["TESTING"] = True
        return application

    @pytest.fixture
    def client(self, app: Flask) -> FlaskClient:
        return app.test_client()

    def test_full_lifecycle(self, client: FlaskClient) -> None:
        """Test complete request lifecycle: auth -> rate limit -> response."""
        # 1. Unauthenticated request
        response = client.get("/foo")
        assert response.status_code == 401

        # 2. Unknown client
        response = client.get("/foo", headers={"Authorization": "Bearer unknown"})
        assert response.status_code == 403

        # 3. Successful requests
        for i in range(5):
            response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
            assert response.status_code == 200
            assert response.json == {"success": True}

        # 4. Rate limited
        response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 429
        assert response.json == {"error": "rate limit exceeded"}

        # 5. Different endpoint still works
        response = client.get("/bar", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 200

        # 6. Different client still works on same endpoint
        response = client.get("/foo", headers={"Authorization": "Bearer client-premium"})
        assert response.status_code == 200

    def test_metrics_tracking(self, client: FlaskClient) -> None:
        """Metrics are tracked correctly through full flow."""
        # Make some requests
        for _ in range(3):
            client.get("/foo", headers={"Authorization": "Bearer client-basic"})

        for _ in range(2):
            client.get("/bar", headers={"Authorization": "Bearer client-premium"})

        # Check metrics
        response = client.get("/metrics")
        data = response.json
        assert data["total_requests"] == 5
        assert data["allowed_requests"] == 5
        assert data["per_client"]["client-basic"]["total"] == 3
        assert data["per_client"]["client-premium"]["total"] == 2
        assert data["per_endpoint"]["foo"]["total"] == 3
        assert data["per_endpoint"]["bar"]["total"] == 2

    def test_reset_restores_rate_limits(self, client: FlaskClient) -> None:
        """Admin reset restores rate limits."""
        # Exhaust limit
        for _ in range(5):
            client.get("/foo", headers={"Authorization": "Bearer client-basic"})

        response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 429

        # Reset
        client.post("/admin/reset")

        # Should work again
        response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 200


class TestFullFlowSQLite:
    """Integration tests with SQLite storage backend."""

    @pytest.fixture
    def app(self) -> Flask:
        """Create app with SQLite storage (in-memory for tests)."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.SQLITE,
            sqlite_db_path=":memory:",
            foo_algorithm=AlgorithmType.FIXED_WINDOW,
            bar_algorithm=AlgorithmType.SLIDING_WINDOW_LOG,
            client_basic_foo_limit=5,
            client_basic_foo_window=60,
            client_basic_bar_limit=10,
            client_basic_bar_window=60,
            client_premium_foo_limit=50,
            client_premium_foo_window=60,
            client_premium_bar_limit=100,
            client_premium_bar_window=60,
            adaptive_enabled=False,
            coalescing_enabled=False,
            circuit_breaker_enabled=False,
        )
        application = create_app(settings=settings)
        application.config["TESTING"] = True
        return application

    @pytest.fixture
    def client(self, app: Flask) -> FlaskClient:
        return app.test_client()

    def test_full_lifecycle_sqlite(self, client: FlaskClient) -> None:
        """Test complete lifecycle with SQLite storage."""
        # Success
        for i in range(5):
            response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
            assert response.status_code == 200

        # Rate limited
        response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 429

    def test_bar_sliding_window_sqlite(self, client: FlaskClient) -> None:
        """Sliding window log works with SQLite."""
        for i in range(10):
            response = client.get("/bar", headers={"Authorization": "Bearer client-basic"})
            assert response.status_code == 200

        response = client.get("/bar", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 429

    def test_health_check_sqlite(self, client: FlaskClient) -> None:
        """Health check reports SQLite as healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json["storage"]["backend"] == "sqlite"
        assert response.json["storage"]["healthy"] is True


class TestAlgorithmSwitching:
    """Tests for switching algorithms via configuration."""

    def test_token_bucket_for_foo(self) -> None:
        """Token bucket can be used for /foo via config."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.MEMORY,
            foo_algorithm=AlgorithmType.TOKEN_BUCKET,
            bar_algorithm=AlgorithmType.SLIDING_WINDOW_LOG,
            client_basic_foo_limit=5,
            client_basic_foo_window=60,
            client_basic_bar_limit=10,
            client_basic_bar_window=60,
            client_premium_foo_limit=50,
            client_premium_foo_window=60,
            client_premium_bar_limit=100,
            client_premium_bar_window=60,
            adaptive_enabled=False,
            coalescing_enabled=False,
            circuit_breaker_enabled=False,
        )
        app = create_app(settings=settings)
        app.config["TESTING"] = True
        client = app.test_client()

        # Should work with token bucket
        for _ in range(5):
            response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
            assert response.status_code == 200

        response = client.get("/foo", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 429

    def test_sliding_window_counter_for_bar(self) -> None:
        """Sliding window counter can be used for /bar."""
        settings = Settings(
            app_env="testing",
            rate_limit_storage=StorageBackend.MEMORY,
            foo_algorithm=AlgorithmType.FIXED_WINDOW,
            bar_algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER,
            client_basic_foo_limit=5,
            client_basic_foo_window=60,
            client_basic_bar_limit=10,
            client_basic_bar_window=60,
            client_premium_foo_limit=50,
            client_premium_foo_window=60,
            client_premium_bar_limit=100,
            client_premium_bar_window=60,
            adaptive_enabled=False,
            coalescing_enabled=False,
            circuit_breaker_enabled=False,
        )
        app = create_app(settings=settings)
        app.config["TESTING"] = True
        client = app.test_client()

        # Should work with sliding window counter
        response = client.get("/bar", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 200
