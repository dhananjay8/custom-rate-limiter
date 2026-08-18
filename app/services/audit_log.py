"""Audit logging for admin and privileged operations.

Keeps an in-memory ring buffer of privileged actions. This is not a
replacement for a persistent audit database, but it provides fast,
structured observability for admin activity.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app.logging.structured import get_logger


class AuditLogger:
    """Ring-buffer audit logger for administrative actions.

    Args:
        max_entries: Maximum number of retained entries (oldest evicted).
    """

    def __init__(self, max_entries: int = 1000) -> None:
        """Initialize the audit logger."""
        self._max_entries = max_entries
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._logger = get_logger()

    def record(
        self,
        action: str,
        actor: str,
        resource: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an audit event.

        Args:
            action: What happened (e.g. "admin.config_update").
            actor: Who performed it (e.g. "admin" or a masked token).
            resource: The endpoint or object affected.
            details: Optional structured details.
        """
        entry = {
            "timestamp": time.time(),
            "action": action,
            "actor": actor,
            "resource": resource,
            "details": details or {},
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries.pop(0)
        self._logger.info("Audit event", extra=entry)

    def get_log(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return recent audit entries, newest first.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of audit entries.
        """
        with self._lock:
            entries = self._entries[:]
            if limit:
                entries = entries[-limit:]
            return entries

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics for the audit log."""
        with self._lock:
            return {
                "enabled": True,
                "total_entries": len(self._entries),
                "max_entries": self._max_entries,
            }
