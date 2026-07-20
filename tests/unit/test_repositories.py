"""Unit tests for repository implementations."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SQLiteRepository


class TestMemoryRepository:
    """Tests for in-memory repository."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.repo = MemoryRepository()

    # --- Counter tests ---

    def test_increment_counter_new_key(self) -> None:
        """New counter starts at 1."""
        result = self.repo.increment_counter("test:key", ttl=60)
        assert result == 1

    def test_increment_counter_existing(self) -> None:
        """Counter increments correctly."""
        self.repo.increment_counter("test:key", ttl=60)
        result = self.repo.increment_counter("test:key", ttl=60)
        assert result == 2

    def test_increment_counter_multiple(self) -> None:
        """Counter increments sequentially."""
        for i in range(5):
            result = self.repo.increment_counter("test:key", ttl=60)
            assert result == i + 1

    def test_get_counter_existing(self) -> None:
        """Get returns current counter value."""
        self.repo.increment_counter("test:key", ttl=60)
        self.repo.increment_counter("test:key", ttl=60)
        assert self.repo.get_counter("test:key") == 2

    def test_get_counter_missing(self) -> None:
        """Get returns 0 for non-existent key."""
        assert self.repo.get_counter("nonexistent") == 0

    def test_counter_expiry(self) -> None:
        """Counter expires after TTL."""
        with patch("time.time", return_value=1000.0):
            self.repo.increment_counter("test:key", ttl=60)

        with patch("time.time", return_value=1061.0):
            assert self.repo.get_counter("test:key") == 0

    def test_counter_not_expired(self) -> None:
        """Counter persists within TTL."""
        with patch("time.time", return_value=1000.0):
            self.repo.increment_counter("test:key", ttl=60)

        with patch("time.time", return_value=1059.0):
            assert self.repo.get_counter("test:key") == 1

    def test_counter_expired_resets(self) -> None:
        """Expired counter resets to 1 on next increment."""
        with patch("time.time", return_value=1000.0):
            self.repo.increment_counter("test:key", ttl=60)
            self.repo.increment_counter("test:key", ttl=60)

        with patch("time.time", return_value=1061.0):
            result = self.repo.increment_counter("test:key", ttl=60)
            assert result == 1

    # --- Timestamp log tests ---

    def test_add_request_timestamp(self) -> None:
        """Timestamp is stored correctly."""
        self.repo.add_request_timestamp("log:key", 1000.0)
        count = self.repo.get_request_count("log:key", 999.0)
        assert count == 1

    def test_get_request_count_within_window(self) -> None:
        """Count returns only timestamps within window."""
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.add_request_timestamp("log:key", 1010.0)
        self.repo.add_request_timestamp("log:key", 1020.0)

        # Window from 1005 should include 2 requests
        count = self.repo.get_request_count("log:key", 1005.0)
        assert count == 2

    def test_get_request_count_empty(self) -> None:
        """Count returns 0 for empty log."""
        count = self.repo.get_request_count("empty:key", 0.0)
        assert count == 0

    def test_remove_expired_entries(self) -> None:
        """Expired entries are removed."""
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.add_request_timestamp("log:key", 1010.0)
        self.repo.add_request_timestamp("log:key", 1020.0)

        self.repo.remove_expired_entries("log:key", 1015.0)
        count = self.repo.get_request_count("log:key", 0.0)
        assert count == 1  # Only 1020.0 remains

    # --- Token bucket tests ---

    def test_get_token_bucket_missing(self) -> None:
        """Missing bucket returns None."""
        result = self.repo.get_token_bucket("bucket:key")
        assert result is None

    def test_set_and_get_token_bucket(self) -> None:
        """Token bucket state is stored and retrieved."""
        self.repo.set_token_bucket("bucket:key", 5.0, 1000.0)
        result = self.repo.get_token_bucket("bucket:key")
        assert result == (5.0, 1000.0)

    def test_update_token_bucket(self) -> None:
        """Token bucket state can be updated."""
        self.repo.set_token_bucket("bucket:key", 5.0, 1000.0)
        self.repo.set_token_bucket("bucket:key", 3.0, 1010.0)
        result = self.repo.get_token_bucket("bucket:key")
        assert result == (3.0, 1010.0)

    # --- Lifecycle tests ---

    def test_clear(self) -> None:
        """Clear removes all data."""
        self.repo.increment_counter("counter:key", ttl=60)
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.set_token_bucket("bucket:key", 5.0, 1000.0)

        self.repo.clear()

        assert self.repo.get_counter("counter:key") == 0
        assert self.repo.get_request_count("log:key", 0.0) == 0
        assert self.repo.get_token_bucket("bucket:key") is None

    def test_health_check(self) -> None:
        """Memory repository is always healthy."""
        assert self.repo.health_check() is True


class TestSQLiteRepository:
    """Tests for SQLite repository."""

    def setup_method(self) -> None:
        """Set up test fixtures with in-memory SQLite."""
        self.repo = SQLiteRepository(db_path=":memory:")

    # --- Counter tests ---

    def test_increment_counter_new_key(self) -> None:
        """New counter starts at 1."""
        result = self.repo.increment_counter("test:key", ttl=60)
        assert result == 1

    def test_increment_counter_existing(self) -> None:
        """Counter increments correctly."""
        self.repo.increment_counter("test:key", ttl=60)
        result = self.repo.increment_counter("test:key", ttl=60)
        assert result == 2

    def test_get_counter_existing(self) -> None:
        """Get returns current counter value."""
        self.repo.increment_counter("test:key", ttl=60)
        self.repo.increment_counter("test:key", ttl=60)
        assert self.repo.get_counter("test:key") == 2

    def test_get_counter_missing(self) -> None:
        """Get returns 0 for non-existent key."""
        assert self.repo.get_counter("nonexistent") == 0

    def test_counter_expiry(self) -> None:
        """Counter expires after TTL."""
        with patch("time.time", return_value=1000.0):
            self.repo.increment_counter("test:key", ttl=60)

        with patch("time.time", return_value=1061.0):
            assert self.repo.get_counter("test:key") == 0

    # --- Timestamp log tests ---

    def test_add_and_count_timestamps(self) -> None:
        """Timestamps are stored and counted correctly."""
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.add_request_timestamp("log:key", 1010.0)
        count = self.repo.get_request_count("log:key", 999.0)
        assert count == 2

    def test_count_within_window(self) -> None:
        """Only timestamps within window are counted."""
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.add_request_timestamp("log:key", 1010.0)
        self.repo.add_request_timestamp("log:key", 1020.0)
        count = self.repo.get_request_count("log:key", 1005.0)
        assert count == 2

    def test_remove_expired_entries(self) -> None:
        """Expired entries are removed from SQLite."""
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.add_request_timestamp("log:key", 1010.0)
        self.repo.add_request_timestamp("log:key", 1020.0)

        self.repo.remove_expired_entries("log:key", 1015.0)
        count = self.repo.get_request_count("log:key", 0.0)
        assert count == 1

    # --- Token bucket tests ---

    def test_get_token_bucket_missing(self) -> None:
        """Missing bucket returns None."""
        assert self.repo.get_token_bucket("bucket:key") is None

    def test_set_and_get_token_bucket(self) -> None:
        """Token bucket state persists in SQLite."""
        self.repo.set_token_bucket("bucket:key", 5.0, 1000.0)
        result = self.repo.get_token_bucket("bucket:key")
        assert result is not None
        assert abs(result[0] - 5.0) < 0.001
        assert abs(result[1] - 1000.0) < 0.001

    # --- Lifecycle tests ---

    def test_clear(self) -> None:
        """Clear removes all data."""
        self.repo.increment_counter("counter:key", ttl=60)
        self.repo.add_request_timestamp("log:key", 1000.0)
        self.repo.set_token_bucket("bucket:key", 5.0, 1000.0)

        self.repo.clear()

        assert self.repo.get_counter("counter:key") == 0
        assert self.repo.get_request_count("log:key", 0.0) == 0
        assert self.repo.get_token_bucket("bucket:key") is None

    def test_health_check(self) -> None:
        """SQLite repository reports healthy."""
        assert self.repo.health_check() is True
