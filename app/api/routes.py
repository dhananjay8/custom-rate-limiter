"""API route definitions."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Flask, current_app, jsonify

from app.api.middleware import require_auth, require_rate_limit
from app.auth.bearer_auth import BearerAuthenticator
from app.services.rate_limiter import RateLimiterService


def create_routes(
    app: Flask,
    authenticator: BearerAuthenticator,
    rate_limiter: RateLimiterService,
) -> None:
    """Register all API routes on the Flask application.

    Args:
        app: Flask application instance.
        authenticator: Bearer token authenticator.
        rate_limiter: Rate limiter service instance.
    """
    auth = require_auth(authenticator)

    # --- Rate Limited Endpoints ---

    @app.route("/foo", methods=["GET"])
    @auth
    @require_rate_limit(rate_limiter, "foo")
    def get_foo() -> tuple[Any, int]:
        """GET /foo - Rate limited endpoint using configured algorithm."""
        return jsonify({"success": True}), 200

    @app.route("/bar", methods=["GET"])
    @auth
    @require_rate_limit(rate_limiter, "bar")
    def get_bar() -> tuple[Any, int]:
        """GET /bar - Rate limited endpoint using configured algorithm."""
        return jsonify({"success": True}), 200

    # --- Health & Monitoring ---

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Any, int]:
        """GET /health - Application health check."""
        settings = current_app.config["SETTINGS"]
        storage_healthy = rate_limiter.repository.health_check()

        status = "healthy" if storage_healthy else "degraded"
        http_status = 200 if storage_healthy else 503

        return jsonify({
            "status": status,
            "storage": {
                "backend": settings.rate_limit_storage.value,
                "healthy": storage_healthy,
            },
            "algorithms": {
                endpoint: algo.name
                for endpoint, algo in rate_limiter._algorithms.items()
            },
            "uptime_seconds": round(app.config.get("APP_START_TIME", 0), 2),
        }), http_status

    @app.route("/metrics", methods=["GET"])
    def metrics() -> tuple[Any, int]:
        """GET /metrics - Application metrics."""
        return jsonify(rate_limiter.metrics.get_metrics()), 200

    @app.route("/admin/config", methods=["GET"])
    def admin_config() -> tuple[Any, int]:
        """GET /admin/config - Current configuration."""
        settings = current_app.config["SETTINGS"]

        return jsonify({
            "storage": settings.rate_limit_storage.value,
            "algorithms": {
                endpoint: algo.name
                for endpoint, algo in rate_limiter._algorithms.items()
            },
            "clients": {
                client_id: {
                    "endpoints": {
                        ep: {"limit": cfg.limit, "window": cfg.window}
                        for ep, cfg in client_cfg.endpoints.items()
                    }
                }
                for client_id, client_cfg in rate_limiter._clients.items()
            },
            "environment": settings.app_env,
        }), 200

    @app.route("/admin/reset", methods=["POST"])
    def admin_reset() -> tuple[Any, int]:
        """POST /admin/reset - Reset all rate limit state."""
        rate_limiter.repository.clear()
        rate_limiter.metrics.reset()
        return jsonify({"status": "reset_complete"}), 200
