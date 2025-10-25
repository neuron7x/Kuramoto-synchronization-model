"""Base primitives shared across TradePulse microservices."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Mapping


class ServiceState(str, Enum):
    """Lifecycle states exposed by a microservice."""

    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


@dataclass(slots=True)
class ServiceHealth:
    """Lightweight health report emitted by a microservice."""

    name: str
    state: ServiceState
    healthy: bool
    detail: str | None = None
    metadata: Mapping[str, object] | None = None


class Microservice:
    """Canonical base class encapsulating lifecycle and health reporting."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._state = ServiceState.STOPPED
        self._last_error: str | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> ServiceState:
        return self._state

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start(self) -> None:
        """Mark the service as ready to accept work."""

        self._state = ServiceState.RUNNING
        self._last_error = None

    def stop(self) -> None:
        """Transition the service into an idle state."""

        self._state = ServiceState.STOPPED

    def health(self) -> ServiceHealth:
        """Return a snapshot of the service's current health."""

        metadata = self._health_metadata()
        return ServiceHealth(
            name=self._name,
            state=self._state,
            healthy=self._state is ServiceState.RUNNING and self._last_error is None,
            detail=self._last_error,
            metadata=metadata if metadata else None,
        )

    def _ensure_active(self) -> None:
        if self._state is ServiceState.STOPPED:
            raise RuntimeError(f"Service '{self._name}' is not running")

    def _mark_healthy(self) -> None:
        if self._state is not ServiceState.STOPPED:
            self._state = ServiceState.RUNNING
        self._last_error = None

    def _mark_error(self, error: Exception) -> None:
        self._state = ServiceState.ERROR
        self._last_error = str(error)

    def _health_metadata(self) -> Mapping[str, object] | None:
        """Hook allowing subclasses to attach observability metadata."""

        return None

    @contextmanager
    def lifecycle(self) -> Iterator["Microservice"]:
        """Context manager that starts and stops the service automatically."""

        self.start()
        try:
            yield self
        finally:
            self.stop()
