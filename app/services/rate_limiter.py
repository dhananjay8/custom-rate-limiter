"""Rate limiter service - core business logic."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from app.algorithms.base import RateLimitAlgorithm, RateLimitResult
from app.config.settings import AlgorithmType, ClientConfig, ClientEndpointConfig
from app.logging.structured import get_logger
from app.repositories.base import RateLimitRepository

if TYPE_CHECKING:
    from app.services.adaptive import AdaptiveRateLimiter
    from app.services.coalescing import RequestCoalescer
    from app.services.quota_sharing import QuotaManager
    from app.services.weighted import WeightedRateLimiter


class RateLimiterService:
    """Core rate limiting service.

    Orchestrates the rate limiting process by:
    1. Checking request coalescing cache
    2. Applying weighted operation cost
    3. Applying adaptive load multiplier
    4. Checking shared quota pool
    5. Looking up client configuration
    6. Selecting the appropriate algorithm
    7. Checking the rate limit via the repository
    8. Recording metrics
    """

    def __init__(
        self,
        repository: RateLimitRepository,
        algorithms: dict[str, RateLimitAlgorithm],
        clients: dict[str, ClientConfig],
        adaptive: AdaptiveRateLimiter | None = None,
        weighted: WeightedRateLimiter | None = None,
        coalescer: RequestCoalescer | None = None,
        quota_manager: QuotaManager | None = None,
        shadow_repository: RateLimitRepository | None = None,
    ) -> None:
        """Initialize the rate limiter service.

        Args:
            repository: Storage backend for rate limit state.
            algorithms: Mapping of endpoint -> algorithm instance.
            clients: Mapping of client_id -> client configuration.
            adaptive: Optional adaptive rate limiter for load-based adjustment.
            weighted: Optional weighted rate limiter for operation costs.
            coalescer: Optional request coalescer for deduplication.
            quota_manager: Optional quota manager for shared pools.
            shadow_repository: Optional separate storage for shadow-mode checks.
        """
        self._repository = repository
        self._algorithms = algorithms
        self._clients = clients
        self._adaptive = adaptive
        self._weighted = weighted
        self._coalescer = coalescer
        self._quota_manager = quota_manager
        self._logger = get_logger()
        self._metrics = RateLimiterMetrics()

        if shadow_repository is None:
            from app.repositories.memory_repository import MemoryRepository

            shadow_repository = MemoryRepository()
        self._shadow_repository = shadow_repository

    def check_rate_limit(
        self,
        client_id: str,
        endpoint: str,
        method: str = "GET",
        request_weight: int | None = None,
        shadow: bool = False,
    ) -> RateLimitResult:
        """Check if a request should be allowed.

        Args:
            client_id: The authenticated client making the request.
            endpoint: The endpoint being accessed (e.g., 'foo', 'bar').
            method: HTTP method (for weighted operations).
            request_weight: Optional override for operation cost.
            shadow: If True, run a non-enforcing check against a separate repository.

        Returns:
            RateLimitResult indicating whether the request is allowed.

        Raises:
            ValueError: If endpoint has no configured algorithm or client has no config.
        """
        start_time = time.time()
        repository = self._shadow_repository if shadow else self._repository

        # 1. Get operation weight
        cost = 1
        if self._weighted:
            cost = self._weighted.get_cost(endpoint, method)
        if request_weight is not None:
            cost = request_weight
        cost = max(1, cost)

        # 2. Check coalescing cache (only in live mode)
        coalescing_key = f"{endpoint}:{method.upper()}:{cost}"
        if not shadow and self._coalescer:
            cached = self._coalescer.get_cached(client_id, coalescing_key)
            if cached is not None:
                self._metrics.record_request(client_id, endpoint, cached.allowed)
                return cached

        # 3. Check shared quota pool (only in live mode)
        if not shadow and self._quota_manager:
            pool_allowed, pool_remaining = self._quota_manager.check_pool_quota(
                client_id, cost
            )
            if not pool_allowed:
                result = RateLimitResult(
                    allowed=False,
                    limit=0,
                    remaining=0,
                    reset_at=time.time() + 60,
                    current_count=0,
                )
                self._metrics.record_request(client_id, endpoint, False)
                return result

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

        # 4. Apply adaptive multiplier to the limit (only in live mode)
        effective_limit = endpoint_config.limit
        if not shadow and self._adaptive:
            effective_limit = self._adaptive.get_effective_limit(endpoint_config.limit)

        # 5. Run the rate limit algorithm
        result = algorithm.allow_request(
            repository=repository,
            client_id=client_id,
            endpoint=endpoint,
            limit=effective_limit,
            window=endpoint_config.window,
        )

        # Apply weighted operation cost by consuming additional units.
        # Cost=1 means normal behavior; cost>1 simulates extra request units.
        if result.allowed and cost > 1:
            for _ in range(cost - 1):
                result = algorithm.allow_request(
                    repository=repository,
                    client_id=client_id,
                    endpoint=endpoint,
                    limit=effective_limit,
                    window=endpoint_config.window,
                )
                if not result.allowed:
                    break

        latency_ms = (time.time() - start_time) * 1000

        # 6. Record adaptive metrics (only in live mode)
        if not shadow and self._adaptive:
            self._adaptive.record_request_end(latency_ms)

        # 7. Cache result for coalescing (only in live mode)
        if not shadow and self._coalescer:
            self._coalescer.cache_result(client_id, coalescing_key, result)

        # 8. Record metrics (only in live mode)
        if not shadow:
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
                "effective_limit": effective_limit,
                "cost": cost,
                "shadow": shadow,
                "latency_ms": round(latency_ms, 3),
            },
        )

        return result

    @property
    def metrics(self) -> "RateLimiterMetrics":
        """Access the metrics collector."""
        return self._metrics

    @property
    def algorithms(self) -> dict[str, RateLimitAlgorithm]:
        """Access configured endpoint algorithms."""
        return dict(self._algorithms)

    @property
    def clients(self) -> dict[str, ClientConfig]:
        """Access configured client rate limit profiles."""
        return dict(self._clients)

    @property
    def repository(self) -> RateLimitRepository:
        """Access the repository (for admin operations)."""
        return self._repository

    @property
    def weighted_config(self) -> dict[str, Any] | None:
        """Access the weighted rate limiter configuration."""
        if self._weighted is None:
            return None
        return self._weighted.get_config()

    def update_client_endpoint(
        self,
        client_id: str,
        endpoint: str,
        limit: int,
        window: int,
    ) -> None:
        """Update a client-endpoint limit at runtime.

        Args:
            client_id: Client to update.
            endpoint: Endpoint to update.
            limit: New request limit.
            window: New window size in seconds.
        """
        client_config = self._clients.get(client_id)
        if client_config is None:
            client_config = ClientConfig()
            self._clients[client_id] = client_config

        client_config.endpoints[endpoint] = ClientEndpointConfig(limit=limit, window=window)
        self._logger.info(
            "Updated client endpoint config",
            extra={"client_id": client_id, "endpoint": endpoint, "limit": limit, "window": window},
        )

    def update_algorithm(self, endpoint: str, algorithm_type: AlgorithmType) -> None:
        """Update the algorithm for an endpoint at runtime.

        Args:
            endpoint: Endpoint to update.
            algorithm_type: New algorithm type.
        """
        from app.algorithms.factory import AlgorithmFactory

        self._algorithms[endpoint] = AlgorithmFactory.create(algorithm_type)
        self._logger.info(
            "Updated endpoint algorithm",
            extra={"endpoint": endpoint, "algorithm": algorithm_type.value},
        )

    def update_weighted_endpoint(
        self,
        endpoint: str,
        default_cost: int,
        method_costs: dict[str, int],
    ) -> None:
        """Update weighted operation cost for an endpoint at runtime.

        Args:
            endpoint: Endpoint to update.
            default_cost: Default cost for unspecified methods.
            method_costs: Mapping of HTTP method to cost.
        """
        if self._weighted is not None:
            self._weighted.configure_endpoint(endpoint, default_cost, method_costs)
            self._logger.info(
                "Updated weighted endpoint config",
                extra={"endpoint": endpoint, "default_cost": default_cost, "method_costs": method_costs},
            )

    def run_logical_dry_run(self) -> dict[str, Any]:
        """Run non-invasive configuration and storage diagnostics.

        Returns:
            Dictionary with pass/fail checks and feature status details.
        """
        checks: list[dict[str, Any]] = []
        configured_endpoints = set(self._algorithms.keys())

        checks.append(
            {
                "check": "endpoint_algorithms_configured",
                "status": "pass" if configured_endpoints else "fail",
                "details": sorted(configured_endpoints),
            }
        )

        missing_client_endpoint_configs: list[dict[str, Any]] = []
        for client_id, client_cfg in self._clients.items():
            missing = sorted(configured_endpoints - set(client_cfg.endpoints.keys()))
            if missing:
                missing_client_endpoint_configs.append(
                    {"client_id": client_id, "missing_endpoints": missing}
                )

        checks.append(
            {
                "check": "client_endpoint_coverage",
                "status": "pass" if not missing_client_endpoint_configs else "fail",
                "details": missing_client_endpoint_configs,
            }
        )

        storage_healthy = self._repository.health_check()
        checks.append(
            {
                "check": "storage_health",
                "status": "pass" if storage_healthy else "fail",
                "details": {"healthy": storage_healthy},
            }
        )

        circuit_breaker_status: dict[str, Any] = {
            "enabled": False,
            "state": "not_configured",
        }
        try:
            from app.repositories.resilient_repository import ResilientRepository

            if isinstance(self._repository, ResilientRepository):
                circuit_breaker_status = {
                    "enabled": True,
                    **self._repository.circuit_breaker.get_status(),
                }
        except Exception:
            pass

        adaptive_status = (
            self._adaptive.get_status() if self._adaptive is not None else {"enabled": False}
        )
        coalescing_status = (
            self._coalescer.get_stats() if self._coalescer is not None else {"enabled": False}
        )
        quota_status = (
            self._quota_manager.get_all_pools()
            if self._quota_manager is not None
            else {"enabled": False}
        )
        weighted_config = (
            self._weighted.get_config() if self._weighted is not None else {"enabled": False}
        )

        overall_status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"

        return {
            "overall_status": overall_status,
            "checks": checks,
            "features": {
                "adaptive": adaptive_status,
                "circuit_breaker": circuit_breaker_status,
                "coalescing": coalescing_status,
                "quota_pools": quota_status,
                "weighted": weighted_config,
            },
        }


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

    def get_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus exposition format.

        Returns:
            Prometheus text with HELP/TYPE lines and metric samples.
        """
        with self._lock:
            lines: list[str] = []

            lines.append("# HELP rate_limiter_requests_total Total rate limit decisions")
            lines.append("# TYPE rate_limiter_requests_total counter")
            lines.append(f"rate_limiter_requests_total{{decision=\"allowed\"}} {self._allowed_requests}")
            lines.append(f"rate_limiter_requests_total{{decision=\"rejected\"}} {self._rejected_requests}")

            lines.append("# HELP rate_limiter_client_requests_total Requests per client")
            lines.append("# TYPE rate_limiter_client_requests_total counter")
            for client_id, counts in self._per_client.items():
                for decision in ("allowed", "rejected"):
                    value = counts.get(decision, 0)
                    lines.append(
                        f"rate_limiter_client_requests_total{{client=\"{client_id}\",decision=\"{decision}\"}} {value}"
                    )

            lines.append("# HELP rate_limiter_endpoint_requests_total Requests per endpoint")
            lines.append("# TYPE rate_limiter_endpoint_requests_total counter")
            for endpoint, counts in self._per_endpoint.items():
                for decision in ("allowed", "rejected"):
                    value = counts.get(decision, 0)
                    lines.append(
                        f"rate_limiter_endpoint_requests_total{{endpoint=\"{endpoint}\",decision=\"{decision}\"}} {value}"
                    )

            return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._total_requests = 0
            self._allowed_requests = 0
            self._rejected_requests = 0
            self._per_client.clear()
            self._per_endpoint.clear()
