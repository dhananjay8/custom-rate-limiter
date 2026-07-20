"""Factory for creating repository instances."""

from __future__ import annotations

from app.config.settings import Settings, StorageBackend
from app.repositories.base import RateLimitRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SQLiteRepository


class RepositoryFactory:
    """Factory for creating storage repository instances.

    Creates the appropriate repository based on configuration.
    Optionally wraps with circuit breaker for resilience.
    """

    @staticmethod
    def create(settings: Settings) -> RateLimitRepository:
        """Create a repository based on settings.

        Args:
            settings: Application settings.

        Returns:
            A repository instance (optionally wrapped with circuit breaker).

        Raises:
            ValueError: If the storage backend is not supported.
        """
        if settings.rate_limit_storage == StorageBackend.MEMORY:
            repo = MemoryRepository()
        elif settings.rate_limit_storage == StorageBackend.SQLITE:
            repo = SQLiteRepository(db_path=settings.sqlite_db_path)
        elif settings.rate_limit_storage == StorageBackend.REDIS:
            from app.repositories.redis_repository import RedisRepository

            repo = RedisRepository(
                url=settings.redis_url,
                key_prefix=settings.redis_key_prefix,
            )
        else:
            raise ValueError(
                f"Unsupported storage backend: {settings.rate_limit_storage}"
            )

        # Wrap with circuit breaker if enabled
        if settings.circuit_breaker_enabled:
            from app.repositories.resilient_repository import ResilientRepository
            from app.resilience.circuit_breaker import CircuitBreaker

            circuit_breaker = CircuitBreaker(
                failure_threshold=settings.circuit_breaker_failure_threshold,
                recovery_timeout=settings.circuit_breaker_recovery_timeout,
            )
            return ResilientRepository(
                repository=repo,
                circuit_breaker=circuit_breaker,
            )

        return repo
