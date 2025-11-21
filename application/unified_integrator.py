"""Unified System Integrator for TradePulse.

This module provides a unified integration layer that connects all TradePulse
components (modules, microservices, core components) into a cohesive system
using the ArchitectureIntegrator pattern.

Features:
- Automatic component registration with proper dependencies
- Lifecycle management for all system components
- Health monitoring and system-wide health checks
- Dependency validation and initialization ordering
- Event-driven component coordination
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from application.microservices.registry import ServiceRegistry
from application.system import TradePulseSystem, TradePulseSystemConfig
from core.architecture_integrator import (
    ArchitectureIntegrator,
    ComponentHealth,
    ComponentStatus,
)
from modules import (
    AdaptiveRiskManager,
    AgentCoordinator,
    DynamicPositionSizer,
    MarketRegimeAnalyzer,
)

logger = logging.getLogger(__name__)


@dataclass
class UnifiedIntegratorConfig:
    """Configuration for the unified system integrator."""

    enable_risk_manager: bool = True
    enable_regime_analyzer: bool = True
    enable_position_sizer: bool = True
    enable_agent_coordinator: bool = True
    enable_fractal_regulator: bool = False

    # Module configurations
    risk_manager_config: Mapping[str, Any] | None = None
    regime_analyzer_config: Mapping[str, Any] | None = None
    position_sizer_config: Mapping[str, Any] | None = None
    agent_coordinator_config: Mapping[str, Any] | None = None
    fractal_regulator_config: Mapping[str, Any] | None = None


class UnifiedSystemIntegrator:
    """Unified integration layer for all TradePulse components.
    
    This class orchestrates the integration of:
    - Microservices (market data, backtesting, execution)
    - Modules (risk manager, regime analyzer, position sizer, agent coordinator)
    - Core components (neuro controllers, indicators, strategies)
    
    Example:
        >>> config = UnifiedIntegratorConfig(enable_all=True)
        >>> integrator = UnifiedSystemIntegrator(tradepulse_system, config)
        >>> integrator.initialize()
        >>> integrator.start()
        >>> health = integrator.get_system_health()
        >>> integrator.stop()
    """

    def __init__(
        self,
        system: TradePulseSystem,
        config: UnifiedIntegratorConfig | None = None,
    ) -> None:
        """Initialize the unified system integrator.
        
        Args:
            system: The TradePulseSystem instance to integrate
            config: Configuration for component enablement and settings
        """
        self._system = system
        self._config = config or UnifiedIntegratorConfig()
        self._integrator = ArchitectureIntegrator()
        self._service_registry: ServiceRegistry | None = None
        self._components: dict[str, Any] = {}

        # Register all components
        self._register_all_components()

    def _register_all_components(self) -> None:
        """Register all system components with the integrator."""
        # Register core services first
        self._register_service_registry()

        # Register modules with dependencies
        if self._config.enable_risk_manager:
            self._register_risk_manager()

        if self._config.enable_regime_analyzer:
            self._register_regime_analyzer()

        if self._config.enable_position_sizer:
            self._register_position_sizer()

        if self._config.enable_agent_coordinator:
            self._register_agent_coordinator()

        logger.info("All components registered successfully")

    def _register_service_registry(self) -> None:
        """Register the microservices registry."""
        service_registry = ServiceRegistry.from_system(self._system)
        self._service_registry = service_registry

        # Register market data service
        self._integrator.register_component(
            name="market_data_service",
            instance=service_registry.market_data,
            version="1.0.0",
            description="Market data ingestion and management service",
            tags=["service", "data", "core"],
            provides=["market_data"],
            init_hook=None,  # Already initialized
            start_hook=lambda: service_registry.market_data.start()
            if service_registry.market_data.state.name == "STOPPED"
            else None,
            stop_hook=lambda: service_registry.market_data.stop(),
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING
                if service_registry.market_data.state.name == "RUNNING"
                else ComponentStatus.STOPPED,
                healthy=service_registry.market_data.state.name == "RUNNING",
                message=f"Market data service: {service_registry.market_data.state.name}",
            ),
        )

        # Register backtesting service
        self._integrator.register_component(
            name="backtesting_service",
            instance=service_registry.backtesting,
            version="1.0.0",
            description="Backtesting and simulation service",
            tags=["service", "testing", "core"],
            dependencies=["market_data_service"],
            provides=["backtesting"],
            start_hook=lambda: service_registry.backtesting.start()
            if service_registry.backtesting.state.name == "STOPPED"
            else None,
            stop_hook=lambda: service_registry.backtesting.stop(),
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING
                if service_registry.backtesting.state.name == "RUNNING"
                else ComponentStatus.STOPPED,
                healthy=service_registry.backtesting.state.name == "RUNNING",
                message=f"Backtesting service: {service_registry.backtesting.state.name}",
            ),
        )

        # Register execution service
        self._integrator.register_component(
            name="execution_service",
            instance=service_registry.execution,
            version="1.0.0",
            description="Order execution and management service",
            tags=["service", "execution", "core"],
            dependencies=["market_data_service"],
            provides=["execution"],
            start_hook=lambda: service_registry.execution.start()
            if service_registry.execution.state.name == "STOPPED"
            else None,
            stop_hook=lambda: service_registry.execution.stop(),
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING
                if service_registry.execution.state.name == "RUNNING"
                else ComponentStatus.STOPPED,
                healthy=service_registry.execution.state.name == "RUNNING",
                message=f"Execution service: {service_registry.execution.state.name}",
            ),
        )

        self._components["service_registry"] = service_registry
        logger.info("Service registry and microservices registered")

    def _register_risk_manager(self) -> None:
        """Register the adaptive risk manager module."""
        config = self._config.risk_manager_config or {}
        risk_manager = AdaptiveRiskManager(**config)

        self._integrator.register_component(
            name="adaptive_risk_manager",
            instance=risk_manager,
            version="1.0.0",
            description="Adaptive risk management with TACL integration",
            tags=["module", "risk", "adaptive"],
            dependencies=["market_data_service", "execution_service"],
            provides=["risk_management"],
            init_hook=None,  # No initialization needed
            start_hook=None,  # Stateless module
            stop_hook=None,
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
                message="Risk manager operational",
            ),
        )

        self._components["risk_manager"] = risk_manager
        logger.info("Adaptive risk manager registered")

    def _register_regime_analyzer(self) -> None:
        """Register the market regime analyzer module."""
        config = self._config.regime_analyzer_config or {}
        regime_analyzer = MarketRegimeAnalyzer(**config)

        self._integrator.register_component(
            name="market_regime_analyzer",
            instance=regime_analyzer,
            version="1.0.0",
            description="Market regime detection and classification",
            tags=["module", "analytics", "regime"],
            dependencies=["market_data_service"],
            provides=["regime_analysis"],
            init_hook=None,
            start_hook=None,
            stop_hook=None,
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
                message="Regime analyzer operational",
            ),
        )

        self._components["regime_analyzer"] = regime_analyzer
        logger.info("Market regime analyzer registered")

    def _register_position_sizer(self) -> None:
        """Register the dynamic position sizer module."""
        config = self._config.position_sizer_config or {}
        position_sizer = DynamicPositionSizer(**config)

        self._integrator.register_component(
            name="dynamic_position_sizer",
            instance=position_sizer,
            version="1.0.0",
            description="Dynamic position sizing with Kelly criterion",
            tags=["module", "sizing", "risk"],
            dependencies=["adaptive_risk_manager", "market_regime_analyzer"],
            provides=["position_sizing"],
            init_hook=None,
            start_hook=None,
            stop_hook=None,
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
                message="Position sizer operational",
            ),
        )

        self._components["position_sizer"] = position_sizer
        logger.info("Dynamic position sizer registered")

    def _register_agent_coordinator(self) -> None:
        """Register the agent coordinator module."""
        config = self._config.agent_coordinator_config or {}
        agent_coordinator = AgentCoordinator(**config)

        self._integrator.register_component(
            name="agent_coordinator",
            instance=agent_coordinator,
            version="1.0.0",
            description="Multi-agent coordination and task management",
            tags=["module", "coordination", "agents"],
            dependencies=[
                "adaptive_risk_manager",
                "market_regime_analyzer",
                "dynamic_position_sizer",
            ],
            provides=["agent_coordination"],
            init_hook=None,
            start_hook=None,
            stop_hook=None,
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
                message=f"Agent coordinator operational with {len(agent_coordinator.agents)} agents",
            ),
        )

        self._components["agent_coordinator"] = agent_coordinator
        logger.info("Agent coordinator registered")

    def initialize(self) -> None:
        """Initialize all registered components in dependency order."""
        logger.info("Initializing unified system...")
        order = self._integrator.get_initialization_order()
        logger.info(f"Initialization order: {order}")
        self._integrator.initialize_all()
        logger.info("All components initialized")

    def start(self) -> None:
        """Start all registered components in dependency order."""
        logger.info("Starting unified system...")
        self._integrator.start_all()
        logger.info("All components started")

    def stop(self) -> None:
        """Stop all registered components in reverse dependency order."""
        logger.info("Stopping unified system...")
        self._integrator.stop_all()
        logger.info("All components stopped")

    def get_system_health(self) -> dict[str, ComponentHealth]:
        """Get health status of all components.
        
        Returns:
            Dictionary mapping component names to their health status
        """
        return self._integrator.aggregate_health()

    def is_system_healthy(self) -> bool:
        """Check if the entire system is healthy.
        
        Returns:
            True if all components are healthy, False otherwise
        """
        return self._integrator.is_system_healthy()

    def validate_architecture(self) -> bool:
        """Validate the system architecture.
        
        Returns:
            True if architecture validation passes, False otherwise
        """
        validation = self._integrator.validate_architecture()
        if not validation.passed:
            logger.error("Architecture validation failed:")
            for issue in validation.issues:
                logger.error(f"  [{issue.severity.value}] {issue.message}")
        return validation.passed

    def get_component(self, name: str) -> Any:
        """Get a registered component by name.
        
        Args:
            name: The component name
            
        Returns:
            The component instance
            
        Raises:
            KeyError: If component not found
        """
        if name in self._components:
            return self._components[name]

        # Try to get from integrator registry
        metadata = self._integrator.registry.get_metadata(name)
        if metadata:
            return metadata.instance

        raise KeyError(f"Component not found: {name}")

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """Get the dependency graph of all components.
        
        Returns:
            Dictionary mapping component names to their dependencies
        """
        return self._integrator.get_dependency_graph()

    @property
    def integrator(self) -> ArchitectureIntegrator:
        """Get the underlying architecture integrator."""
        return self._integrator

    @property
    def service_registry(self) -> ServiceRegistry:
        """Get the service registry."""
        if self._service_registry is None:
            raise RuntimeError("Service registry not initialized")
        return self._service_registry

    @property
    def components(self) -> dict[str, Any]:
        """Get all registered components."""
        return self._components.copy()


def build_unified_system(
    system_config: TradePulseSystemConfig | None = None,
    integrator_config: UnifiedIntegratorConfig | None = None,
) -> UnifiedSystemIntegrator:
    """Build a complete unified TradePulse system.
    
    This is a convenience function that creates both the TradePulseSystem
    and UnifiedSystemIntegrator with sensible defaults.
    
    Args:
        system_config: Configuration for the TradePulseSystem
        integrator_config: Configuration for the UnifiedSystemIntegrator
        
    Returns:
        A configured UnifiedSystemIntegrator ready to use
        
    Example:
        >>> integrator = build_unified_system()
        >>> integrator.initialize()
        >>> integrator.start()
        >>> # Use the system
        >>> integrator.stop()
    """
    from application.system_orchestrator import build_tradepulse_system

    # Build base system if not provided
    if system_config is None:
        system = build_tradepulse_system()
    else:
        system = TradePulseSystem(system_config)

    # Build unified integrator
    integrator = UnifiedSystemIntegrator(system, integrator_config)

    return integrator


__all__ = [
    "UnifiedSystemIntegrator",
    "UnifiedIntegratorConfig",
    "build_unified_system",
]
