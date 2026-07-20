"""Structured JSON logging for the rate limiter application."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted string.
        """
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from the record
        if hasattr(record, "client_id"):
            log_entry["client_id"] = record.client_id  # type: ignore[attr-defined]
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint  # type: ignore[attr-defined]
        if hasattr(record, "algorithm"):
            log_entry["algorithm"] = record.algorithm  # type: ignore[attr-defined]
        if hasattr(record, "decision"):
            log_entry["decision"] = record.decision  # type: ignore[attr-defined]
        if hasattr(record, "remaining"):
            log_entry["remaining"] = record.remaining  # type: ignore[attr-defined]
        if hasattr(record, "latency_ms"):
            log_entry["latency_ms"] = record.latency_ms  # type: ignore[attr-defined]
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id  # type: ignore[attr-defined]

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured JSON logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("rate_limiter")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler with JSON formatting
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    return logger


def get_logger() -> logging.Logger:
    """Get the application logger."""
    return logging.getLogger("rate_limiter")
