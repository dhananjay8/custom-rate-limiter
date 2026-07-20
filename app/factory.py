"""Application factory for creating and configuring the Flask app."""

from __future__ import annotations

import time
from typing import Any

from flask import Flask, jsonify

from app.algorithms.factory import AlgorithmFactory
from app.api.middleware import register_middleware
from app.api.routes import create_routes
from app.auth.bearer_auth import BearerAuthenticator
from app.config.settings import Settings, get_settings
from app.logging.structured import setup_logging
from app.repositories.factory import RepositoryFactory
from app.services.rate_limiter import RateLimiterService


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

    # 1. Create repository (storage backend)
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

    # 5. Create rate limiter service
    rate_limiter = RateLimiterService(
        repository=repository,
        algorithms=algorithms,
        clients=clients,
    )

    # --- Register middleware and routes ---
    register_middleware(app, authenticator, rate_limiter)
    create_routes(app, authenticator, rate_limiter)

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
