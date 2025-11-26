"""Adapters for integrating with existing TradePulse orchestration systems.

This module provides adapter classes that bridge the Architecture Integrator
with existing orchestration components like TradePulseSystem and
TradePulseOrchestrator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.architecture_integrator.component import ComponentHealth, ComponentStatus

if TYPE_CHECKING:
    from application.system import TradePulseSystem
    from application.system_orchestrator import TradePulseOrchestrator


class TradePulseSystemAdapter:
    """Adapter for TradePulseSystem to work with Architecture Integrator."""

    def __init__(self, system: TradePulseSystem) -> None:
        """Initialize adapter with a TradePulseSystem instance.

        Args:
            system: TradePulseSystem instance to adapt
        """
        self._system = system
        self._initialized = False
        self._started = False

    def initialize(self) -> None:
        """Initialize the TradePulse system."""
        # TradePulseSystem is initialized on construction
        self._initialized = True

    def start(self) -> None:
        """Start the TradePulse system services."""
        # Ensure live loop is initialized if needed
        if hasattr(self._system, "ensure_live_loop"):
            self._system.ensure_live_loop()
        self._started = True

    def stop(self) -> None:
        """Stop the TradePulse system services."""
        # Stop live loop if it exists
        if hasattr(self._system, "live_loop") and self._system.live_loop:
            # Live loop cleanup would go here
            pass
        self._started = False

    def health_check(self) -> ComponentHealth:
        """Check health of the TradePulse system.

        Returns:
            ComponentHealth with system status
        """
        if not self._initialized:
            return ComponentHealth(
                status=ComponentStatus.UNINITIALIZED,
                healthy=False,
                message="System not initialized",
            )

        if not self._started:
            return ComponentHealth(
                status=ComponentStatus.INITIALIZED,
                healthy=True,
                message="System initialized but not started",
            )

        # Check for recent errors
        errors = []
        if self._system.last_ingestion_error:
            errors.append(f"Ingestion: {self._system.last_ingestion_error}")
        if self._system.last_signal_error:
            errors.append(f"Signal: {self._system.last_signal_error}")
        if self._system.last_execution_error:
            errors.append(f"Execution: {self._system.last_execution_error}")

        if errors:
            return ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message="; ".join(errors),
            )

        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="System operational",
        )

    @property
    def system(self) -> TradePulseSystem:
        """Access the underlying TradePulseSystem."""
        return self._system


class TradePulseOrchestratorAdapter:
    """Adapter for TradePulseOrchestrator to work with Architecture Integrator."""

    def __init__(self, orchestrator: TradePulseOrchestrator) -> None:
        """Initialize adapter with a TradePulseOrchestrator instance.

        Args:
            orchestrator: TradePulseOrchestrator instance to adapt
        """
        self._orchestrator = orchestrator
        self._initialized = False
        self._started = False

    def initialize(self) -> None:
        """Initialize the orchestrator."""
        # Orchestrator is initialized on construction
        self._initialized = True

    def start(self) -> None:
        """Start orchestrator services."""
        # Ensure live loop is ready
        self._orchestrator.ensure_live_loop()
        self._started = True

    def stop(self) -> None:
        """Stop orchestrator services."""
        # Services are managed by ServiceRegistry
        self._started = False

    def health_check(self) -> ComponentHealth:
        """Check health of the orchestrator.

        Returns:
            ComponentHealth with orchestrator status
        """
        if not self._initialized:
            return ComponentHealth(
                status=ComponentStatus.UNINITIALIZED,
                healthy=False,
                message="Orchestrator not initialized",
            )

        if not self._started:
            return ComponentHealth(
                status=ComponentStatus.INITIALIZED,
                healthy=True,
                message="Orchestrator initialized but not started",
            )

        # Check if services are running
        if hasattr(self._orchestrator, "services"):
            services = self._orchestrator.services
            # ServiceRegistry should be started
            if hasattr(services, "_started") and not services._started:
                return ComponentHealth(
                    status=ComponentStatus.DEGRADED,
                    healthy=False,
                    message="Services not started",
                )

        # Check fractal regulator if enabled
        if self._orchestrator.fractal_regulator:
            if self._orchestrator.is_system_in_crisis():
                metrics = self._orchestrator.get_system_health_metrics()
                return ComponentHealth(
                    status=ComponentStatus.DEGRADED,
                    healthy=False,
                    message=f"System in crisis (CSI: {metrics.csi if metrics else 'N/A'})",
                    metrics={"csi": metrics.csi} if metrics else {},
                )

        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="Orchestrator operational",
        )

    @property
    def orchestrator(self) -> TradePulseOrchestrator:
        """Access the underlying TradePulseOrchestrator."""
        return self._orchestrator


def create_system_component_adapter(
    system: TradePulseSystem,
) -> TradePulseSystemAdapter:
    """Create an adapter for TradePulseSystem.

    Args:
        system: TradePulseSystem instance to adapt

    Returns:
        Adapter that implements component protocol
    """
    return TradePulseSystemAdapter(system)


def create_orchestrator_component_adapter(
    orchestrator: TradePulseOrchestrator,
) -> TradePulseOrchestratorAdapter:
    """Create an adapter for TradePulseOrchestrator.

    Args:
        orchestrator: TradePulseOrchestrator instance to adapt

    Returns:
        Adapter that implements component protocol
    """
    return TradePulseOrchestratorAdapter(orchestrator)
