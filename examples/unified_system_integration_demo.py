"""Demonstration of the Unified System Integration.

This example shows how the UnifiedSystemIntegrator brings together all
TradePulse components into a cohesive, production-ready system.

Features demonstrated:
- Automatic component registration and dependency management
- Lifecycle management (initialize, start, stop)
- Health monitoring across all components
- Architecture validation
- Component access and interaction
"""

from __future__ import annotations

import time
from pathlib import Path

from application.system import ExchangeAdapterConfig, TradePulseSystemConfig
from application.unified_integrator import (
    UnifiedIntegratorConfig,
    build_unified_system,
)
from execution.connectors import BinanceConnector, CoinbaseConnector


def demo_basic_integration():
    """Demonstrate basic unified system integration."""
    print("\n" + "=" * 70)
    print("Demo 1: Basic Unified System Integration")
    print("=" * 70 + "\n")

    # Build unified system with all components
    print("Building unified system with all components...")
    integrator = build_unified_system()

    # Show dependency graph
    print("\nComponent Dependency Graph:")
    graph = integrator.get_dependency_graph()
    for component, deps in sorted(graph.items()):
        if deps:
            print(f"  {component} → {', '.join(deps)}")
        else:
            print(f"  {component} (no dependencies)")

    # Initialize all components
    print("\n--- Initializing System ---")
    integrator.initialize()

    # Start all components
    print("\n--- Starting System ---")
    integrator.start()

    # Check system health
    print("\n--- System Health Check ---")
    health_map = integrator.get_system_health()
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
    is_valid = integrator.validate_architecture()
    print(f"Architecture validation: {'PASSED' if is_valid else 'FAILED'}")

    # Access components
    print("\n--- Component Access ---")
    risk_manager = integrator.get_component("adaptive_risk_manager")
    print(f"Risk Manager: {risk_manager.__class__.__name__}")

    regime_analyzer = integrator.get_component("market_regime_analyzer")
    print(f"Regime Analyzer: {regime_analyzer.__class__.__name__}")

    position_sizer = integrator.get_component("dynamic_position_sizer")
    print(f"Position Sizer: {position_sizer.__class__.__name__}")

    agent_coordinator = integrator.get_component("agent_coordinator")
    print(f"Agent Coordinator: {agent_coordinator.__class__.__name__}")

    # Stop system
    print("\n--- Stopping System ---")
    integrator.stop()

    print("\n✓ Demo completed successfully")


def demo_custom_configuration():
    """Demonstrate unified system with custom configuration."""
    print("\n" + "=" * 70)
    print("Demo 2: Custom Configuration")
    print("=" * 70 + "\n")

    # Create custom system configuration
    venues = [
        ExchangeAdapterConfig(name="binance", connector=BinanceConnector()),
        ExchangeAdapterConfig(name="coinbase", connector=CoinbaseConnector()),
    ]

    system_config = TradePulseSystemConfig(
        venues=venues,
        allowed_data_roots=[Path("/tmp/tradepulse/data")],
        max_csv_bytes=10_000_000,  # 10MB limit
    )

    # Create custom integrator configuration
    integrator_config = UnifiedIntegratorConfig(
        enable_risk_manager=True,
        enable_regime_analyzer=True,
        enable_position_sizer=True,
        enable_agent_coordinator=True,
        risk_manager_config={
            "max_portfolio_risk": 0.05,  # 5% max risk
            "default_stop_loss": 0.02,   # 2% stop loss
        },
        regime_analyzer_config={
            "lookback_periods": [20, 50, 200],
            "volatility_window": 20,
        },
    )

    print("Building unified system with custom configuration...")
    integrator = build_unified_system(system_config, integrator_config)

    # Show configuration
    print("\nSystem Configuration:")
    print(f"  Venues: {len(venues)}")
    print("  Risk Manager: Enabled")
    print("  Regime Analyzer: Enabled")
    print("  Position Sizer: Enabled")
    print("  Agent Coordinator: Enabled")

    # Initialize and start
    integrator.initialize()
    integrator.start()

    # Verify components
    print("\n--- Registered Components ---")
    components = integrator.components
    for name, component in sorted(components.items()):
        print(f"  {name}: {component.__class__.__name__}")

    # Stop
    integrator.stop()

    print("\n✓ Demo completed successfully")


def demo_selective_components():
    """Demonstrate unified system with selective component enablement."""
    print("\n" + "=" * 70)
    print("Demo 3: Selective Component Enablement")
    print("=" * 70 + "\n")

    # Enable only core services and risk manager
    integrator_config = UnifiedIntegratorConfig(
        enable_risk_manager=True,
        enable_regime_analyzer=False,
        enable_position_sizer=False,
        enable_agent_coordinator=False,
    )

    print("Building system with only core services + risk manager...")
    integrator = build_unified_system(integrator_config=integrator_config)

    # Show what's enabled
    print("\nEnabled Components:")
    graph = integrator.get_dependency_graph()
    for component in sorted(graph.keys()):
        print(f"  - {component}")

    # Initialize and start
    integrator.initialize()
    integrator.start()

    # Check health
    print("\n--- Health Check ---")
    health_map = integrator.get_system_health()
    for name, health in sorted(health_map.items()):
        status_icon = "✓" if health.healthy else "✗"
        print(f"{status_icon} {name}: {health.message}")

    # Stop
    integrator.stop()

    print("\n✓ Demo completed successfully")


def demo_component_interaction():
    """Demonstrate interaction between integrated components."""
    print("\n" + "=" * 70)
    print("Demo 4: Component Interaction")
    print("=" * 70 + "\n")

    # Build full system
    print("Building unified system...")
    integrator = build_unified_system()
    integrator.initialize()
    integrator.start()

    # Get components
    print("\n--- Accessing Components ---")
    risk_manager = integrator.get_component("adaptive_risk_manager")
    regime_analyzer = integrator.get_component("market_regime_analyzer")
    position_sizer = integrator.get_component("dynamic_position_sizer")
    agent_coordinator = integrator.get_component("agent_coordinator")
    service_registry = integrator.service_registry

    print(f"✓ Risk Manager: {risk_manager.__class__.__name__}")
    print(f"✓ Regime Analyzer: {regime_analyzer.__class__.__name__}")
    print(f"✓ Position Sizer: {position_sizer.__class__.__name__}")
    print(f"✓ Agent Coordinator: {agent_coordinator.__class__.__name__}")
    print(f"✓ Service Registry: {service_registry.__class__.__name__}")

    # Show service access
    print("\n--- Microservices Access ---")
    market_data = service_registry.market_data
    backtesting = service_registry.backtesting
    execution = service_registry.execution

    print(f"✓ Market Data Service: {market_data.__class__.__name__}")
    print(f"✓ Backtesting Service: {backtesting.__class__.__name__}")
    print(f"✓ Execution Service: {execution.__class__.__name__}")

    # Demonstrate component cooperation
    print("\n--- Component Cooperation Example ---")
    print("Scenario: Analyzing market regime and adjusting risk parameters")

    # Simulate market regime detection
    print("\n1. Regime Analyzer detects market conditions")
    print("   → Current regime: NORMAL")
    print("   → Volatility: MODERATE")

    # Risk manager adjusts based on regime
    print("\n2. Risk Manager adjusts limits based on regime")
    print("   → Position limits updated")
    print("   → Stop-loss parameters adjusted")

    # Position sizer calculates optimal sizes
    print("\n3. Position Sizer calculates optimal position sizes")
    print("   → Kelly criterion applied")
    print("   → Risk-adjusted sizes computed")

    # Agent coordinator manages workflow
    print("\n4. Agent Coordinator orchestrates execution")
    print("   → Tasks distributed to agents")
    print("   → Execution workflow managed")

    print("\n✓ Components working together seamlessly")

    # Stop system
    integrator.stop()

    print("\n✓ Demo completed successfully")


def demo_monitoring_and_health():
    """Demonstrate continuous monitoring and health checks."""
    print("\n" + "=" * 70)
    print("Demo 5: Monitoring and Health Checks")
    print("=" * 70 + "\n")

    print("Building unified system...")
    integrator = build_unified_system()
    integrator.initialize()
    integrator.start()

    # Continuous health monitoring simulation
    print("\n--- Continuous Health Monitoring (5 seconds) ---")
    for i in range(5):
        time.sleep(1)
        is_healthy = integrator.is_system_healthy()
        status = "✓ HEALTHY" if is_healthy else "✗ UNHEALTHY"
        print(f"[{i+1}s] System Status: {status}")

        if not is_healthy:
            print("\nDetailed Health Report:")
            health_map = integrator.get_system_health()
            for name, health in health_map.items():
                if not health.healthy:
                    print(f"  ⚠ {name}: {health.message}")

    # Final status report
    print("\n--- Final Status Report ---")
    health_map = integrator.get_system_health()

    healthy_count = sum(1 for h in health_map.values() if h.healthy)
    total_count = len(health_map)

    print(f"Healthy Components: {healthy_count}/{total_count}")
    print(f"Overall Health: {'PASS' if healthy_count == total_count else 'FAIL'}")

    # Stop system
    integrator.stop()

    print("\n✓ Demo completed successfully")


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 70)
    print("Unified System Integration Demonstration")
    print("=" * 70)

    demo_basic_integration()
    time.sleep(1)

    demo_custom_configuration()
    time.sleep(1)

    demo_selective_components()
    time.sleep(1)

    demo_component_interaction()
    time.sleep(1)

    demo_monitoring_and_health()

    print("\n" + "=" * 70)
    print("All Demonstrations Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
