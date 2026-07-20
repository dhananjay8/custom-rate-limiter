"""Rate limiter service - core business logic."""

from __future__ import annotations

import threading
import time
from typing import Any

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult
from app.config.settings import ClientConfig
from app.logging.structured import get_logger
from app.repositories.base import RateLimitRepository


class RateLimiterService:
    """Core rate limiting service.

    Orchestrates the rate limiting process by:
    1. Looking up client configuration
    2. Selecting the appropriate algorithm
    3. Checking the rate limit via the repository
    4. Recording metrics
    """

    def __init__(
        self,
        repository: RateLimitRepository,
        algorithms: dict[str, RateLimitAlgorithm],
        clients: dict[str, ClientConfig],
    ) -> None:
        """Initialize the rate limiter service.

        Args:
            repository: Storage backend for rate limit state.
            algorithms: Mapping of endpoint -> algorithm instance.
            clients: Mapping of client_id -> client configuration.
        """
        self._repository = repository
        self._algorithms = algorithms
        self._clients = clients
        self._logger = get_logger()
        self._metrics = RateLimiterMetrics()

    def check_rate_limit(self, client_id: str, endpoint: str) -> RateLimitResult:
        """Check if a request should be allowed.

        Args:
            client_id: The authenticated client making the request.
            endpoint: The endpoint being accessed (e.g., 'foo', 'bar').

        Returns:
            RateLimitResult indicating whether the request is allowed.

        Raises:
            ValueError: If endpoint has no configured algorithm or client has no config.
        """
        start_time = time.time()

        algorithm = self._algorithms.get(endpoint)
        if algorithm is None:
            raise ValueError(f"No algorithm configured for endpoint: {endpoint}")

        client_config = self._clients.get(client_id)
        if client_config is None:
            raise ValueError(f"No configuration found for client: {client_id}")

        endpoint_config = client_config.endpoints.get(endpoint)
        if endpoint_config is None:
            raise ValueError(
                f"No endpoint configuration for client={client_id}, endpoint={endpoint}"
            )

        result = algorithm.allow_request(
            repository=self._repository,
            client_id=client_id,
            endpoint=endpoint,
            limit=endpoint_config.limit,
            window=endpoint_config.window,
        )

        latency_ms = (time.time() - start_time) * 1000

        # Record metrics
        self._metrics.record_request(client_id, endpoint, result.allowed)

        # Structured logging
        self._logger.info(
            "Rate limit check",
            extra={
                "client_id": client_id,
                "endpoint": endpoint,
                "algorithm": algorithm.name,
                "decision": "allowed" if result.allowed else "rejected",
                "remaining": result.remaining,
                "latency_ms": round(latency_ms, 3),
            },
        )

        return result

    @property
    def metrics(self) -> "RateLimiterMetrics":
        """Access the metrics collector."""
        return self._metrics

    @property
    def repository(self) -> RateLimitRepository:
        """Access the repository (for admin operations)."""
        return self._repository


class RateLimiterMetrics:
    """Collects and exposes rate limiter metrics."""

    def __init__(self) -> None:
        """Initialize metrics counters."""
        self._lock = threading.Lock()
        self._total_requests: int = 0
        self._allowed_requests: int = 0
        self._rejected_requests: int = 0
        self._per_client: dict[str, dict[str, int]] = {}
        self._per_endpoint: dict[str, dict[str, int]] = {}

    def record_request(self, client_id: str, endpoint: str, allowed: bool) -> None:
        """Record a rate limit decision.

        Args:
            client_id: The client that made the request.
            endpoint: The endpoint accessed.
            allowed: Whether the request was allowed.
        """
        with self._lock:
            self._total_requests += 1
            if allowed:
                self._allowed_requests += 1
            else:
                self._rejected_requests += 1

            # Per client
            if client_id not in self._per_client:
                self._per_client[client_id] = {"allowed": 0, "rejected": 0, "total": 0}
            self._per_client[client_id]["total"] += 1
            if allowed:
                self._per_client[client_id]["allowed"] += 1
            else:
                self._per_client[client_id]["rejected"] += 1

            # Per endpoint
            if endpoint not in self._per_endpoint:
                self._per_endpoint[endpoint] = {"allowed": 0, "rejected": 0, "total": 0}
            self._per_endpoint[endpoint]["total"] += 1
            if allowed:
                self._per_endpoint[endpoint]["allowed"] += 1
            else:
                self._per_endpoint[endpoint]["rejected"] += 1

    def get_metrics(self) -> dict[str, Any]:
        """Get all collected metrics.

        Returns:
            Dictionary containing all metrics.
        """
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "allowed_requests": self._allowed_requests,
                "rejected_requests": self._rejected_requests,
                "per_client": dict(self._per_client),
                "per_endpoint": dict(self._per_endpoint),
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._total_requests = 0
            self._allowed_requests = 0
            self._rejected_requests = 0
            self._per_client.clear()
            self._per_endpoint.clear()
