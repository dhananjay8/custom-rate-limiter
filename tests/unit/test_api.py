"""Unit tests for API endpoints."""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient


class TestFooEndpoint:
    """Tests for GET /foo endpoint."""

    def test_success_response(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Valid request returns 200 with success."""
        response = client.get("/foo", headers=basic_auth_header)
        assert response.status_code == 200
        assert response.json == {"success": True}

    def test_missing_auth(self, client: FlaskClient) -> None:
        """Missing Authorization header returns 401."""
        response = client.get("/foo")
        assert response.status_code == 401
        assert "error" in response.json

    def test_unknown_client(self, client: FlaskClient) -> None:
        """Unknown client returns 403."""
        response = client.get("/foo", headers={"Authorization": "Bearer unknown"})
        assert response.status_code == 403
        assert "error" in response.json

    def test_invalid_auth_format(self, client: FlaskClient) -> None:
        """Invalid auth format returns 401."""
        response = client.get("/foo", headers={"Authorization": "Basic token"})
        assert response.status_code == 401

    def test_rate_limit_headers(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Response includes rate limit headers."""
        response = client.get("/foo", headers=basic_auth_header)
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_basic_client(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Basic client is rate limited at 10 requests/minute."""
        for i in range(10):
            response = client.get("/foo", headers=basic_auth_header)
            assert response.status_code == 200

        response = client.get("/foo", headers=basic_auth_header)
        assert response.status_code == 429
        assert response.json == {"error": "rate limit exceeded"}

    def test_rate_limit_premium_client(self, client: FlaskClient, premium_auth_header: dict) -> None:
        """Premium client has higher limits."""
        for i in range(100):
            response = client.get("/foo", headers=premium_auth_header)
            assert response.status_code == 200

        response = client.get("/foo", headers=premium_auth_header)
        assert response.status_code == 429

    def test_request_id_header(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Response includes X-Request-ID header."""
        response = client.get("/foo", headers=basic_auth_header)
        assert "X-Request-ID" in response.headers

    def test_retry_after_header(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """429 response includes Retry-After header."""
        for _ in range(10):
            client.get("/foo", headers=basic_auth_header)

        response = client.get("/foo", headers=basic_auth_header)
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_invalid_request_weight_non_integer(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """X-Request-Weight must be an integer when provided."""
        headers = dict(basic_auth_header)
        headers["X-Request-Weight"] = "abc"
        response = client.get("/foo", headers=headers)
        assert response.status_code == 400
        assert response.json == {"error": "X-Request-Weight must be an integer"}

    def test_invalid_request_weight_minimum(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """X-Request-Weight must be >= 1 when provided."""
        headers = dict(basic_auth_header)
        headers["X-Request-Weight"] = "0"
        response = client.get("/foo", headers=headers)
        assert response.status_code == 400
        assert response.json == {"error": "X-Request-Weight must be >= 1"}

    def test_weighted_request_consumes_multiple_units(
        self, client: FlaskClient, basic_auth_header: dict
    ) -> None:
        """Custom request weight consumes multiple limit units."""
        headers = dict(basic_auth_header)
        headers["X-Request-Weight"] = "3"

        for _ in range(3):
            response = client.get("/foo", headers=headers)
            assert response.status_code == 200

        response = client.get("/foo", headers=headers)
        assert response.status_code == 429


class TestBarEndpoint:
    """Tests for GET /bar endpoint."""

    def test_success_response(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Valid request returns 200 with success."""
        response = client.get("/bar", headers=basic_auth_header)
        assert response.status_code == 200
        assert response.json == {"success": True}

    def test_missing_auth(self, client: FlaskClient) -> None:
        """Missing Authorization header returns 401."""
        response = client.get("/bar")
        assert response.status_code == 401

    def test_rate_limit_basic_client(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Basic client is rate limited at 20 requests/minute on /bar."""
        for i in range(20):
            response = client.get("/bar", headers=basic_auth_header)
            assert response.status_code == 200

        response = client.get("/bar", headers=basic_auth_header)
        assert response.status_code == 429

    def test_different_algorithm_than_foo(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Bar uses a different algorithm (sliding window log)."""
        # This test verifies that /bar and /foo have independent limits
        # Fill /foo limit
        for _ in range(10):
            client.get("/foo", headers=basic_auth_header)

        # /bar should still be available
        response = client.get("/bar", headers=basic_auth_header)
        assert response.status_code == 200


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_response(self, client: FlaskClient) -> None:
        """Health endpoint returns status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json
        assert data["status"] == "healthy"
        assert "storage" in data
        assert "algorithms" in data
        assert "circuit_breaker" in data
        assert "adaptive" in data
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    def test_no_auth_required(self, client: FlaskClient) -> None:
        """Health endpoint does not require authentication."""
        response = client.get("/health")
        assert response.status_code == 200


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint."""

    def test_metrics_response(self, client: FlaskClient) -> None:
        """Metrics endpoint returns counters."""
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json
        assert "total_requests" in data
        assert "allowed_requests" in data
        assert "rejected_requests" in data

    def test_metrics_increment(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Metrics increase after requests."""
        client.get("/foo", headers=basic_auth_header)
        client.get("/foo", headers=basic_auth_header)

        response = client.get("/metrics")
        data = response.json
        assert data["total_requests"] == 2
        assert data["allowed_requests"] == 2

    def test_prometheus_metrics(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Prometheus endpoint returns exposition format."""
        client.get("/foo", headers=basic_auth_header)
        client.get("/foo", headers=basic_auth_header)

        response = client.get("/metrics/prometheus")
        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")
        text = response.get_data(as_text=True)
        assert "rate_limiter_requests_total" in text
        assert "rate_limiter_client_requests_total" in text
        assert "rate_limiter_endpoint_requests_total" in text
        assert "client=\"client-basic\"" in text
        assert "endpoint=\"foo\"" in text


class TestAdminEndpoints:
    """Tests for admin endpoints."""

    def test_admin_config(self, client: FlaskClient) -> None:
        """Admin config returns current configuration."""
        response = client.get("/admin/config")
        assert response.status_code == 200
        data = response.json
        assert "storage" in data
        assert "algorithms" in data
        assert "clients" in data

    def test_admin_dry_run(self, client: FlaskClient) -> None:
        """Admin dry-run reports non-invasive diagnostics."""
        response = client.get("/admin/dry-run")
        assert response.status_code == 200
        data = response.json
        assert data["overall_status"] == "pass"
        assert "checks" in data
        assert "features" in data

    def test_admin_reset(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """Admin reset clears all state."""
        # Make some requests
        for _ in range(5):
            client.get("/foo", headers=basic_auth_header)

        # Reset
        response = client.post("/admin/reset")
        assert response.status_code == 200
        assert response.json["status"] == "reset_complete"

        # Metrics should be reset
        response = client.get("/metrics")
        assert response.json["total_requests"] == 0


class TestWriteEndpoints:
    """Tests for POST /foo and POST /bar."""

    def test_post_foo_success(self, client: FlaskClient, basic_auth_header: dict) -> None:
        """POST /foo is allowed and returns success."""
        response = client.post("/foo", headers=basic_auth_header)
        assert response.status_code == 200
        assert response.json == {"success": True}

    def test_post_foo_consumes_post_weight(
        self, client: FlaskClient, basic_auth_header: dict
    ) -> None:
        """POST /foo consumes FOO_POST_WEIGHT (default 5) units."""
        for _ in range(2):
            response = client.post("/foo", headers=basic_auth_header)
            assert response.status_code == 200

        response = client.post("/foo", headers=basic_auth_header)
        assert response.status_code == 429

    def test_post_bar_consumes_post_weight(
        self, client: FlaskClient, basic_auth_header: dict
    ) -> None:
        """POST /bar consumes BAR_POST_WEIGHT (default 3) units."""
        for _ in range(6):
            response = client.post("/bar", headers=basic_auth_header)
            assert response.status_code == 200

        response = client.post("/bar", headers=basic_auth_header)
        assert response.status_code == 429


class TestAdminAuth:
    """Tests for admin endpoint authentication."""

    def test_admin_endpoints_public_when_no_token(
        self, client: FlaskClient
    ) -> None:
        """Admin endpoints are public when ADMIN_TOKEN is not set."""
        response = client.get("/admin/config")
        assert response.status_code == 200

    def test_admin_endpoints_require_token(
        self, admin_token_client: FlaskClient
    ) -> None:
        """Admin endpoints require token when ADMIN_TOKEN is set."""
        response = admin_token_client.get("/admin/config")
        assert response.status_code == 401

    def test_admin_endpoints_with_valid_token(
        self, admin_token_client: FlaskClient, admin_token: str
    ) -> None:
        """Valid admin token grants access."""
        response = admin_token_client.get(
            "/admin/config", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

    def test_admin_endpoints_reject_invalid_token(
        self, admin_token_client: FlaskClient
    ) -> None:
        """Invalid admin token returns 403."""
        response = admin_token_client.get(
            "/admin/config", headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 403


class TestShadowMode:
    """Tests for X-Shadow-Mode header."""

    def test_shadow_mode_returns_decision_without_enforcing(
        self, shadow_enabled_client: FlaskClient, basic_auth_header: dict
    ) -> None:
        """Shadow mode returns the decision but does not block the request."""
        headers = dict(basic_auth_header)
        headers["X-Shadow-Mode"] = "true"

        for _ in range(15):
            response = shadow_enabled_client.get("/foo", headers=headers)
            assert response.status_code == 200
            assert response.json["shadow"] is True

    def test_shadow_mode_does_not_consume_live_quota(
        self, shadow_enabled_client: FlaskClient, basic_auth_header: dict
    ) -> None:
        """Shadow mode does not affect live rate limit counters."""
        headers = dict(basic_auth_header)
        headers["X-Shadow-Mode"] = "true"

        for _ in range(15):
            shadow_enabled_client.get("/foo", headers=headers)

        # Live request should still be allowed because shadow did not consume quota
        response = shadow_enabled_client.get("/foo", headers=basic_auth_header)
        assert response.status_code == 200

    def test_shadow_mode_disabled_when_setting_is_false(
        self, client: FlaskClient, basic_auth_header: dict
    ) -> None:
        """X-Shadow-Mode is ignored when shadow mode is disabled."""
        headers = dict(basic_auth_header)
        headers["X-Shadow-Mode"] = "true"

        response = client.get("/foo", headers=headers)
        assert response.status_code == 200
        assert response.json == {"success": True}


class TestErrorHandling:
    """Tests for error handling."""

    def test_404(self, client: FlaskClient) -> None:
        """Unknown route returns 404."""
        response = client.get("/unknown")
        assert response.status_code == 404
        assert response.json == {"error": "not found"}

    def test_method_not_allowed(self, client: FlaskClient) -> None:
        """Wrong HTTP method returns 405."""
        response = client.put("/foo", headers={"Authorization": "Bearer client-basic"})
        assert response.status_code == 405
