"""SQLite implementation of the rate limit repository."""

from __future__ import annotations

import sqlite3
import threading
import time

from app.repositories.base import RateLimitRepository


class SQLiteRepository(RateLimitRepository):
    """SQLite-based persistent storage for rate limit data.

    Uses SQLite with WAL mode for better concurrent read performance.
    Thread-safe through connection-per-thread pattern and proper locking.
    """

    def __init__(self, db_path: str = "rate_limiter.db") -> None:
        """Initialize SQLite repository.

        Args:
            db_path: Path to the SQLite database file. Use ':memory:' for testing.
        """
        self._db_path = db_path
        self._lock = threading.Lock()
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS counters (
                key TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                timestamp REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_request_logs_key_ts
                ON request_logs(key, timestamp);

            CREATE TABLE IF NOT EXISTS token_buckets (
                key TEXT PRIMARY KEY,
                tokens REAL NOT NULL,
                last_refill REAL NOT NULL
            );
            """
        )
        conn.commit()

    def increment_counter(self, key: str, ttl: int) -> int:
        """Increment counter atomically in SQLite.

        Args:
            key: Unique key for the counter.
            ttl: Time-to-live in seconds.

        Returns:
            New counter value.
        """
        with self._lock:
            conn = self._get_connection()
            now = time.time()

            row = conn.execute(
                "SELECT count, expires_at FROM counters WHERE key = ?", (key,)
            ).fetchone()

            if row and now < row["expires_at"]:
                new_count = row["count"] + 1
                conn.execute(
                    "UPDATE counters SET count = ? WHERE key = ?", (new_count, key)
                )
            else:
                new_count = 1
                conn.execute(
                    "INSERT OR REPLACE INTO counters (key, count, expires_at) VALUES (?, ?, ?)",
                    (key, 1, now + ttl),
                )

            conn.commit()
            return new_count

    def get_counter(self, key: str) -> int:
        """Get current counter value from SQLite.

        Args:
            key: Unique key for the counter.

        Returns:
            Current count or 0 if expired/missing.
        """
        with self._lock:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT count, expires_at FROM counters WHERE key = ?", (key,)
            ).fetchone()

            if row and time.time() < row["expires_at"]:
                return row["count"]
            return 0

    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add a timestamp to the request log in SQLite.

        Args:
            key: Unique key for the timestamp log.
            timestamp: Unix timestamp of the request.
        """
        with self._lock:
            conn = self._get_connection()
            conn.execute(
                "INSERT INTO request_logs (key, timestamp) VALUES (?, ?)",
                (key, timestamp),
            )
            conn.commit()

    def get_request_count(self, key: str, window_start: float) -> int:
        """Count requests within the window from SQLite.

        Args:
            key: Unique key for the timestamp log.
            window_start: Start of the window.

        Returns:
            Number of requests in the window.
        """
        with self._lock:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM request_logs WHERE key = ? AND timestamp >= ?",
                (key, window_start),
            ).fetchone()
            return row["cnt"] if row else 0

    def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove expired timestamps from SQLite.

        Args:
            key: Unique key for the timestamp log.
            window_start: Remove entries before this time.
        """
        with self._lock:
            conn = self._get_connection()
            conn.execute(
                "DELETE FROM request_logs WHERE key = ? AND timestamp < ?",
                (key, window_start),
            )
            conn.commit()

    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get token bucket state from SQLite.

        Args:
            key: Unique key for the bucket.

        Returns:
            (tokens, last_refill) or None.
        """
        with self._lock:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT tokens, last_refill FROM token_buckets WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return (row["tokens"], row["last_refill"])
            return None

    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        """Set token bucket state in SQLite.

        Args:
            key: Unique key for the bucket.
            tokens: Current token count.
            last_refill: Last refill timestamp.
        """
        with self._lock:
            conn = self._get_connection()
            conn.execute(
                "INSERT OR REPLACE INTO token_buckets (key, tokens, last_refill) VALUES (?, ?, ?)",
                (key, tokens, last_refill),
            )
            conn.commit()

    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            conn = self._get_connection()
            conn.executescript(
                """
                DELETE FROM counters;
                DELETE FROM request_logs;
                DELETE FROM token_buckets;
                """
            )
            conn.commit()

    def health_check(self) -> bool:
        """Check if SQLite is accessible."""
        try:
            conn = self._get_connection()
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False
