"""Unit tests for authentication."""

from __future__ import annotations

import pytest

from app.auth.bearer_auth import BearerAuthenticator


class TestBearerAuthenticator:
    """Tests for Bearer token authentication."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.auth = BearerAuthenticator(valid_clients={"client-basic", "client-premium"})

    def test_valid_client(self) -> None:
        """Valid client ID is extracted correctly."""
        client_id, error = self.auth.extract_client_id("Bearer client-basic")
        assert client_id == "client-basic"
        assert error is None

    def test_valid_premium_client(self) -> None:
        """Premium client ID is extracted correctly."""
        client_id, error = self.auth.extract_client_id("Bearer client-premium")
        assert client_id == "client-premium"
        assert error is None

    def test_missing_header(self) -> None:
        """Missing header returns appropriate error."""
        client_id, error = self.auth.extract_client_id(None)
        assert client_id is None
        assert error == "missing_authorization"

    def test_empty_header(self) -> None:
        """Empty header returns appropriate error."""
        client_id, error = self.auth.extract_client_id("")
        assert client_id is None
        assert error == "missing_authorization"

    def test_invalid_format_no_bearer(self) -> None:
        """Header without Bearer prefix is invalid."""
        client_id, error = self.auth.extract_client_id("Basic client-basic")
        assert client_id is None
        assert error == "invalid_authorization_format"

    def test_invalid_format_no_space(self) -> None:
        """Header without space separator is invalid."""
        client_id, error = self.auth.extract_client_id("Bearerclient-basic")
        assert client_id is None
        assert error == "invalid_authorization_format"

    def test_unknown_client(self) -> None:
        """Unknown client ID returns appropriate error."""
        client_id, error = self.auth.extract_client_id("Bearer unknown-client")
        assert client_id is None
        assert error == "unknown_client"

    def test_empty_client_id(self) -> None:
        """Empty client ID after Bearer is invalid."""
        client_id, error = self.auth.extract_client_id("Bearer ")
        assert client_id is None
        assert error == "empty_client_id"

    def test_case_insensitive_bearer(self) -> None:
        """Bearer keyword is case-insensitive."""
        client_id, error = self.auth.extract_client_id("bearer client-basic")
        assert client_id == "client-basic"
        assert error is None

    def test_bearer_uppercase(self) -> None:
        """BEARER keyword works."""
        client_id, error = self.auth.extract_client_id("BEARER client-basic")
        assert client_id == "client-basic"
        assert error is None
