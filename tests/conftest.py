"""Shared test fixtures and configuration."""

from __future__ import annotations

import os
import tempfile
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.config.settings import AlgorithmType, Settings, StorageBackend
from app.factory import create_app
from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SQLiteRepository


@pytest.fixture
def memory_repository() -> MemoryRepository:
    """Create a fresh in-memory repository."""
    return MemoryRepository()


@pytest.fixture
def sqlite_repository() -> Generator[SQLiteRepository, None, None]:
    """Create a fresh SQLite repository with a temp database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    repo = SQLiteRepository(db_path=db_path)
    yield repo

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with memory storage."""
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
    )


@pytest.fixture
def test_settings_sqlite() -> Settings:
    """Create test settings with SQLite storage."""
    return Settings(
        app_env="testing",
        log_level="DEBUG",
        rate_limit_storage=StorageBackend.SQLITE,
        sqlite_db_path=":memory:",
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
    )


@pytest.fixture
def app(test_settings: Settings) -> Flask:
    """Create test Flask application."""
    application = create_app(settings=test_settings)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client."""
    return app.test_client()


@pytest.fixture
def basic_auth_header() -> dict[str, str]:
    """Authorization header for client-basic."""
    return {"Authorization": "Bearer client-basic"}


@pytest.fixture
def premium_auth_header() -> dict[str, str]:
    """Authorization header for client-premium."""
    return {"Authorization": "Bearer client-premium"}
