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

    # --- Advanced Feature Endpoints ---

    @app.route("/admin/adaptive", methods=["GET"])
    def admin_adaptive() -> tuple[Any, int]:
        """GET /admin/adaptive - Adaptive rate limiter status."""
        adaptive = current_app.config.get("ADAPTIVE")
        if adaptive is None:
            return jsonify({"enabled": False}), 200
        return jsonify(adaptive.get_status()), 200

    @app.route("/admin/circuit-breaker", methods=["GET"])
    def admin_circuit_breaker() -> tuple[Any, int]:
        """GET /admin/circuit-breaker - Circuit breaker status."""
        from app.repositories.resilient_repository import ResilientRepository

        repo = rate_limiter.repository
        if isinstance(repo, ResilientRepository):
            return jsonify(repo.circuit_breaker.get_status()), 200
        return jsonify({"enabled": False, "state": "not_configured"}), 200

    @app.route("/admin/quotas", methods=["GET"])
    def admin_quotas() -> tuple[Any, int]:
        """GET /admin/quotas - Quota pool status."""
        quota_manager = current_app.config.get("QUOTA_MANAGER")
        if quota_manager is None:
            return jsonify({"enabled": False}), 200
        return jsonify(quota_manager.get_all_pools()), 200

    @app.route("/admin/coalescing", methods=["GET"])
    def admin_coalescing() -> tuple[Any, int]:
        """GET /admin/coalescing - Request coalescing stats."""
        coalescer = current_app.config.get("COALESCER")
        if coalescer is None:
            return jsonify({"enabled": False}), 200
        return jsonify(coalescer.get_stats()), 200

    @app.route("/admin/weights", methods=["GET"])
    def admin_weights() -> tuple[Any, int]:
        """GET /admin/weights - Weighted operation config."""
        weighted = current_app.config.get("WEIGHTED")
        if weighted is None:
            return jsonify({"enabled": False}), 200
        return jsonify(weighted.get_config()), 200
