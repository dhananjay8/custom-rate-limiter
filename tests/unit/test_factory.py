"""Tests for algorithm and repository factories."""

from __future__ import annotations

import pytest

from app.algorithms.factory import AlgorithmFactory
from app.algorithms.fixed_window import FixedWindowAlgorithm
from app.algorithms.gcra import GCRAAlgorithm
from app.algorithms.leaky_bucket import LeakyBucketAlgorithm
from app.algorithms.sliding_window_counter import SlidingWindowCounterAlgorithm
from app.algorithms.sliding_window_log import SlidingWindowLogAlgorithm
from app.algorithms.token_bucket import TokenBucketAlgorithm
from app.config.settings import AlgorithmType, Settings, StorageBackend
from app.repositories.factory import RepositoryFactory
from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SQLiteRepository


class TestAlgorithmFactory:
    """Tests for algorithm factory."""

    def test_create_fixed_window(self) -> None:
        """Factory creates FixedWindowAlgorithm."""
        algo = AlgorithmFactory.create(AlgorithmType.FIXED_WINDOW)
        assert isinstance(algo, FixedWindowAlgorithm)

    def test_create_sliding_window_log(self) -> None:
        """Factory creates SlidingWindowLogAlgorithm."""
        algo = AlgorithmFactory.create(AlgorithmType.SLIDING_WINDOW_LOG)
        assert isinstance(algo, SlidingWindowLogAlgorithm)

    def test_create_sliding_window_counter(self) -> None:
        """Factory creates SlidingWindowCounterAlgorithm."""
        algo = AlgorithmFactory.create(AlgorithmType.SLIDING_WINDOW_COUNTER)
        assert isinstance(algo, SlidingWindowCounterAlgorithm)

    def test_create_token_bucket(self) -> None:
        """Factory creates TokenBucketAlgorithm."""
        algo = AlgorithmFactory.create(AlgorithmType.TOKEN_BUCKET)
        assert isinstance(algo, TokenBucketAlgorithm)

    def test_create_leaky_bucket(self) -> None:
        """Factory creates LeakyBucketAlgorithm."""
        algo = AlgorithmFactory.create(AlgorithmType.LEAKY_BUCKET)
        assert isinstance(algo, LeakyBucketAlgorithm)

    def test_create_gcra(self) -> None:
        """Factory creates GCRAAlgorithm."""
        algo = AlgorithmFactory.create(AlgorithmType.GCRA)
        assert isinstance(algo, GCRAAlgorithm)

    def test_available_algorithms(self) -> None:
        """All algorithms are listed."""
        available = AlgorithmFactory.available_algorithms()
        assert "fixed_window" in available
        assert "sliding_window_log" in available
        assert "sliding_window_counter" in available
        assert "token_bucket" in available
        assert "leaky_bucket" in available
        assert "gcra" in available


class TestRepositoryFactory:
    """Tests for repository factory."""

    def test_create_memory_repository(self) -> None:
        """Factory creates MemoryRepository."""
        settings = Settings(rate_limit_storage=StorageBackend.MEMORY)
        repo = RepositoryFactory.create(settings)
        assert isinstance(repo, MemoryRepository)

    def test_create_sqlite_repository(self) -> None:
        """Factory creates SQLiteRepository."""
        settings = Settings(
            rate_limit_storage=StorageBackend.SQLITE,
            sqlite_db_path=":memory:",
        )
        repo = RepositoryFactory.create(settings)
        assert isinstance(repo, SQLiteRepository)
