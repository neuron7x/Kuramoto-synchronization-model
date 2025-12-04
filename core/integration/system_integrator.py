"""Unified System Integrator for TradePulse.

This module provides the SystemIntegrator class that unifies all TradePulse
modules and services into a single, cohesive system. It combines:

- Architecture Integrator for component lifecycle and coordination
- TradePulse Orchestrator for service orchestration
- Service Registry for microservices management
- Agent Coordinator for agent coordination and task management

The SystemIntegrator serves as the primary entry point for bootstrapping
and managing the entire TradePulse platform.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence

from core.architecture_integrator import (
    ArchitectureIntegrator,
    ComponentHealth,
    ComponentStatus,
    ValidationResult,
)
from core.integration.adapters import (
    AgentCoordinatorAdapter,
    ServiceRegistryAdapter,
)

if TYPE_CHECKING:
    from application.microservices.registry import ServiceRegistry
    from application.system import TradePulseSystem
    from application.system_orchestrator import TradePulseOrchestrator
    from modules.agent_coordinator import AgentCoordinator

logger = logging.getLogger(__name__)


@dataclass
class IntegrationConfig:
    """Configuration for the unified system integration.

    Attributes:
        enable_orchestrator: Whether to integrate the TradePulse orchestrator
        enable_agent_coordinator: Whether to integrate the agent coordinator
        enable_fractal_regulator: Whether to enable the fractal regulator
        auto_start_services: Whether to automatically start services on bootstrap
        health_check_interval: Interval in seconds for periodic health checks
        component_tags: Default tags to apply to all components
    """

    enable_orchestrator: bool = True
    enable_agent_coordinator: bool = True
    enable_fractal_regulator: bool = False
    auto_start_services: bool = True
    health_check_interval: float = 30.0
    component_tags: List[str] = field(default_factory=lambda: ["tradepulse"])
    regulator_config: Dict[str, float] = field(default_factory=dict)


class SystemIntegrator:
    """Unified system integrator for TradePulse.

    Combines all TradePulse modules and services into a single, cohesive
    system with unified lifecycle management, health monitoring, and
    coordination capabilities.

    The SystemIntegrator acts as the central orchestration point for:
    - Component registration and discovery
    - Service lifecycle coordination
    - Agent task coordination
    - Health aggregation across all subsystems
    - Architecture validation and compliance

    Example:
        >>> config = IntegrationConfig(auto_start_services=True)
        >>> integrator = SystemIntegrator(config)
        >>> integrator.register_system(system)
        >>> integrator.register_orchestrator(orchestrator)
        >>> integrator.register_agent_coordinator(coordinator)
        >>> integrator.bootstrap()
        >>> integrator.start_all()
        >>> health = integrator.get_unified_health()
    """

    def __init__(self, config: IntegrationConfig | None = None) -> None:
        """Initialize the unified system integrator.

        Args:
            config: Integration configuration settings
        """
        self._config = config or IntegrationConfig()
        self._arch_integrator = ArchitectureIntegrator()

        # Subsystem references
        self._system: Optional[TradePulseSystem] = None
        self._orchestrator: Optional[TradePulseOrchestrator] = None
        self._service_registry: Optional[ServiceRegistry] = None
        self._agent_coordinator: Optional[AgentCoordinator] = None

        # Adapters for subsystems
        self._service_registry_adapter: Optional[ServiceRegistryAdapter] = None
        self._agent_coordinator_adapter: Optional[AgentCoordinatorAdapter] = None

        # State tracking
        self._bootstrapped = False
        self._started = False

        # Event handlers
        self._event_handlers: Dict[str, List[Callable[..., None]]] = {}

    @property
    def architecture_integrator(self) -> ArchitectureIntegrator:
        """Access the underlying architecture integrator."""
        return self._arch_integrator

    @property
    def config(self) -> IntegrationConfig:
        """Access the integration configuration."""
        return self._config

    @property
    def is_bootstrapped(self) -> bool:
        """Check if the system has been bootstrapped."""
        return self._bootstrapped

    @property
    def is_started(self) -> bool:
        """Check if the system has been started."""
        return self._started

    # ------------------------------------------------------------------
    # Subsystem Registration
    # ------------------------------------------------------------------

    def register_system(
        self,
        system: TradePulseSystem,
        *,
        name: str = "tradepulse_system",
        description: str = "Core TradePulse system",
    ) -> None:
        """Register the core TradePulse system.

        Args:
            system: TradePulseSystem instance
            name: Component name for registration
            description: Component description
        """
        from core.architecture_integrator.adapters import TradePulseSystemAdapter

        self._system = system
        adapter = TradePulseSystemAdapter(system)

        self._arch_integrator.register_component(
            name=name,
            instance=adapter,
            version="1.0.0",
            description=description,
            tags=self._config.component_tags + ["core", "system"],
            provides=["data_ingestion", "feature_pipeline", "signal_generation"],
            init_hook=adapter.initialize,
            start_hook=adapter.start,
            stop_hook=adapter.stop,
            health_hook=adapter.health_check,
        )
        logger.info(f"Registered TradePulse system as '{name}'")
        self._emit_event("system_registered", name=name)

    def register_orchestrator(
        self,
        orchestrator: TradePulseOrchestrator,
        *,
        name: str = "tradepulse_orchestrator",
        description: str = "TradePulse service orchestrator",
    ) -> None:
        """Register the TradePulse orchestrator.

        Args:
            orchestrator: TradePulseOrchestrator instance
            name: Component name for registration
            description: Component description
        """
        from core.architecture_integrator.adapters import TradePulseOrchestratorAdapter

        self._orchestrator = orchestrator
        adapter = TradePulseOrchestratorAdapter(orchestrator)

        # Also register the service registry from the orchestrator
        self._service_registry = orchestrator.services

        self._arch_integrator.register_component(
            name=name,
            instance=adapter,
            version="1.0.0",
            description=description,
            tags=self._config.component_tags + ["orchestrator"],
            dependencies=["tradepulse_system"] if self._system else [],
            provides=["orchestration", "backtest", "execution"],
            init_hook=adapter.initialize,
            start_hook=adapter.start,
            stop_hook=adapter.stop,
            health_hook=adapter.health_check,
        )
        logger.info(f"Registered TradePulse orchestrator as '{name}'")
        self._emit_event("orchestrator_registered", name=name)

    def register_service_registry(
        self,
        registry: ServiceRegistry,
        *,
        name: str = "service_registry",
        description: str = "Microservices registry",
    ) -> None:
        """Register the service registry.

        Args:
            registry: ServiceRegistry instance
            name: Component name for registration
            description: Component description
        """
        self._service_registry = registry
        self._service_registry_adapter = ServiceRegistryAdapter(registry)

        self._arch_integrator.register_component(
            name=name,
            instance=self._service_registry_adapter,
            version="1.0.0",
            description=description,
            tags=self._config.component_tags + ["services", "registry"],
            provides=["market_data", "backtesting", "execution"],
            init_hook=self._service_registry_adapter.initialize,
            start_hook=self._service_registry_adapter.start,
            stop_hook=self._service_registry_adapter.stop,
            health_hook=self._service_registry_adapter.health_check,
        )
        logger.info(f"Registered service registry as '{name}'")
        self._emit_event("service_registry_registered", name=name)

    def register_agent_coordinator(
        self,
        coordinator: AgentCoordinator,
        *,
        name: str = "agent_coordinator",
        description: str = "Agent coordination and task management",
    ) -> None:
        """Register the agent coordinator.

        Args:
            coordinator: AgentCoordinator instance
            name: Component name for registration
            description: Component description
        """
        self._agent_coordinator = coordinator
        self._agent_coordinator_adapter = AgentCoordinatorAdapter(coordinator)

        self._arch_integrator.register_component(
            name=name,
            instance=self._agent_coordinator_adapter,
            version="1.0.0",
            description=description,
            tags=self._config.component_tags + ["agents", "coordinator"],
            provides=["agent_coordination", "task_management"],
            init_hook=self._agent_coordinator_adapter.initialize,
            start_hook=self._agent_coordinator_adapter.start,
            stop_hook=self._agent_coordinator_adapter.stop,
            health_hook=self._agent_coordinator_adapter.health_check,
        )
        logger.info(f"Registered agent coordinator as '{name}'")
        self._emit_event("agent_coordinator_registered", name=name)

    def register_custom_component(
        self,
        name: str,
        instance: Any,
        *,
        version: str = "1.0.0",
        description: str = "",
        tags: List[str] | None = None,
        dependencies: List[str] | None = None,
        provides: List[str] | None = None,
        init_hook: Callable[[], None] | None = None,
        start_hook: Callable[[], None] | None = None,
        stop_hook: Callable[[], None] | None = None,
        health_hook: Callable[[], ComponentHealth] | None = None,
    ) -> None:
        """Register a custom component with the system.

        Args:
            name: Unique component identifier
            instance: The component instance
            version: Component version
            description: Human-readable description
            tags: List of tags for categorization
            dependencies: List of component names this depends on
            provides: List of capabilities this component provides
            init_hook: Optional initialization callback
            start_hook: Optional startup callback
            stop_hook: Optional shutdown callback
            health_hook: Optional health check callback
        """
        combined_tags = (tags or []) + self._config.component_tags
        self._arch_integrator.register_component(
            name=name,
            instance=instance,
            version=version,
            description=description,
            tags=combined_tags,
            dependencies=dependencies,
            provides=provides,
            init_hook=init_hook,
            start_hook=start_hook,
            stop_hook=stop_hook,
            health_hook=health_hook,
        )
        logger.info(f"Registered custom component: {name}")
        self._emit_event("custom_component_registered", name=name)

    # ------------------------------------------------------------------
    # Lifecycle Management
    # ------------------------------------------------------------------

    def bootstrap(self) -> None:
        """Bootstrap the unified system.

        Initializes all registered components in dependency order.

        Raises:
            RuntimeError: If bootstrap fails
        """
        if self._bootstrapped:
            logger.warning("System already bootstrapped")
            return

        logger.info("Bootstrapping unified TradePulse system...")
        self._emit_event("bootstrap_started")

        try:
            # Validate architecture before initialization
            validation = self._arch_integrator.validate_architecture()
            if not validation.passed:
                blocking = validation.get_blocking_issues()
                if blocking:
                    error_msgs = [issue.message for issue in blocking]
                    raise RuntimeError(
                        f"Architecture validation failed: {'; '.join(error_msgs)}"
                    )

            # Initialize all components
            initialized = self._arch_integrator.initialize_all()
            logger.info(f"Initialized {len(initialized)} components")

            self._bootstrapped = True
            self._emit_event("bootstrap_completed", count=len(initialized))

            # Auto-start if configured
            if self._config.auto_start_services:
                self.start_all()

        except Exception as exc:
            logger.error(f"Bootstrap failed: {exc}")
            self._emit_event("bootstrap_failed", error=str(exc))
            raise

    def start_all(self) -> List[str]:
        """Start all components in the system.

        Returns:
            List of successfully started component names

        Raises:
            RuntimeError: If not bootstrapped or startup fails
        """
        if not self._bootstrapped:
            raise RuntimeError("System must be bootstrapped before starting")

        if self._started:
            logger.warning("System already started")
            return []

        logger.info("Starting unified TradePulse system...")
        self._emit_event("startup_started")

        try:
            started = self._arch_integrator.start_all()
            self._started = True
            logger.info(f"Started {len(started)} components")
            self._emit_event("startup_completed", count=len(started))
            return started
        except Exception as exc:
            logger.error(f"Startup failed: {exc}")
            self._emit_event("startup_failed", error=str(exc))
            raise

    def stop_all(self) -> List[str]:
        """Stop all components in the system.

        Returns:
            List of successfully stopped component names
        """
        if not self._started:
            logger.warning("System not started")
            return []

        logger.info("Stopping unified TradePulse system...")
        self._emit_event("shutdown_started")

        stopped = self._arch_integrator.stop_all()
        self._started = False
        logger.info(f"Stopped {len(stopped)} components")
        self._emit_event("shutdown_completed", count=len(stopped))
        return stopped

    def restart(self) -> None:
        """Restart the entire system.

        Stops all components and starts them again in dependency order.
        """
        logger.info("Restarting unified TradePulse system...")
        self._emit_event("restart_started")

        if self._started:
            self.stop_all()

        self.start_all()
        self._emit_event("restart_completed")

    # ------------------------------------------------------------------
    # Health Monitoring
    # ------------------------------------------------------------------

    def get_unified_health(self) -> Dict[str, Any]:
        """Get unified health status from all subsystems.

        Returns:
            Dictionary with comprehensive health information
        """
        health_map = self._arch_integrator.aggregate_health()

        # Aggregate status
        total_components = len(health_map)
        healthy_components = sum(1 for h in health_map.values() if h.healthy)
        degraded_components = sum(
            1 for h in health_map.values()
            if h.status == ComponentStatus.DEGRADED
        )
        failed_components = sum(
            1 for h in health_map.values()
            if h.status == ComponentStatus.FAILED
        )

        # Calculate overall health score (0-100)
        if total_components == 0:
            health_score = 100.0
        else:
            health_score = (healthy_components / total_components) * 100
            health_score -= (degraded_components / total_components) * 25
            health_score -= (failed_components / total_components) * 50
            health_score = max(0.0, min(100.0, health_score))

        # Determine overall status
        if failed_components > 0:
            overall_status = "critical"
        elif degraded_components > 0:
            overall_status = "degraded"
        elif healthy_components == total_components:
            overall_status = "healthy"
        else:
            overall_status = "unknown"

        return {
            "overall_status": overall_status,
            "health_score": health_score,
            "is_bootstrapped": self._bootstrapped,
            "is_started": self._started,
            "components": {
                "total": total_components,
                "healthy": healthy_components,
                "degraded": degraded_components,
                "failed": failed_components,
            },
            "component_health": {
                name: {
                    "status": h.status.value,
                    "healthy": h.healthy,
                    "message": h.message,
                    "metrics": h.metrics,
                }
                for name, h in health_map.items()
            },
        }

    def is_system_healthy(self) -> bool:
        """Check if the entire system is healthy.

        Returns:
            True if all components are healthy, False otherwise
        """
        return self._arch_integrator.is_system_healthy()

    def check_component_health(self, name: str) -> ComponentHealth:
        """Check health of a specific component.

        Args:
            name: Component name

        Returns:
            ComponentHealth for the component

        Raises:
            KeyError: If component not found
        """
        return self._arch_integrator.check_component_health(name)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_architecture(self) -> ValidationResult:
        """Validate architectural constraints and compliance.

        Returns:
            ValidationResult with all issues found
        """
        return self._arch_integrator.validate_architecture()

    # ------------------------------------------------------------------
    # Subsystem Access
    # ------------------------------------------------------------------

    @property
    def system(self) -> Optional[TradePulseSystem]:
        """Access the registered TradePulse system."""
        return self._system

    @property
    def orchestrator(self) -> Optional[TradePulseOrchestrator]:
        """Access the registered orchestrator."""
        return self._orchestrator

    @property
    def service_registry(self) -> Optional[ServiceRegistry]:
        """Access the registered service registry."""
        return self._service_registry

    @property
    def agent_coordinator(self) -> Optional[AgentCoordinator]:
        """Access the registered agent coordinator."""
        return self._agent_coordinator

    # ------------------------------------------------------------------
    # Component Information
    # ------------------------------------------------------------------

    def list_components(self) -> List[str]:
        """List all registered component names.

        Returns:
            List of component names
        """
        return [c.metadata.name for c in self._arch_integrator.list_components()]

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Get the component dependency graph.

        Returns:
            Dictionary mapping component names to their dependencies
        """
        return self._arch_integrator.get_dependency_graph()

    def get_initialization_order(self) -> Sequence[str]:
        """Get the calculated initialization order.

        Returns:
            List of component names in initialization order
        """
        return self._arch_integrator.get_initialization_order()

    def get_status_summary(self) -> Dict[str, int]:
        """Get a summary of component statuses.

        Returns:
            Dictionary mapping status names to counts
        """
        return self._arch_integrator.get_status_summary()

    # ------------------------------------------------------------------
    # Event System
    # ------------------------------------------------------------------

    def on(self, event_name: str, handler: Callable[..., None]) -> None:
        """Register an event handler.

        Args:
            event_name: Name of the event to listen for
            handler: Callback function to invoke on event
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)

        # Also register with architecture integrator
        self._arch_integrator.on(event_name, handler)

    def _emit_event(self, event_name: str, **kwargs: Any) -> None:
        """Emit an event to registered handlers.

        Args:
            event_name: Name of the event
            **kwargs: Event data to pass to handlers
        """
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception as exc:
                logger.error(f"Event handler failed for {event_name}: {exc}")


class SystemIntegratorBuilder:
    """Builder for creating a configured SystemIntegrator.

    Provides a fluent API for constructing and configuring the
    unified system integrator with various subsystems.

    Example:
        >>> builder = SystemIntegratorBuilder()
        >>> integrator = (
        ...     builder
        ...     .with_system(system)
        ...     .with_orchestrator(orchestrator)
        ...     .with_agent_coordinator(coordinator)
        ...     .with_auto_start(True)
        ...     .build()
        ... )
    """

    def __init__(self) -> None:
        """Initialize the builder with default configuration."""
        self._config = IntegrationConfig()
        self._system: Optional[TradePulseSystem] = None
        self._orchestrator: Optional[TradePulseOrchestrator] = None
        self._service_registry: Optional[ServiceRegistry] = None
        self._agent_coordinator: Optional[AgentCoordinator] = None
        self._custom_components: List[Dict[str, Any]] = []

    def with_config(self, config: IntegrationConfig) -> SystemIntegratorBuilder:
        """Set the integration configuration.

        Args:
            config: Integration configuration

        Returns:
            Self for method chaining
        """
        self._config = config
        return self

    def with_system(self, system: TradePulseSystem) -> SystemIntegratorBuilder:
        """Set the TradePulse system.

        Args:
            system: TradePulseSystem instance

        Returns:
            Self for method chaining
        """
        self._system = system
        return self

    def with_orchestrator(
        self, orchestrator: TradePulseOrchestrator
    ) -> SystemIntegratorBuilder:
        """Set the TradePulse orchestrator.

        Args:
            orchestrator: TradePulseOrchestrator instance

        Returns:
            Self for method chaining
        """
        self._orchestrator = orchestrator
        return self

    def with_service_registry(
        self, registry: ServiceRegistry
    ) -> SystemIntegratorBuilder:
        """Set the service registry.

        Args:
            registry: ServiceRegistry instance

        Returns:
            Self for method chaining
        """
        self._service_registry = registry
        return self

    def with_agent_coordinator(
        self, coordinator: AgentCoordinator
    ) -> SystemIntegratorBuilder:
        """Set the agent coordinator.

        Args:
            coordinator: AgentCoordinator instance

        Returns:
            Self for method chaining
        """
        self._agent_coordinator = coordinator
        return self

    def with_auto_start(self, enabled: bool) -> SystemIntegratorBuilder:
        """Set whether to auto-start services on bootstrap.

        Args:
            enabled: Whether to enable auto-start

        Returns:
            Self for method chaining
        """
        self._config.auto_start_services = enabled
        return self

    def with_fractal_regulator(
        self, enabled: bool, config: Dict[str, float] | None = None
    ) -> SystemIntegratorBuilder:
        """Set whether to enable the fractal regulator.

        Args:
            enabled: Whether to enable the fractal regulator
            config: Optional regulator configuration

        Returns:
            Self for method chaining
        """
        self._config.enable_fractal_regulator = enabled
        if config:
            self._config.regulator_config = config
        return self

    def add_custom_component(
        self,
        name: str,
        instance: Any,
        **kwargs: Any,
    ) -> SystemIntegratorBuilder:
        """Add a custom component to the system.

        Args:
            name: Component name
            instance: Component instance
            **kwargs: Additional component configuration

        Returns:
            Self for method chaining
        """
        self._custom_components.append({
            "name": name,
            "instance": instance,
            **kwargs,
        })
        return self

    def build(self) -> SystemIntegrator:
        """Build and return the configured SystemIntegrator.

        Returns:
            Configured SystemIntegrator instance
        """
        integrator = SystemIntegrator(self._config)

        # Register subsystems
        if self._system is not None:
            integrator.register_system(self._system)

        if self._orchestrator is not None:
            integrator.register_orchestrator(self._orchestrator)
        elif self._service_registry is not None:
            integrator.register_service_registry(self._service_registry)

        if self._agent_coordinator is not None:
            integrator.register_agent_coordinator(self._agent_coordinator)

        # Register custom components
        for component in self._custom_components:
            name = component.pop("name")
            instance = component.pop("instance")
            integrator.register_custom_component(name, instance, **component)

        return integrator
