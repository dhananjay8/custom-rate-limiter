"""Factory for creating repository instances."""

from __future__ import annotations

from app.config.settings import Settings, StorageBackend
from app.repositories.base import RateLimitRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.sqlite_repository import SQLiteRepository


class RepositoryFactory:
    """Factory for creating storage repository instances.

    Creates the appropriate repository based on configuration.
    """

    @staticmethod
    def create(settings: Settings) -> RateLimitRepository:
        """Create a repository based on settings.

        Args:
            settings: Application settings.

        Returns:
            A repository instance.

        Raises:
            ValueError: If the storage backend is not supported.
        """
        if settings.rate_limit_storage == StorageBackend.MEMORY:
            return MemoryRepository()
        elif settings.rate_limit_storage == StorageBackend.SQLITE:
            return SQLiteRepository(db_path=settings.sqlite_db_path)
        else:
            raise ValueError(
                f"Unsupported storage backend: {settings.rate_limit_storage}"
            )
