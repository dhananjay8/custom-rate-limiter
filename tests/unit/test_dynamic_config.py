"""Tests for persistent dynamic configuration."""

from __future__ import annotations

import json
import os
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.config.settings import AlgorithmType, Settings, StorageBackend
from app.factory import create_app


@pytest.fixture
def dynamic_config_settings(tmp_path: pytest.TempPathFactory) -> Settings:
    """Settings with dynamic config enabled and a temp file."""
    config_path = tmp_path / "dynamic_config.json"  # type: ignore[operator]
    return Settings(
        app_env="testing",
        log_level="DEBUG",
        rate_limit_storage=StorageBackend.MEMORY,
        foo_algorithm=AlgorithmType.FIXED_WINDOW,
        bar_algorithm=AlgorithmType.SLIDING_WINDOW_LOG,
        client_basic_foo_limit=10,
        client_basic_foo_window=60,
        client_basic_bar_limit=20,
        client_basic_bar_window=60,
        client_premium_foo_limit=100,
        client_premium_foo_window=60,
        client_premium_bar_limit=250,
        client_premium_bar_window=60,
        adaptive_enabled=False,
        coalescing_enabled=False,
        circuit_breaker_enabled=False,
        dynamic_config_enabled=True,
        dynamic_config_path=str(config_path),
    )


@pytest.fixture
def dynamic_config_app(dynamic_config_settings: Settings) -> Flask:
    """Flask app with dynamic config enabled."""
    app = create_app(settings=dynamic_config_settings)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def dynamic_config_client(dynamic_config_app: Flask) -> FlaskClient:
    """Test client for dynamic config app."""
    return dynamic_config_app.test_client()


class TestDynamicConfig:
    """Tests for POST /admin/config."""

    def test_dynamic_config_disabled_returns_503(
        self, client: FlaskClient
    ) -> None:
        """When dynamic config is disabled, POST /admin/config returns 503."""
        response = client.post("/admin/config", json={"clients": {}})
        assert response.status_code == 503
        assert response.json == {"error": "dynamic configuration is not enabled"}

    def test_post_client_limit_update(
        self, dynamic_config_client: FlaskClient
    ) -> None:
        """POST /admin/config can lower a client limit, enforced immediately."""
        response = dynamic_config_client.post(
            "/admin/config",
            json={
                "clients": {
                    "client-basic": {
                        "foo": {"limit": 3, "window": 60}
                    }
                }
            },
        )
        assert response.status_code == 200

        for _ in range(3):
            response = dynamic_config_client.get(
                "/foo", headers={"Authorization": "Bearer client-basic"}
            )
            assert response.status_code == 200

        response = dynamic_config_client.get(
            "/foo", headers={"Authorization": "Bearer client-basic"}
        )
        assert response.status_code == 429

    def test_post_algorithm_update(
        self, dynamic_config_client: FlaskClient
    ) -> None:
        """POST /admin/config can switch endpoint algorithm at runtime."""
        response = dynamic_config_client.post(
            "/admin/config",
            json={"algorithms": {"foo": "token_bucket"}},
        )
        assert response.status_code == 200

        response = dynamic_config_client.get("/admin/config")
        assert response.status_code == 200
        assert response.json["algorithms"]["foo"] == "token_bucket"

    def test_post_weighted_config_update(
        self, dynamic_config_client: FlaskClient
    ) -> None:
        """POST /admin/config can update method weights at runtime."""
        response = dynamic_config_client.post(
            "/admin/config",
            json={
                "weights": {
                    "foo": {
                        "default_cost": 2,
                        "method_costs": {"GET": 2, "POST": 4},
                    }
                }
            },
        )
        assert response.status_code == 200

        response = dynamic_config_client.get("/admin/weights")
        data = response.json
        assert data["foo"]["method_costs"]["GET"] == 2
        assert data["foo"]["method_costs"]["POST"] == 4

    def test_invalid_config_returns_400(
        self, dynamic_config_client: FlaskClient
    ) -> None:
        """Invalid dynamic config returns 400 with an error message."""
        response = dynamic_config_client.post(
            "/admin/config",
            json={"clients": {"client-basic": {"foo": {"window": 60}}}},
        )
        assert response.status_code == 400
        assert "limit" in response.json["error"]

    def test_config_is_persisted(
        self, dynamic_config_client: FlaskClient, dynamic_config_settings: Settings
    ) -> None:
        """A successful update is written to the configured JSON file."""
        dynamic_config_client.post(
            "/admin/config",
            json={
                "clients": {
                    "client-basic": {
                        "foo": {"limit": 3, "window": 60}
                    }
                }
            },
        )

        with open(dynamic_config_settings.dynamic_config_path, encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["clients"]["client-basic"]["foo"]["limit"] == 3

    def test_persisted_config_is_reloaded(
        self, dynamic_config_settings: Settings
    ) -> None:
        """A new app instance loads previously persisted config."""
        with open(dynamic_config_settings.dynamic_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "clients": {
                        "client-basic": {
                            "foo": {"limit": 2, "window": 60}
                        }
                    }
                },
                f,
            )

        app = create_app(settings=dynamic_config_settings)
        app.config["TESTING"] = True
        client = app.test_client()

        for _ in range(2):
            response = client.get(
                "/foo", headers={"Authorization": "Bearer client-basic"}
            )
            assert response.status_code == 200

        response = client.get(
            "/foo", headers={"Authorization": "Bearer client-basic"}
        )
        assert response.status_code == 429
