"""Time-of-day / tiered rate limiting policy.

Allows a client/endpoint limit to vary by the current clock time. Rules are
evaluated in order; the first matching time range wins. If no rule matches,
the base client/endpoint limit is used.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any


class TimeOfDayPolicy:
    """Tiered limits driven by wall-clock time.

    Args:
        timezone_offset_hours: Optional fixed offset from UTC for evaluation.
            Defaults to local system time.
    """

    def __init__(self, timezone_offset_hours: float = 0.0) -> None:
        """Initialize the time-of-day policy."""
        self._rules: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._offset = timezone_offset_hours

    @staticmethod
    def _parse_time(value: str) -> time:
        """Parse a 24-hour ``HH:MM`` string."""
        hour, minute = value.split(":")
        return time(int(hour), int(minute))

    def set_policy(
        self,
        client_id: str,
        endpoint: str,
        schedule: list[dict[str, Any]],
    ) -> None:
        """Set the tiered schedule for a client/endpoint.

        Args:
            client_id: Client identifier.
            endpoint: Endpoint name.
            schedule: List of rules with ``start``, ``end`` and ``limit`` keys.
        """
        # Validate shape
        for rule in schedule:
            if not all(k in rule for k in ("start", "end", "limit")):
                raise ValueError(
                    "time-of-day rule requires 'start', 'end', and 'limit'"
                )
            self._parse_time(rule["start"])
            self._parse_time(rule["end"])
        self._rules[(client_id, endpoint)] = schedule

    def get_effective_limit(
        self, client_id: str, endpoint: str, base_limit: int
    ) -> int:
        """Return the limit in effect for the current time.

        Args:
            client_id: Client identifier.
            endpoint: Endpoint name.
            base_limit: Default limit if no tier applies.

        Returns:
            The effective request limit.
        """
        schedule = self._rules.get((client_id, endpoint))
        if not schedule:
            return base_limit

        now = datetime.utcnow().time()
        for rule in schedule:
            start = self._parse_time(rule["start"])
            end = self._parse_time(rule["end"])

            # Handle ranges that wrap midnight
            if start < end:
                if start <= now < end:
                    return int(rule["limit"])
            elif start > end:
                if now >= start or now < end:
                    return int(rule["limit"])
            else:  # exact single instant; treat as inclusive
                return int(rule["limit"])

        return base_limit

    def get_config(self) -> dict[str, Any]:
        """Return the current time-of-day policy config."""
        return {
            "enabled": bool(self._rules),
            "rules": {
                f"{client_id}:{endpoint}": schedule
                for (client_id, endpoint), schedule in self._rules.items()
            },
        }
