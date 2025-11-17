"""Component abstraction for architecture integration.

This module defines the core component model used by the Architecture Integrator
to represent and manage system components uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, Protocol, Sequence


class ComponentStatus(str, Enum):
    """Represents the operational status of a component."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class ComponentHealth:
    """Health information for a component."""

    status: ComponentStatus
    healthy: bool
    message: str = ""
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, float] = field(default_factory=dict)

    def is_operational(self) -> bool:
        """Check if component is in an operational state."""
        return self.status in {ComponentStatus.RUNNING, ComponentStatus.DEGRADED}

    def is_failed(self) -> bool:
        """Check if component has failed."""
        return self.status == ComponentStatus.FAILED


@dataclass
class ComponentMetadata:
    """Metadata describing a component."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    configuration: dict[str, Any] = field(default_factory=dict)


class ComponentProtocol(Protocol):
    """Protocol defining the interface that components must implement."""

    def initialize(self) -> None:
        """Initialize the component."""
        ...

    def start(self) -> None:
        """Start the component."""
        ...

    def stop(self) -> None:
        """Stop the component."""
        ...

    def health_check(self) -> ComponentHealth:
        """Check component health."""
        ...


@dataclass
class Component:
    """Wrapper for a component managed by the Architecture Integrator."""

    metadata: ComponentMetadata
    instance: Any
    status: ComponentStatus = ComponentStatus.UNINITIALIZED
    health: ComponentHealth | None = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Lifecycle hooks (optional)
    init_hook: Optional[Callable[[], None]] = None
    start_hook: Optional[Callable[[], None]] = None
    stop_hook: Optional[Callable[[], None]] = None
    health_hook: Optional[Callable[[], ComponentHealth]] = None

    def initialize(self) -> None:
        """Initialize the component using appropriate hook."""
        self.status = ComponentStatus.INITIALIZING
        try:
            if self.init_hook:
                self.init_hook()
            elif hasattr(self.instance, "initialize"):
                self.instance.initialize()
            self.status = ComponentStatus.INITIALIZED
        except Exception as exc:
            self.status = ComponentStatus.FAILED
            raise RuntimeError(
                f"Failed to initialize component {self.metadata.name}: {exc}"
            ) from exc
        finally:
            self.last_updated = datetime.now(timezone.utc)

    def start(self) -> None:
        """Start the component using appropriate hook."""
        if self.status != ComponentStatus.INITIALIZED:
            raise RuntimeError(
                f"Cannot start component {self.metadata.name} in state {self.status}"
            )
        self.status = ComponentStatus.STARTING
        try:
            if self.start_hook:
                self.start_hook()
            elif hasattr(self.instance, "start"):
                self.instance.start()
            self.status = ComponentStatus.RUNNING
        except Exception as exc:
            self.status = ComponentStatus.FAILED
            raise RuntimeError(
                f"Failed to start component {self.metadata.name}: {exc}"
            ) from exc
        finally:
            self.last_updated = datetime.now(timezone.utc)

    def stop(self) -> None:
        """Stop the component using appropriate hook."""
        if self.status not in {ComponentStatus.RUNNING, ComponentStatus.DEGRADED}:
            return
        self.status = ComponentStatus.STOPPING
        try:
            if self.stop_hook:
                self.stop_hook()
            elif hasattr(self.instance, "stop"):
                self.instance.stop()
            self.status = ComponentStatus.STOPPED
        except Exception as exc:
            self.status = ComponentStatus.FAILED
            raise RuntimeError(
                f"Failed to stop component {self.metadata.name}: {exc}"
            ) from exc
        finally:
            self.last_updated = datetime.now(timezone.utc)

    def check_health(self) -> ComponentHealth:
        """Check component health using appropriate hook."""
        try:
            if self.health_hook:
                health = self.health_hook()
            elif hasattr(self.instance, "health_check"):
                health = self.instance.health_check()
            else:
                # Default health based on status
                health = ComponentHealth(
                    status=self.status,
                    healthy=self.status == ComponentStatus.RUNNING,
                    message="No health check implemented",
                )
            self.health = health
            return health
        except Exception as exc:
            error_health = ComponentHealth(
                status=ComponentStatus.FAILED,
                healthy=False,
                message=f"Health check failed: {exc}",
            )
            self.health = error_health
            return error_health

    def get_dependencies(self) -> Sequence[str]:
        """Return list of component dependencies."""
        return self.metadata.dependencies

    def get_provides(self) -> Sequence[str]:
        """Return list of capabilities this component provides."""
        return self.metadata.provides
