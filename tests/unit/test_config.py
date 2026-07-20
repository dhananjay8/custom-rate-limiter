"""Unit tests for configuration management."""

from __future__ import annotations

import pytest

from app.config.settings import AlgorithmType, ClientEndpointConfig, Settings, StorageBackend


class TestSettings:
    """Tests for application settings."""

    def test_default_storage(self) -> None:
        """Default storage is memory."""
        settings = Settings()
        assert settings.rate_limit_storage == StorageBackend.MEMORY

    def test_default_algorithms(self) -> None:
        """Default algorithms are correctly set."""
        settings = Settings()
        assert settings.foo_algorithm == AlgorithmType.FIXED_WINDOW
        assert settings.bar_algorithm == AlgorithmType.SLIDING_WINDOW_LOG

    def test_get_clients(self) -> None:
        """Clients are correctly constructed from settings."""
        settings = Settings()
        clients = settings.get_clients()

        assert "client-basic" in clients
        assert "client-premium" in clients

        basic = clients["client-basic"]
        assert basic.endpoints["foo"].limit == 10
        assert basic.endpoints["foo"].window == 60
        assert basic.endpoints["bar"].limit == 20
        assert basic.endpoints["bar"].window == 60

        premium = clients["client-premium"]
        assert premium.endpoints["foo"].limit == 100
        assert premium.endpoints["foo"].window == 60
        assert premium.endpoints["bar"].limit == 250
        assert premium.endpoints["bar"].window == 60

    def test_get_algorithm_for_endpoint(self) -> None:
        """Algorithm mapping works correctly."""
        settings = Settings()
        assert settings.get_algorithm_for_endpoint("foo") == AlgorithmType.FIXED_WINDOW
        assert settings.get_algorithm_for_endpoint("bar") == AlgorithmType.SLIDING_WINDOW_LOG

    def test_get_algorithm_unknown_endpoint(self) -> None:
        """Unknown endpoint raises ValueError."""
        settings = Settings()
        with pytest.raises(ValueError, match="Unknown endpoint"):
            settings.get_algorithm_for_endpoint("unknown")

    def test_get_endpoint_algorithms(self) -> None:
        """All endpoint algorithms are returned."""
        settings = Settings()
        algorithms = settings.get_endpoint_algorithms()
        assert algorithms == {
            "foo": AlgorithmType.FIXED_WINDOW,
            "bar": AlgorithmType.SLIDING_WINDOW_LOG,
        }

    def test_custom_settings(self) -> None:
        """Settings can be customized."""
        settings = Settings(
            rate_limit_storage=StorageBackend.SQLITE,
            foo_algorithm=AlgorithmType.TOKEN_BUCKET,
            client_basic_foo_limit=50,
        )
        assert settings.rate_limit_storage == StorageBackend.SQLITE
        assert settings.foo_algorithm == AlgorithmType.TOKEN_BUCKET
        assert settings.client_basic_foo_limit == 50


class TestClientEndpointConfig:
    """Tests for client endpoint configuration."""

    def test_valid_config(self) -> None:
        """Valid configuration is accepted."""
        config = ClientEndpointConfig(limit=10, window=60)
        assert config.limit == 10
        assert config.window == 60

    def test_invalid_limit(self) -> None:
        """Limit must be positive."""
        with pytest.raises(Exception):
            ClientEndpointConfig(limit=0, window=60)

    def test_invalid_window(self) -> None:
        """Window must be positive."""
        with pytest.raises(Exception):
            ClientEndpointConfig(limit=10, window=0)
