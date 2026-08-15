"""API route definitions."""

from __future__ import annotations

import time
from typing import Any

from flask import Flask, current_app, jsonify, request

from app.api.middleware import require_admin_auth, require_auth, require_rate_limit
from app.auth.bearer_auth import BearerAuthenticator
from app.services.dynamic_config import DynamicConfigManager
from app.services.rate_limiter import RateLimiterService


def create_routes(
    app: Flask,
    authenticator: BearerAuthenticator,
    rate_limiter: RateLimiterService,
    admin_token: str | None = None,
    dynamic_config: DynamicConfigManager | None = None,
) -> None:
    """Register all API routes on the Flask application.

    Args:
        app: Flask application instance.
        authenticator: Bearer token authenticator.
        rate_limiter: Rate limiter service instance.
        admin_token: Optional bearer token for admin endpoints.
        dynamic_config: Optional dynamic configuration manager.
    """
    auth = require_auth(authenticator)
    admin_auth = require_admin_auth(admin_token)

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

    @app.route("/foo", methods=["POST"])
    @auth
    @require_rate_limit(rate_limiter, "foo")
    def post_foo() -> tuple[Any, int]:
        """POST /foo - Write operation with higher default weight."""
        return jsonify({"success": True}), 200

    @app.route("/bar", methods=["POST"])
    @auth
    @require_rate_limit(rate_limiter, "bar")
    def post_bar() -> tuple[Any, int]:
        """POST /bar - Write operation with higher default weight."""
        return jsonify({"success": True}), 200

    # --- Health & Monitoring ---

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Any, int]:
        """GET /health - Application health check."""
        settings = current_app.config["SETTINGS"]
        storage_healthy = rate_limiter.repository.health_check()
        dry_run = rate_limiter.run_logical_dry_run()

        status = "healthy" if storage_healthy else "degraded"
        http_status = 200 if storage_healthy else 503
        started_at = app.config.get("APP_START_TIME", time.time())
        uptime_seconds = round(max(0.0, time.time() - started_at), 2)

        return jsonify({
            "status": status,
            "storage": {
                "backend": settings.rate_limit_storage.value,
                "healthy": storage_healthy,
            },
            "algorithms": {
                endpoint: algo.name
                for endpoint, algo in rate_limiter.algorithms.items()
            },
            "circuit_breaker": dry_run["features"]["circuit_breaker"],
            "adaptive": dry_run["features"]["adaptive"],
            "uptime_seconds": uptime_seconds,
        }), http_status

    @app.route("/metrics", methods=["GET"])
    def metrics() -> tuple[Any, int]:
        """GET /metrics - Application metrics."""
        return jsonify(rate_limiter.metrics.get_metrics()), 200

    @app.route("/metrics/prometheus", methods=["GET"])
    def prometheus_metrics() -> tuple[str, int]:
        """GET /metrics/prometheus - Prometheus-compatible metrics."""
        return rate_limiter.metrics.get_prometheus_metrics(), 200, {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"}

    @app.route("/admin/config", methods=["GET", "POST"])
    @admin_auth
    def admin_config() -> tuple[Any, int]:
        """GET/POST /admin/config - View or update current configuration."""
        if request.method == "POST":
            settings = current_app.config["SETTINGS"]
            if not settings.dynamic_config_enabled or dynamic_config is None:
                return jsonify({"error": "dynamic configuration is not enabled"}), 503

            data = request.get_json(silent=True) or {}
            try:
                current = dynamic_config.apply_update(data)
                return jsonify({"status": "updated", "config": current}), 200
            except (ValueError, KeyError, TypeError) as e:
                return jsonify({"error": str(e)}), 400

        settings = current_app.config["SETTINGS"]

        return jsonify({
            "storage": settings.rate_limit_storage.value,
            "algorithms": {
                endpoint: algo.name
                for endpoint, algo in rate_limiter.algorithms.items()
            },
            "clients": {
                client_id: {
                    "endpoints": {
                        ep: {"limit": cfg.limit, "window": cfg.window}
                        for ep, cfg in client_cfg.endpoints.items()
                    }
                }
                for client_id, client_cfg in rate_limiter.clients.items()
            },
            "environment": settings.app_env,
        }), 200

    @app.route("/admin/dry-run", methods=["GET"])
    @admin_auth
    def admin_dry_run() -> tuple[Any, int]:
        """GET /admin/dry-run - Non-invasive diagnostics for config and backend health."""
        report = rate_limiter.run_logical_dry_run()
        status_code = 200 if report.get("overall_status") == "pass" else 503
        return jsonify(report), status_code

    @app.route("/admin/reset", methods=["POST"])
    @admin_auth
    def admin_reset() -> tuple[Any, int]:
        """POST /admin/reset - Reset all rate limit state."""
        rate_limiter.repository.clear()
        rate_limiter.metrics.reset()
        return jsonify({"status": "reset_complete"}), 200

    # --- Advanced Feature Endpoints ---

    @app.route("/admin/adaptive", methods=["GET"])
    @admin_auth
    def admin_adaptive() -> tuple[Any, int]:
        """GET /admin/adaptive - Adaptive rate limiter status."""
        adaptive = current_app.config.get("ADAPTIVE")
        if adaptive is None:
            return jsonify({"enabled": False}), 200
        return jsonify(adaptive.get_status()), 200

    @app.route("/admin/circuit-breaker", methods=["GET"])
    @admin_auth
    def admin_circuit_breaker() -> tuple[Any, int]:
        """GET /admin/circuit-breaker - Circuit breaker status."""
        from app.repositories.resilient_repository import ResilientRepository

        repo = rate_limiter.repository
        if isinstance(repo, ResilientRepository):
            status = repo.circuit_breaker.get_status()
            status["enabled"] = True
            return jsonify(status), 200
        return jsonify({"enabled": False, "state": "not_configured"}), 200

    @app.route("/admin/quotas", methods=["GET"])
    @admin_auth
    def admin_quotas() -> tuple[Any, int]:
        """GET /admin/quotas - Quota pool status."""
        quota_manager = current_app.config.get("QUOTA_MANAGER")
        if quota_manager is None:
            return jsonify({"enabled": False}), 200
        return jsonify(quota_manager.get_all_pools()), 200

    @app.route("/admin/coalescing", methods=["GET"])
    @admin_auth
    def admin_coalescing() -> tuple[Any, int]:
        """GET /admin/coalescing - Request coalescing stats."""
        coalescer = current_app.config.get("COALESCER")
        if coalescer is None:
            return jsonify({"enabled": False}), 200
        return jsonify(coalescer.get_stats()), 200

    @app.route("/admin/weights", methods=["GET"])
    @admin_auth
    def admin_weights() -> tuple[Any, int]:
        """GET /admin/weights - Weighted operation config."""
        weighted = current_app.config.get("WEIGHTED")
        if weighted is None:
            return jsonify({"enabled": False}), 200
        return jsonify(weighted.get_config()), 200
