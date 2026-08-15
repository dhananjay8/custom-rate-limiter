"""Request middleware for authentication and rate limiting."""

from __future__ import annotations

import time
import uuid
from functools import wraps
from typing import Any, Callable

from flask import Flask, Response, current_app, g, jsonify, request

from app.auth.bearer_auth import BearerAuthenticator
from app.exceptions import AuthenticationError
from app.logging.structured import get_logger
from app.services.rate_limiter import RateLimiterService


def register_middleware(
    app: Flask,
    authenticator: BearerAuthenticator,
    rate_limiter: RateLimiterService,
) -> None:
    """Register application middleware.

    Args:
        app: Flask application instance.
        authenticator: Bearer token authenticator.
        rate_limiter: Rate limiter service instance.
    """
    logger = get_logger()

    @app.before_request
    def add_request_id() -> None:
        """Add a unique request ID to every request."""
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.time()

    @app.after_request
    def add_response_headers(response: Response) -> Response:
        """Add standard response headers."""
        if hasattr(g, "request_id"):
            response.headers["X-Request-ID"] = g.request_id
        if hasattr(g, "rate_limit_result"):
            result = g.rate_limit_result
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))
        return response


def require_auth(authenticator: BearerAuthenticator) -> Callable[..., Any]:
    """Decorator that requires valid Bearer authentication.

    Args:
        authenticator: Bearer token authenticator.

    Returns:
        Decorator function.
    """

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            auth_header = request.headers.get("Authorization")
            client_id, error = authenticator.extract_client_id(auth_header)

            if error == "missing_authorization":
                return jsonify({"error": "Authorization header is required"}), 401
            elif error == "invalid_authorization_format":
                return jsonify({"error": "Invalid authorization format. Use: Bearer <client-id>"}), 401
            elif error == "empty_client_id":
                return jsonify({"error": "Client ID cannot be empty"}), 401
            elif error == "unknown_client":
                return jsonify({"error": "Unknown client"}), 403

            g.client_id = client_id
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_admin_auth(admin_token: str | None) -> Callable[..., Any]:
    """Decorator that requires a valid admin token for admin endpoints.

    Args:
        admin_token: The expected admin token. If None, admin routes are public.

    Returns:
        Decorator function.
    """

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            if admin_token is None:
                return f(*args, **kwargs)

            auth_header = request.headers.get("Authorization")
            if not auth_header:
                return jsonify({"error": "Authorization header is required"}), 401

            parts = auth_header.split(" ", 1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return jsonify({"error": "Invalid authorization format. Use: Bearer <admin-token>"}), 401

            if parts[1].strip() != admin_token:
                return jsonify({"error": "Invalid admin token"}), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_rate_limit(
    rate_limiter: RateLimiterService, endpoint_name: str
) -> Callable[..., Any]:
    """Decorator that enforces rate limiting on an endpoint.

    Args:
        rate_limiter: Rate limiter service.
        endpoint_name: The logical endpoint name (e.g., 'foo', 'bar').

    Returns:
        Decorator function.
    """

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            client_id = g.get("client_id")
            if not client_id:
                return jsonify({"error": "Authentication required"}), 401

            request_weight: int | None = None
            raw_weight = request.headers.get("X-Request-Weight")
            if raw_weight is not None:
                try:
                    request_weight = int(raw_weight)
                except ValueError:
                    return jsonify({"error": "X-Request-Weight must be an integer"}), 400

                if request_weight < 1:
                    return jsonify({"error": "X-Request-Weight must be >= 1"}), 400

            shadow_mode_enabled = current_app.config.get("SETTINGS", {}).shadow_mode_enabled
            is_shadow = (
                shadow_mode_enabled
                and request.headers.get("X-Shadow-Mode", "").lower() == "true"
            )

            result = rate_limiter.check_rate_limit(
                client_id,
                endpoint_name,
                method=request.method,
                request_weight=request_weight,
                shadow=is_shadow,
            )

            if is_shadow:
                response = jsonify({
                    "success": True,
                    "shadow": True,
                    "decision": "allowed" if result.allowed else "rejected",
                    "limit": result.limit,
                    "remaining": result.remaining,
                    "reset_at": int(result.reset_at),
                })
                response.headers["X-Shadow-Decision"] = (
                    "allowed" if result.allowed else "rejected"
                )
                response.headers["X-Shadow-Remaining"] = str(result.remaining)
                response.headers["X-Shadow-Allowed"] = str(result.allowed).lower()
                return response, 200

            g.rate_limit_result = result

            if not result.allowed:
                response = jsonify({"error": "rate limit exceeded"})
                response.status_code = 429
                response.headers["Retry-After"] = str(int(result.retry_after) + 1)
                response.headers["X-RateLimit-Limit"] = str(result.limit)
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))
                return response

            return f(*args, **kwargs)

        return decorated_function

    return decorator
