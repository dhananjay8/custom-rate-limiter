"""Application factory for creating and configuring the Flask app."""

from __future__ import annotations

import time
from typing import Any

from flask import Flask, jsonify

from app.algorithms.factory import AlgorithmFactory
from app.api.middleware import register_middleware
from app.api.openapi import register_openapi_routes
from app.api.routes import create_routes
from app.auth.bearer_auth import BearerAuthenticator
from app.config.settings import Settings, get_settings
from app.logging.structured import setup_logging
from app.repositories.factory import RepositoryFactory
from app.services.adaptive import AdaptiveRateLimiter
from app.services.coalescing import RequestCoalescer
from app.services.dynamic_config import DynamicConfigManager
from app.services.quota_sharing import QuotaManager
from app.services.rate_limiter import RateLimiterService
from app.services.weighted import WeightedRateLimiter


def create_app(settings: Settings | None = None) -> Flask:
    """Create and configure the Flask application.

    This is the main application factory that wires together all
    components using dependency injection.

    Args:
        settings: Optional settings override (useful for testing).

    Returns:
        Configured Flask application instance.
    """
    if settings is None:
        settings = get_settings()

    # Setup structured logging
    logger = setup_logging(settings.log_level)

    # Create Flask app
    app = Flask(__name__)
    app.config["APP_START_TIME"] = time.time()
    app.config["SETTINGS"] = settings

    # --- Dependency Injection ---

    # 1. Create repository (storage backend, optionally with circuit breaker)
    repository = RepositoryFactory.create(settings)
    logger.info(f"Storage backend: {settings.rate_limit_storage.value}")

    # 2. Create algorithms for each endpoint
    endpoint_algorithms = settings.get_endpoint_algorithms()
    algorithms = {
        endpoint: AlgorithmFactory.create(algo_type)
        for endpoint, algo_type in endpoint_algorithms.items()
    }
    for endpoint, algo in algorithms.items():
        logger.info(f"Endpoint /{endpoint} -> algorithm: {algo.name}")

    # 3. Load client configurations
    clients = settings.get_clients()
    logger.info(f"Loaded {len(clients)} client configurations")

    # 4. Create authenticator
    authenticator = BearerAuthenticator(valid_clients=set(clients.keys()))

    # 5. Create adaptive rate limiter
    adaptive = AdaptiveRateLimiter(
        enabled=settings.adaptive_enabled,
        sample_interval=settings.adaptive_sample_interval,
    )

    # 6. Create weighted rate limiter
    weighted = WeightedRateLimiter()
    weighted.configure_endpoint("foo", default_cost=settings.foo_get_weight, method_costs={
        "GET": settings.foo_get_weight,
        "POST": settings.foo_post_weight,
    })
    weighted.configure_endpoint("bar", default_cost=settings.bar_get_weight, method_costs={
        "GET": settings.bar_get_weight,
        "POST": settings.bar_post_weight,
    })

    # 7. Create request coalescer
    coalescer = RequestCoalescer(
        window_ms=settings.coalescing_window_ms,
        enabled=settings.coalescing_enabled,
    )

    # 8. Create quota manager with default pools
    quota_manager = QuotaManager()
    quota_manager.create_pool(
        pool_id="standard",
        total_limit=500,
        window=60,
        members={"client-basic"},
    )
    quota_manager.create_pool(
        pool_id="premium",
        total_limit=2000,
        window=60,
        members={"client-premium"},
    )

    # 9. Create rate limiter service
    rate_limiter = RateLimiterService(
        repository=repository,
        algorithms=algorithms,
        clients=clients,
        adaptive=adaptive,
        weighted=weighted,
        coalescer=coalescer,
        quota_manager=quota_manager,
    )

    # 10. Create dynamic config manager (loads persisted config if enabled)
    dynamic_config_path = settings.dynamic_config_path if settings.dynamic_config_enabled else None
    dynamic_config = DynamicConfigManager(
        file_path=dynamic_config_path,
        rate_limiter=rate_limiter,
        weighted=weighted,
    )

    # Store services in app config for route access
    app.config["ADAPTIVE"] = adaptive
    app.config["WEIGHTED"] = weighted
    app.config["COALESCER"] = coalescer
    app.config["QUOTA_MANAGER"] = quota_manager
    app.config["ADMIN_TOKEN"] = settings.admin_token
    app.config["DYNAMIC_CONFIG"] = dynamic_config

    # --- Register middleware and routes ---
    register_middleware(app, authenticator, rate_limiter)
    create_routes(
        app,
        authenticator,
        rate_limiter,
        admin_token=settings.admin_token,
        dynamic_config=dynamic_config,
    )
    register_openapi_routes(app)

    # --- Error handlers ---
    _register_error_handlers(app)

    logger.info("Application initialized successfully")

    return app


def _register_error_handlers(app: Flask) -> None:
    """Register global error handlers.

    Args:
        app: Flask application instance.
    """

    @app.errorhandler(404)
    def not_found(error: Any) -> tuple[Any, int]:
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(error: Any) -> tuple[Any, int]:
        return jsonify({"error": "method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(error: Any) -> tuple[Any, int]:
        return jsonify({"error": "internal server error"}), 500
