"""Abstract base repository for rate limit storage."""

from __future__ import annotations

from abc import ABC, abstractmethod


class RateLimitRepository(ABC):
    """Abstract interface for rate limit data storage.

    All storage backends must implement this interface.
    The business layer interacts only with this abstraction,
    enabling easy swapping of storage implementations.
    """

    # --- Counter operations (Fixed Window, Sliding Window Counter) ---

    @abstractmethod
    def increment_counter(self, key: str, ttl: int) -> int:
        """Increment a counter and return the new value.

        Args:
            key: Unique key for the counter.
            ttl: Time-to-live in seconds for auto-expiry.

        Returns:
            The new counter value after increment.
        """
        ...

    @abstractmethod
    def get_counter(self, key: str) -> int:
        """Get the current value of a counter.

        Args:
            key: Unique key for the counter.

        Returns:
            Current counter value, or 0 if not found/expired.
        """
        ...

    # --- Timestamp log operations (Sliding Window Log) ---

    @abstractmethod
    def add_request_timestamp(self, key: str, timestamp: float) -> None:
        """Add a request timestamp to the log.

        Args:
            key: Unique key for the timestamp log.
            timestamp: Unix timestamp of the request.
        """
        ...

    @abstractmethod
    def get_request_count(self, key: str, window_start: float) -> int:
        """Count requests in the window.

        Args:
            key: Unique key for the timestamp log.
            window_start: Start of the current window (unix timestamp).

        Returns:
            Number of requests within the window.
        """
        ...

    @abstractmethod
    def remove_expired_entries(self, key: str, window_start: float) -> None:
        """Remove entries older than the window start.

        Args:
            key: Unique key for the timestamp log.
            window_start: Entries before this time are expired.
        """
        ...

    # --- Token Bucket operations ---

    @abstractmethod
    def get_token_bucket(self, key: str) -> tuple[float, float] | None:
        """Get current token bucket state.

        Args:
            key: Unique key for the token bucket.

        Returns:
            Tuple of (tokens, last_refill_timestamp) or None if not initialized.
        """
        ...

    @abstractmethod
    def set_token_bucket(self, key: str, tokens: float, last_refill: float) -> None:
        """Set token bucket state.

        Args:
            key: Unique key for the token bucket.
            tokens: Current number of tokens.
            last_refill: Timestamp of last refill calculation.
        """
        ...

    # --- Lifecycle ---

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored data. Used for testing and admin reset."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the storage backend is healthy.

        Returns:
            True if the backend is operational.
        """
        ...
