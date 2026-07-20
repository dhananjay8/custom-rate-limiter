"""Factory for creating rate limiting algorithm instances."""

from __future__ import annotations

from app.algorithms.base import RateLimitAlgorithm
from app.algorithms.fixed_window import FixedWindowAlgorithm
from app.algorithms.gcra import GCRAAlgorithm
from app.algorithms.leaky_bucket import LeakyBucketAlgorithm
from app.algorithms.sliding_window_counter import SlidingWindowCounterAlgorithm
from app.algorithms.sliding_window_log import SlidingWindowLogAlgorithm
from app.algorithms.token_bucket import TokenBucketAlgorithm
from app.config.settings import AlgorithmType


class AlgorithmFactory:
    """Factory for creating rate limiting algorithm instances.

    Supports registration of custom algorithms at runtime.
    """

    _algorithms: dict[AlgorithmType, type[RateLimitAlgorithm]] = {
        AlgorithmType.FIXED_WINDOW: FixedWindowAlgorithm,
        AlgorithmType.SLIDING_WINDOW_LOG: SlidingWindowLogAlgorithm,
        AlgorithmType.SLIDING_WINDOW_COUNTER: SlidingWindowCounterAlgorithm,
        AlgorithmType.TOKEN_BUCKET: TokenBucketAlgorithm,
        AlgorithmType.LEAKY_BUCKET: LeakyBucketAlgorithm,
        AlgorithmType.GCRA: GCRAAlgorithm,
    }

    @classmethod
    def create(cls, algorithm_type: AlgorithmType) -> RateLimitAlgorithm:
        """Create an algorithm instance by type.

        Args:
            algorithm_type: The type of algorithm to create.

        Returns:
            An instance of the requested algorithm.

        Raises:
            ValueError: If the algorithm type is not registered.
        """
        algorithm_class = cls._algorithms.get(algorithm_type)
        if algorithm_class is None:
            raise ValueError(
                f"Unknown algorithm type: {algorithm_type}. "
                f"Available: {list(cls._algorithms.keys())}"
            )
        return algorithm_class()

    @classmethod
    def register(
        cls, algorithm_type: AlgorithmType, algorithm_class: type[RateLimitAlgorithm]
    ) -> None:
        """Register a new algorithm type.

        Args:
            algorithm_type: The enum value for the algorithm.
            algorithm_class: The class implementing the algorithm.
        """
        cls._algorithms[algorithm_type] = algorithm_class

    @classmethod
    def available_algorithms(cls) -> list[str]:
        """List all available algorithm types."""
        return [algo.value for algo in cls._algorithms.keys()]
