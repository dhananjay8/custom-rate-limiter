"""Custom exceptions for the rate limiter application."""

from __future__ import annotations


class RateLimiterError(Exception):
    """Base exception for rate limiter errors."""

    pass


class AuthenticationError(RateLimiterError):
    """Raised when authentication fails."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        """Initialize authentication error.

        Args:
            message: Error message.
            status_code: HTTP status code (401 or 403).
        """
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class RateLimitExceededError(RateLimiterError):
    """Raised when a client exceeds their rate limit."""

    def __init__(self, client_id: str, endpoint: str, retry_after: float) -> None:
        """Initialize rate limit exceeded error.

        Args:
            client_id: The client that exceeded the limit.
            endpoint: The endpoint that was rate limited.
            retry_after: Seconds until the client can retry.
        """
        super().__init__(f"Rate limit exceeded for {client_id} on {endpoint}")
        self.client_id = client_id
        self.endpoint = endpoint
        self.retry_after = retry_after


class ConfigurationError(RateLimiterError):
    """Raised when configuration is invalid."""

    pass


class StorageError(RateLimiterError):
    """Raised when storage operations fail."""

    pass
