"""Application configuration management using Pydantic Settings."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class StorageBackend(str, Enum):
    """Supported storage backends."""

    MEMORY = "memory"
    SQLITE = "sqlite"


class AlgorithmType(str, Enum):
    """Supported rate limiting algorithms."""

    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"


class ClientEndpointConfig(BaseModel):
    """Rate limit configuration for a specific client-endpoint pair."""

    limit: int = Field(gt=0, description="Maximum requests allowed in the window")
    window: int = Field(gt=0, description="Window size in seconds")


class ClientConfig(BaseModel):
    """Rate limit configuration for a client across all endpoints."""

    endpoints: dict[str, ClientEndpointConfig] = Field(
        default_factory=dict, description="Endpoint-specific rate limit configs"
    )


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_env: str = Field(default="development", description="Application environment")
    log_level: str = Field(default="INFO", description="Logging level")

    # Storage
    rate_limit_storage: StorageBackend = Field(
        default=StorageBackend.MEMORY, description="Storage backend to use"
    )
    sqlite_db_path: str = Field(
        default="rate_limiter.db", description="Path to SQLite database"
    )

    # Algorithm mapping per endpoint
    foo_algorithm: AlgorithmType = Field(
        default=AlgorithmType.FIXED_WINDOW, description="Algorithm for /foo endpoint"
    )
    bar_algorithm: AlgorithmType = Field(
        default=AlgorithmType.SLIDING_WINDOW_LOG, description="Algorithm for /bar endpoint"
    )

    # Client: client-basic
    client_basic_foo_limit: int = Field(default=10, gt=0)
    client_basic_foo_window: int = Field(default=60, gt=0)
    client_basic_bar_limit: int = Field(default=20, gt=0)
    client_basic_bar_window: int = Field(default=60, gt=0)

    # Client: client-premium
    client_premium_foo_limit: int = Field(default=100, gt=0)
    client_premium_foo_window: int = Field(default=60, gt=0)
    client_premium_bar_limit: int = Field(default=250, gt=0)
    client_premium_bar_window: int = Field(default=60, gt=0)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_algorithm_for_endpoint(self, endpoint: str) -> AlgorithmType:
        """Get the configured algorithm for an endpoint."""
        algorithm_map: dict[str, AlgorithmType] = {
            "foo": self.foo_algorithm,
            "bar": self.bar_algorithm,
        }
        if endpoint not in algorithm_map:
            raise ValueError(f"Unknown endpoint: {endpoint}")
        return algorithm_map[endpoint]

    def get_clients(self) -> dict[str, ClientConfig]:
        """Build client configurations from environment variables."""
        return {
            "client-basic": ClientConfig(
                endpoints={
                    "foo": ClientEndpointConfig(
                        limit=self.client_basic_foo_limit,
                        window=self.client_basic_foo_window,
                    ),
                    "bar": ClientEndpointConfig(
                        limit=self.client_basic_bar_limit,
                        window=self.client_basic_bar_window,
                    ),
                }
            ),
            "client-premium": ClientConfig(
                endpoints={
                    "foo": ClientEndpointConfig(
                        limit=self.client_premium_foo_limit,
                        window=self.client_premium_foo_window,
                    ),
                    "bar": ClientEndpointConfig(
                        limit=self.client_premium_bar_limit,
                        window=self.client_premium_bar_window,
                    ),
                }
            ),
        }

    def get_endpoint_algorithms(self) -> dict[str, AlgorithmType]:
        """Get algorithm mapping for all endpoints."""
        return {
            "foo": self.foo_algorithm,
            "bar": self.bar_algorithm,
        }


def get_settings() -> Settings:
    """Factory function to create settings instance."""
    return Settings()
