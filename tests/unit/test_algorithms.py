"""Unit tests for rate limiting algorithms."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.algorithms.fixed_window import FixedWindowAlgorithm
from app.algorithms.sliding_window_counter import SlidingWindowCounterAlgorithm
from app.algorithms.sliding_window_log import SlidingWindowLogAlgorithm
from app.algorithms.token_bucket import TokenBucketAlgorithm
from app.repositories.memory_repository import MemoryRepository


class TestFixedWindowAlgorithm:
    """Tests for Fixed Window Counter algorithm."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.algo = FixedWindowAlgorithm()
        self.repo = MemoryRepository()

    def test_name(self) -> None:
        """Algorithm reports correct name."""
        assert self.algo.name == "fixed_window"

    def test_first_request_allowed(self) -> None:
        """First request should always be allowed."""
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is True
        assert result.remaining == 9
        assert result.current_count == 1

    def test_requests_within_limit(self) -> None:
        """Requests within limit should all be allowed."""
        for i in range(10):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True
            assert result.remaining == 10 - (i + 1)

    def test_request_exceeds_limit(self) -> None:
        """Request exceeding limit should be rejected."""
        for _ in range(10):
            self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is False
        assert result.remaining == 0

    def test_different_clients_independent(self) -> None:
        """Different clients have independent rate limits."""
        for _ in range(10):
            self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

        # client-1 is exhausted
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is False

        # client-2 is still fresh
        result = self.algo.allow_request(self.repo, "client-2", "foo", limit=10, window=60)
        assert result.allowed is True

    def test_different_endpoints_independent(self) -> None:
        """Different endpoints have independent rate limits."""
        for _ in range(10):
            self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

        # foo is exhausted
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is False

        # bar is still fresh
        result = self.algo.allow_request(self.repo, "client-1", "bar", limit=10, window=60)
        assert result.allowed is True

    def test_window_reset(self) -> None:
        """Counter resets after window expires."""
        with patch("time.time", return_value=1000.0):
            for _ in range(10):
                self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is False

        # Move to next window
        with patch("time.time", return_value=1060.0):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True
            assert result.remaining == 9

    def test_limit_of_one(self) -> None:
        """Limit of 1 allows exactly one request."""
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=1, window=60)
        assert result.allowed is True

        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=1, window=60)
        assert result.allowed is False

    def test_result_metadata(self) -> None:
        """Result contains correct metadata."""
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.limit == 10
        assert result.reset_at > time.time()


class TestSlidingWindowLogAlgorithm:
    """Tests for Sliding Window Log algorithm."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.algo = SlidingWindowLogAlgorithm()
        self.repo = MemoryRepository()

    def test_name(self) -> None:
        """Algorithm reports correct name."""
        assert self.algo.name == "sliding_window_log"

    def test_first_request_allowed(self) -> None:
        """First request should always be allowed."""
        result = self.algo.allow_request(self.repo, "client-1", "bar", limit=20, window=60)
        assert result.allowed is True
        assert result.remaining == 19

    def test_requests_within_limit(self) -> None:
        """Requests within limit should be allowed."""
        for i in range(20):
            result = self.algo.allow_request(self.repo, "client-1", "bar", limit=20, window=60)
            assert result.allowed is True

    def test_request_exceeds_limit(self) -> None:
        """Request exceeding limit should be rejected."""
        for _ in range(20):
            self.algo.allow_request(self.repo, "client-1", "bar", limit=20, window=60)

        result = self.algo.allow_request(self.repo, "client-1", "bar", limit=20, window=60)
        assert result.allowed is False
        assert result.remaining == 0

    def test_sliding_window_precision(self) -> None:
        """Sliding window should precisely track request timestamps."""
        base_time = 1000.0

        # Fill up the limit
        with patch("time.time", return_value=base_time):
            for _ in range(5):
                self.algo.allow_request(self.repo, "client-1", "bar", limit=5, window=60)

        # Still within window - should be rejected
        with patch("time.time", return_value=base_time + 30):
            result = self.algo.allow_request(self.repo, "client-1", "bar", limit=5, window=60)
            assert result.allowed is False

        # Just after window expires for earliest requests
        with patch("time.time", return_value=base_time + 61):
            result = self.algo.allow_request(self.repo, "client-1", "bar", limit=5, window=60)
            assert result.allowed is True

    def test_different_clients_independent(self) -> None:
        """Different clients have independent limits."""
        for _ in range(5):
            self.algo.allow_request(self.repo, "client-1", "bar", limit=5, window=60)

        result = self.algo.allow_request(self.repo, "client-1", "bar", limit=5, window=60)
        assert result.allowed is False

        result = self.algo.allow_request(self.repo, "client-2", "bar", limit=5, window=60)
        assert result.allowed is True


class TestSlidingWindowCounterAlgorithm:
    """Tests for Sliding Window Counter algorithm."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.algo = SlidingWindowCounterAlgorithm()
        self.repo = MemoryRepository()

    def test_name(self) -> None:
        """Algorithm reports correct name."""
        assert self.algo.name == "sliding_window_counter"

    def test_first_request_allowed(self) -> None:
        """First request should always be allowed."""
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is True

    def test_requests_within_limit(self) -> None:
        """Requests within limit should be allowed."""
        for _ in range(9):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True

    def test_request_exceeds_limit(self) -> None:
        """Enough requests should eventually be rejected."""
        results = []
        for _ in range(15):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            results.append(result.allowed)

        # Should have some rejections
        assert False in results

    def test_weighted_calculation(self) -> None:
        """Previous window contributes weighted count."""
        base_time = 1000.0
        window = 60

        # Fill previous window
        with patch("time.time", return_value=base_time):
            for _ in range(8):
                self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=window)

        # At 50% through current window, previous window contributes 50%
        with patch("time.time", return_value=base_time + window + 30):
            # Previous count * 0.5 + current count = 8 * 0.5 + 0 = 4
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=window)
            assert result.allowed is True


class TestTokenBucketAlgorithm:
    """Tests for Token Bucket algorithm."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.algo = TokenBucketAlgorithm()
        self.repo = MemoryRepository()

    def test_name(self) -> None:
        """Algorithm reports correct name."""
        assert self.algo.name == "token_bucket"

    def test_first_request_allowed(self) -> None:
        """First request should always be allowed."""
        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is True
        assert result.remaining == 9

    def test_burst_allowed(self) -> None:
        """All tokens can be consumed in a burst."""
        for i in range(10):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True

    def test_exceeds_bucket_capacity(self) -> None:
        """Requests beyond bucket capacity should be rejected."""
        for _ in range(10):
            self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

        result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
        assert result.allowed is False

    def test_token_refill(self) -> None:
        """Tokens should refill over time."""
        base_time = 1000.0

        # Consume all tokens
        with patch("time.time", return_value=base_time):
            for _ in range(10):
                self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is False

        # Wait for refill (6 seconds = 1 token at rate of 10/60)
        with patch("time.time", return_value=base_time + 6.1):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is True

    def test_partial_refill(self) -> None:
        """Partial time elapsed adds partial tokens."""
        base_time = 1000.0

        # Consume all tokens
        with patch("time.time", return_value=base_time):
            for _ in range(10):
                self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

        # 3 seconds at 10/60 rate = 0.5 tokens (not enough)
        with patch("time.time", return_value=base_time + 3):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            assert result.allowed is False

    def test_max_tokens_capped(self) -> None:
        """Tokens should not exceed bucket capacity."""
        base_time = 1000.0

        # Use one token
        with patch("time.time", return_value=base_time):
            self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)

        # Wait a very long time
        with patch("time.time", return_value=base_time + 1000):
            result = self.algo.allow_request(self.repo, "client-1", "foo", limit=10, window=60)
            # Should have max tokens (capped at limit)
            assert result.remaining <= 10
