"""Weighted rate limiting for endpoint operations.

Different HTTP methods or operation types can consume different amounts
of rate limit quota. For example, a POST (write) may cost 5 tokens while
a GET (read) costs only 1.

Industry Usage:
    - GitHub API: Different weights for mutations vs queries
    - GraphQL APIs: Query complexity scoring
    - Stripe: Write operations have higher cost
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OperationWeight:
    """Weight configuration for an operation type.

    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH).
        cost: Number of tokens/units this operation consumes.
    """

    method: str
    cost: int = 1


@dataclass
class EndpointWeightConfig:
    """Weight configuration for an endpoint.

    Defines how much each HTTP method costs at this endpoint.
    """

    endpoint: str
    default_cost: int = 1
    method_costs: dict[str, int] = field(default_factory=dict)

    def get_cost(self, method: str) -> int:
        """Get the cost for a specific HTTP method.

        Args:
            method: HTTP method (uppercase).

        Returns:
            The cost in rate limit units.
        """
        return self.method_costs.get(method.upper(), self.default_cost)


class WeightedRateLimiter:
    """Manages weighted rate limiting across endpoints.

    Allows configuring different costs for different operations (HTTP methods)
    on each endpoint. The effective cost is applied when checking the rate limit.

    Example configuration:
        - GET /foo → costs 1 unit
        - POST /foo → costs 5 units
        - DELETE /foo → costs 10 units
    """

    def __init__(self) -> None:
        """Initialize with empty weight configuration."""
        self._endpoint_weights: dict[str, EndpointWeightConfig] = {}

    def configure_endpoint(
        self,
        endpoint: str,
        default_cost: int = 1,
        method_costs: dict[str, int] | None = None,
    ) -> None:
        """Configure weights for an endpoint.

        Args:
            endpoint: The endpoint name (e.g., 'foo', 'bar').
            default_cost: Default cost for unspecified methods.
            method_costs: Mapping of HTTP method → cost.
        """
        self._endpoint_weights[endpoint] = EndpointWeightConfig(
            endpoint=endpoint,
            default_cost=default_cost,
            method_costs=method_costs or {},
        )

    def get_cost(self, endpoint: str, method: str) -> int:
        """Get the cost for an operation.

        Args:
            endpoint: The endpoint being accessed.
            method: The HTTP method being used.

        Returns:
            The cost in rate limit units (minimum 1).
        """
        config = self._endpoint_weights.get(endpoint)
        if config is None:
            return 1
        return max(1, config.get_cost(method))

    def get_config(self) -> dict[str, dict]:
        """Get all weight configurations for monitoring."""
        return {
            endpoint: {
                "default_cost": config.default_cost,
                "method_costs": config.method_costs,
            }
            for endpoint, config in self._endpoint_weights.items()
        }
