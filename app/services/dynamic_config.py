"""Persistent dynamic configuration manager.

Allows runtime updates to client limits, endpoint algorithms, and weighted
operation costs. Changes are persisted to a JSON file and applied immediately
to the running RateLimiterService. On startup, any saved dynamic config is
loaded and applied before the app begins serving requests.
"""

from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING, Any

from app.algorithms.factory import AlgorithmFactory
from app.config.settings import AlgorithmType, ClientConfig, ClientEndpointConfig
from app.logging.structured import get_logger

if TYPE_CHECKING:
    from app.services.rate_limiter import RateLimiterService
    from app.services.weighted import WeightedRateLimiter


class DynamicConfigManager:
    """Manages runtime, persistent updates to rate limiter configuration.

    The configuration file uses the following shape:

        {
            "clients": {
                "client-basic": {
                    "foo": {"limit": 10, "window": 60},
                    "bar": {"limit": 20, "window": 60}
                }
            },
            "algorithms": {
                "foo": "fixed_window",
                "bar": "sliding_window_log"
            },
            "weights": {
                "foo": {"default_cost": 1, "method_costs": {"GET": 1, "POST": 5}},
                "bar": {"default_cost": 1, "method_costs": {"GET": 1, "POST": 3}}
            }
        }

    Args:
        file_path: Path to the dynamic config JSON file. If None/empty, no
            persistence is performed.
        rate_limiter: The running rate limiter service to update.
        weighted: Optional weighted rate limiter to update.
    """

    def __init__(
        self,
        file_path: str | None,
        rate_limiter: RateLimiterService,
        weighted: WeightedRateLimiter | None = None,
    ) -> None:
        """Initialize the dynamic config manager."""
        self._file_path = file_path
        self._rate_limiter = rate_limiter
        self._weighted = weighted
        self._lock = threading.Lock()
        self._logger = get_logger()
        self._last_config: dict[str, Any] = {}

        if self._file_path and os.path.exists(self._file_path):
            try:
                with open(self._file_path, encoding="utf-8") as f:
                    config = json.load(f)
                self.apply_update(config, save=False)
                self._logger.info(f"Loaded dynamic config from {self._file_path}")
            except Exception as e:
                self._logger.error(f"Failed to load dynamic config from {self._file_path}: {e}")

    def apply_update(self, update: dict[str, Any], save: bool = True) -> dict[str, Any]:
        """Apply a dynamic configuration update.

        Args:
            update: Dictionary with clients, algorithms, and/or weights updates.
            save: Whether to persist the update to disk.

        Returns:
            The current configuration after applying the update.

        Raises:
            ValueError: If an unknown client, endpoint, or algorithm is provided.
        """
        with self._lock:
            clients = update.get("clients", {})
            self._update_clients(clients)

            algorithms = update.get("algorithms", {})
            self._update_algorithms(algorithms)

            weights = update.get("weights", {})
            self._update_weights(weights)

            current = self._current_config()
            self._last_config = current

            if save and self._file_path:
                self._save(update)

            return current

    def _update_clients(self, clients: dict[str, Any]) -> None:
        """Apply client limit updates."""
        for client_id, endpoints in clients.items():
            if not isinstance(endpoints, dict):
                raise ValueError(f"Invalid config for client {client_id}: expected dict of endpoints")

            for endpoint, cfg in endpoints.items():
                if not isinstance(cfg, dict):
                    raise ValueError(f"Invalid config for {client_id}/{endpoint}: expected dict")

                limit = cfg.get("limit")
                window = cfg.get("window")
                if limit is None or window is None:
                    raise ValueError(
                        f"limit and window are required for {client_id}/{endpoint}"
                    )

                # Validate new algorithm exists (for client endpoint coverage check)
                if endpoint not in self._rate_limiter.algorithms:
                    raise ValueError(f"Unknown endpoint: {endpoint}")

                self._rate_limiter.update_client_endpoint(client_id, endpoint, int(limit), int(window))

    def _update_algorithms(self, algorithms: dict[str, Any]) -> None:
        """Apply algorithm updates."""
        for endpoint, algo in algorithms.items():
            algorithm_type = AlgorithmType(algo)
            # Validate the algorithm can be instantiated before mutating state
            AlgorithmFactory.create(algorithm_type)
            self._rate_limiter.update_algorithm(endpoint, algorithm_type)

    def _update_weights(self, weights: dict[str, Any]) -> None:
        """Apply weighted operation cost updates."""
        for endpoint, wcfg in weights.items():
            if not isinstance(wcfg, dict):
                raise ValueError(f"Invalid weight config for {endpoint}: expected dict")

            default_cost = max(1, int(wcfg.get("default_cost", 1)))
            method_costs = {
                method.upper(): max(1, int(cost))
                for method, cost in wcfg.get("method_costs", {}).items()
            }

            self._rate_limiter.update_weighted_endpoint(endpoint, default_cost, method_costs)

            if self._weighted is not None:
                self._weighted.configure_endpoint(endpoint, default_cost, method_costs)

    def _save(self, update: dict[str, Any]) -> None:
        """Persist the update to the configured file path."""
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(update, f, indent=2)
        except Exception as e:
            self._logger.error(f"Failed to save dynamic config to {self._file_path}: {e}")
            raise

    def _current_config(self) -> dict[str, Any]:
        """Build the current dynamic configuration snapshot."""
        clients: dict[str, Any] = {}
        for client_id, client_cfg in self._rate_limiter.clients.items():
            clients[client_id] = {
                ep: {"limit": cfg.limit, "window": cfg.window}
                for ep, cfg in client_cfg.endpoints.items()
            }

        algorithms = {
            endpoint: algo.name for endpoint, algo in self._rate_limiter.algorithms.items()
        }

        return {
            "clients": clients,
            "algorithms": algorithms,
            "weights": self._rate_limiter.weighted_config or {},
        }

    def get_config(self) -> dict[str, Any]:
        """Return the current dynamic configuration snapshot."""
        with self._lock:
            return self._current_config()
