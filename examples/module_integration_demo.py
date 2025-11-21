"""Demonstration of Module Integration using ArchitectureIntegrator.

This example shows how to integrate TradePulse modules (risk manager,
regime analyzer, position sizer, agent coordinator) into a unified system
using the ArchitectureIntegrator pattern.

This is a simplified version that doesn't require the full application stack,
demonstrating the integration concept.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core.architecture_integrator import (
    ArchitectureIntegrator,
    ComponentHealth,
    ComponentStatus,
)


# Mock module classes for demonstration
@dataclass
class MockMarketDataService:
    """Mock market data service."""

    name: str = "market_data"
    started: bool = False

    def initialize(self):
        """Initialize service."""
        print(f"{self.name}: Initializing...")

    def start(self):
        """Start service."""
        print(f"{self.name}: Starting...")
        self.started = True

    def stop(self):
        """Stop service."""
        print(f"{self.name}: Stopping...")
        self.started = False

    def health_check(self):
        """Check health."""
        return ComponentHealth(
            status=ComponentStatus.RUNNING if self.started else ComponentStatus.STOPPED,
            healthy=self.started,
            message=f"{self.name} service operational" if self.started else "stopped",
        )


@dataclass
class MockRiskManager:
    """Mock adaptive risk manager."""

    name: str = "risk_manager"
    market_data: MockMarketDataService | None = None
    max_portfolio_risk: float = 0.05

    def initialize(self):
        """Initialize risk manager."""
        print(f"{self.name}: Initializing with max risk {self.max_portfolio_risk}...")

    def start(self):
        """Start risk manager."""
        print(f"{self.name}: Started")

    def stop(self):
        """Stop risk manager."""
        print(f"{self.name}: Stopped")

    def health_check(self):
        """Check health."""
        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="Risk manager operational",
            metrics={"max_portfolio_risk": self.max_portfolio_risk},
        )


@dataclass
class MockRegimeAnalyzer:
    """Mock market regime analyzer."""

    name: str = "regime_analyzer"
    market_data: MockMarketDataService | None = None
    lookback_periods: list[int] | None = None

    def __post_init__(self):
        if self.lookback_periods is None:
            self.lookback_periods = [20, 50, 200]

    def initialize(self):
        """Initialize regime analyzer."""
        print(f"{self.name}: Initializing with lookback {self.lookback_periods}...")

    def start(self):
        """Start regime analyzer."""
        print(f"{self.name}: Started")

    def stop(self):
        """Stop regime analyzer."""
        print(f"{self.name}: Stopped")

    def health_check(self):
        """Check health."""
        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="Regime analyzer operational",
            metrics={"lookback_periods": len(self.lookback_periods or [])},
        )


@dataclass
class MockPositionSizer:
    """Mock dynamic position sizer."""

    name: str = "position_sizer"
    risk_manager: MockRiskManager | None = None
    regime_analyzer: MockRegimeAnalyzer | None = None

    def initialize(self):
        """Initialize position sizer."""
        print(f"{self.name}: Initializing...")

    def start(self):
        """Start position sizer."""
        print(f"{self.name}: Started")

    def stop(self):
        """Stop position sizer."""
        print(f"{self.name}: Stopped")

    def health_check(self):
        """Check health."""
        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="Position sizer operational",
        )


@dataclass
class MockAgentCoordinator:
    """Mock agent coordinator."""

    name: str = "agent_coordinator"
    agents_count: int = 0

    def initialize(self):
        """Initialize agent coordinator."""
        print(f"{self.name}: Initializing...")

    def start(self):
        """Start agent coordinator."""
        print(f"{self.name}: Started with {self.agents_count} agents")

    def stop(self):
        """Stop agent coordinator."""
        print(f"{self.name}: Stopped")

    def health_check(self):
        """Check health."""
        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message=f"Agent coordinator operational with {self.agents_count} agents",
            metrics={"agents_count": self.agents_count},
        )


def demo_module_integration():
    """Demonstrate integration of modules using ArchitectureIntegrator."""
    print("\n" + "=" * 70)
    print("Module Integration Demonstration")
    print("=" * 70 + "\n")

    # Create integrator
    integrator = ArchitectureIntegrator()

    # Create module instances
    market_data = MockMarketDataService()
    risk_manager = MockRiskManager(market_data=market_data)
    regime_analyzer = MockRegimeAnalyzer(market_data=market_data)
    position_sizer = MockPositionSizer(
        risk_manager=risk_manager, regime_analyzer=regime_analyzer
    )
    agent_coordinator = MockAgentCoordinator(agents_count=4)

    # Register components with dependencies
    print("--- Registering Components ---")

    integrator.register_component(
        name="market_data_service",
        instance=market_data,
        version="1.0.0",
        description="Market data ingestion and management",
        tags=["service", "data", "core"],
        provides=["market_data"],
    )

    integrator.register_component(
        name="adaptive_risk_manager",
        instance=risk_manager,
        version="1.0.0",
        description="Adaptive risk management with TACL integration",
        tags=["module", "risk", "adaptive"],
        dependencies=["market_data_service"],
        provides=["risk_management"],
    )

    integrator.register_component(
        name="market_regime_analyzer",
        instance=regime_analyzer,
        version="1.0.0",
        description="Market regime detection and classification",
        tags=["module", "analytics", "regime"],
        dependencies=["market_data_service"],
        provides=["regime_analysis"],
    )

    integrator.register_component(
        name="dynamic_position_sizer",
        instance=position_sizer,
        version="1.0.0",
        description="Dynamic position sizing with Kelly criterion",
        tags=["module", "sizing", "risk"],
        dependencies=["adaptive_risk_manager", "market_regime_analyzer"],
        provides=["position_sizing"],
    )

    integrator.register_component(
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
    )

    print("✓ All components registered\n")

    # Show dependency graph
    print("--- Dependency Graph ---")
    graph = integrator.get_dependency_graph()
    for component, deps in sorted(graph.items()):
        if deps:
            print(f"  {component} → {', '.join(deps)}")
        else:
            print(f"  {component} (no dependencies)")

    # Show initialization order
    print("\n--- Initialization Order ---")
    order = integrator.get_initialization_order()
    for i, name in enumerate(order, 1):
        print(f"  {i}. {name}")

    # Initialize all components
    print("\n--- Initializing Components ---")
    integrator.initialize_all()

    # Start all components
    print("\n--- Starting Components ---")
    integrator.start_all()

    # Check system health
    print("\n--- System Health Check ---")
    health_map = integrator.aggregate_health()
    for name, health in sorted(health_map.items()):
        status_icon = "✓" if health.healthy else "✗"
        print(f"{status_icon} {name}: {health.status.value} - {health.message}")
        if health.metrics:
            for key, value in health.metrics.items():
                print(f"    {key}: {value}")

    is_healthy = integrator.is_system_healthy()
    print(f"\nOverall system health: {'HEALTHY' if is_healthy else 'UNHEALTHY'}")

    # Validate architecture
    print("\n--- Architecture Validation ---")
    validation = integrator.validate_architecture()
    print(f"Validation result: {'PASSED' if validation.passed else 'FAILED'}")
    summary = validation.summary()
    print(f"Issues: {summary}")

    # Demonstrate component access
    print("\n--- Component Access ---")
    rm = integrator.registry.get("adaptive_risk_manager").instance
    print(f"Risk Manager: {rm.name}, max_risk={rm.max_portfolio_risk}")

    ra = integrator.registry.get("market_regime_analyzer").instance
    print(f"Regime Analyzer: {ra.name}, lookback={ra.lookback_periods}")

    ps = integrator.registry.get("dynamic_position_sizer").instance
    print(f"Position Sizer: {ps.name}")

    ac = integrator.registry.get("agent_coordinator").instance
    print(f"Agent Coordinator: {ac.name}, agents={ac.agents_count}")

    # Simulate runtime monitoring
    print("\n--- Runtime Monitoring (3 seconds) ---")
    for i in range(3):
        time.sleep(1)
        is_healthy = integrator.is_system_healthy()
        status = "✓ HEALTHY" if is_healthy else "✗ UNHEALTHY"
        print(f"[{i+1}s] System Status: {status}")

    # Stop all components
    print("\n--- Stopping Components ---")
    integrator.stop_all()

    # Final status
    print("\n--- Final Status Summary ---")
    status_summary = integrator.get_status_summary()
    for status, count in status_summary.items():
        if count > 0:
            print(f"  {status}: {count}")

    print("\n✓ Module integration demonstration completed successfully\n")


def main():
    """Run the demonstration."""
    demo_module_integration()


if __name__ == "__main__":
    main()
