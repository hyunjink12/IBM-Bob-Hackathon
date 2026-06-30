"""Builds health-check payloads for load balancers and compose healthchecks."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class HealthStatus:
    """Immutable snapshot returned by the health endpoint."""

    status: str
    service: str
    environment: str
    timestamp: str


class HealthCheckManager:
    """
    Knows how to say “yep, the API is alive.”

    Casual: returns a small JSON-friendly dict when something pings /health.

    Centralizes health payload shape so routes stay thin and future checks
    (database, market-data feeds, etc.) can be added here without touching
    HTTP wiring.
    """

    def __init__(self, service_name: str, environment: str) -> None:
        self._service_name = service_name
        self._environment = environment

    def get_status(self) -> HealthStatus:
        """Return a fresh health snapshot with an UTC timestamp."""
        return HealthStatus(
            status="ok",
            service=self._service_name,
            environment=self._environment,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
