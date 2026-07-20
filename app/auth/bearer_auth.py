"""Bearer token authentication for client identification."""

from __future__ import annotations

from typing import Optional


class BearerAuthenticator:
    """Authenticates clients using Bearer token from Authorization header.

    Validates that:
    1. Authorization header is present
    2. Token format is 'Bearer <client-id>'
    3. Client ID is recognized
    """

    def __init__(self, valid_clients: set[str]) -> None:
        """Initialize authenticator with known client IDs.

        Args:
            valid_clients: Set of recognized client identifiers.
        """
        self._valid_clients = valid_clients

    def extract_client_id(self, auth_header: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Extract and validate client ID from Authorization header.

        Args:
            auth_header: The Authorization header value.

        Returns:
            Tuple of (client_id, error_message).
            If authentication succeeds, error_message is None.
            If it fails, client_id is None and error_message describes the issue.
        """
        if not auth_header:
            return None, "missing_authorization"

        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None, "invalid_authorization_format"

        client_id = parts[1].strip()
        if not client_id:
            return None, "empty_client_id"

        if client_id not in self._valid_clients:
            return None, "unknown_client"

        return client_id, None
