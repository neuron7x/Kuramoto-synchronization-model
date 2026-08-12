# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Demonstration of the Architecture Integrator.

This example shows how to use the Architecture Integrator to manage
system components with proper lifecycle, dependency management, and
health monitoring.
"""

from __future__ import annotations

import time
from typing import Any

from core.architecture_integrator import (
    ArchitectureIntegrator,
    ComponentHealth,
    ComponentStatus,
)

# ------------------------------------------------------------------
# Example Components
# ------------------------------------------------------------------


class ConfigurationService:
    """Example configuration service."""

    def __init__(self):
        self.config: dict[str, Any] = {}
        self.initialized = False

    def initialize(self):
        """Load configuration."""
        print("ConfigurationService: Loading configuration...")
        self.config = {
            "database_url": "postgresql://localhost/geosync",
            "cache_ttl": 300,
            "max_connections": 100,
        }
        self.initialized = True
        print("ConfigurationService: Configuration loaded")

    def start(self):
        """Start configuration service."""
        print("ConfigurationService: Started")

    def stop(self):
        """Stop configuration service."""
        print("ConfigurationService: Stopped")

    def health_check(self):
        """Check service health."""
        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="Configuration service operational",
            metrics={"config_entries": len(self.config)},
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)


class DatabaseService:
    """Example database service."""

    def __init__(self, config_service: ConfigurationService):
        self.config_service = config_service
        self.connected = False
        self.connection_pool = None

    def initialize(self):
        """Initialize database connection pool."""
        print("DatabaseService: Initializing...")
        db_url = self.config_service.get("database_url")
        print(f"DatabaseService: Connecting to {db_url}")
        # Simulate connection pool setup
        self.connection_pool = {"size": 10, "active": 0}
        print("DatabaseService: Connection pool created")

    def start(self):
        """Start accepting connections."""
        print("DatabaseService: Starting...")
        self.connected = True
        print("DatabaseService: Accepting connections")

    def stop(self):
        """Close all connections."""
        print("DatabaseService: Closing connections...")
        self.connected = False
        self.connection_pool = None
        print("DatabaseService: Stopped")

    def health_check(self):
        """Check database health."""
        if not self.connected:
            return ComponentHealth(
                status=ComponentStatus.STOPPED,
                healthy=False,
                message="Database not connected",
            )

        # Simulate connection check
        active = self.connection_pool.get("active", 0)
        pool_size = self.connection_pool.get("size", 0)

        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message=f"Database operational ({active}/{pool_size} connections)",
            metrics={
                "active_connections": active,
                "pool_size": pool_size,
            },
        )


class DataIngestionService:
    """Example data ingestion service."""

    def __init__(self, database_service: DatabaseService):
        self.database_service = database_service
        self.running = False
        self.records_ingested = 0

    def initialize(self):
        """Initialize ingestion pipeline."""
        print("DataIngestionService: Initializing pipeline...")
        # Setup would happen here
        print("DataIngestionService: Pipeline ready")

    def start(self):
        """Start ingestion."""
        print("DataIngestionService: Starting ingestion...")
        self.running = True
        print("DataIngestionService: Ingestion started")

    def stop(self):
        """Stop ingestion."""
        print("DataIngestionService: Stopping ingestion...")
        self.running = False
        print(f"DataIngestionService: Stopped (ingested {self.records_ingested} records)")

    def health_check(self):
        """Check ingestion health."""
        if not self.running:
            return ComponentHealth(
                status=ComponentStatus.STOPPED,
                healthy=False,
                message="Ingestion not running",
            )

        return ComponentHealth(
            status=ComponentStatus.RUNNING,
            healthy=True,
            message="Ingestion pipeline operational",
            metrics={"records_ingested": self.records_ingested},
        )


# ------------------------------------------------------------------
# Demo Functions
# ------------------------------------------------------------------


def demo_basic_usage():
    """Demonstrate basic Architecture Integrator usage."""
    print("\n" + "=" * 70)
    print("Demo 1: Basic Usage")
    print("=" * 70 + "\n")

    # Create integrator
    integrator = ArchitectureIntegrator()

    # Create services
    config_service = ConfigurationService()
    database_service = DatabaseService(config_service)
    ingestion_service = DataIngestionService(database_service)

    # Register components with dependencies
    integrator.register_component(
        name="config",
        instance=config_service,
        version="1.0.0",
        description="Configuration management service",
        tags=["core", "config"],
        provides=["configuration"],
    )

    integrator.register_component(
        name="database",
        instance=database_service,
        version="1.0.0",
        description="Database connection service",
        tags=["core", "data"],
        dependencies=["config"],
        provides=["database"],
    )

    integrator.register_component(
        name="ingestion",
        instance=ingestion_service,
        version="1.0.0",
        description="Data ingestion service",
        tags=["data", "pipeline"],
        dependencies=["database"],
        provides=["data_ingestion"],
    )

    # Show initialization order
    print("\nCalculated initialization order:")
    order = integrator.get_initialization_order()
    for i, name in enumerate(order, 1):
        print(f"  {i}. {name}")

    # Initialize all components
    print("\n--- Initializing All Components ---")
    integrator.initialize_all()

    # Start all components
    print("\n--- Starting All Components ---")
    integrator.start_all()

    # Check system health
    print("\n--- System Health Check ---")
    health_map = integrator.aggregate_health()
    for name, health in health_map.items():
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

    # Stop all components
    print("\n--- Stopping All Components ---")
    integrator.stop_all()

    # Final status
    print("\n--- Final Status Summary ---")
    status_summary = integrator.get_status_summary()
    for status, count in status_summary.items():
        if count > 0:
            print(f"  {status}: {count}")


def demo_event_handling():
    """Demonstrate event handling."""
    print("\n" + "=" * 70)
    print("Demo 2: Event Handling")
    print("=" * 70 + "\n")

    integrator = ArchitectureIntegrator()

    # Register event handlers
    def on_component_registered(name, **kwargs):
        print(f"[EVENT] Component registered: {name}")

    def on_initialization_started(**kwargs):
        print("[EVENT] Initialization started")

    def on_initialization_completed(count, **kwargs):
        print(f"[EVENT] Initialization completed: {count} components")

    def on_startup_started(**kwargs):
        print("[EVENT] Startup started")

    def on_startup_completed(count, **kwargs):
        print(f"[EVENT] Startup completed: {count} components")

    integrator.on("component_registered", on_component_registered)
    integrator.on("initialization_started", on_initialization_started)
    integrator.on("initialization_completed", on_initialization_completed)
    integrator.on("startup_started", on_startup_started)
    integrator.on("startup_completed", on_startup_completed)

    # Register and start components (events will be emitted)
    config_service = ConfigurationService()
    integrator.register_component(name="config", instance=config_service)

    database_service = DatabaseService(config_service)
    integrator.register_component(
        name="database",
        instance=database_service,
        dependencies=["config"],
    )

    integrator.initialize_all()
    integrator.start_all()
    integrator.stop_all()


def demo_dependency_management():
    """Demonstrate dependency graph and validation."""
    print("\n" + "=" * 70)
    print("Demo 3: Dependency Management")
    print("=" * 70 + "\n")

    integrator = ArchitectureIntegrator()

    # Register components with complex dependencies
    config_service = ConfigurationService()
    database_service = DatabaseService(config_service)
    ingestion_service = DataIngestionService(database_service)

    integrator.register_component(name="config", instance=config_service)
    integrator.register_component(
        name="database",
        instance=database_service,
        dependencies=["config"],
    )
    integrator.register_component(
        name="ingestion",
        instance=ingestion_service,
        dependencies=["database"],
    )

    # Show dependency graph
    print("Dependency Graph:")
    graph = integrator.get_dependency_graph()
    for component, deps in graph.items():
        if deps:
            print(f"  {component} → {', '.join(deps)}")
        else:
            print(f"  {component} (no dependencies)")

    # Validate dependencies
    print("\nValidating dependencies...")
    validation = integrator.validate_architecture()

    if validation.passed:
        print("✓ All dependencies satisfied")
    else:
        print("✗ Validation failed:")
        for issue in validation.issues:
            print(f"  [{issue.severity.value}] {issue.message}")

    # Try registering component with missing dependency
    print("\nTrying to register component with missing dependency...")

    class InvalidService:
        def initialize(self):
            pass

    integrator.register_component(
        name="invalid",
        instance=InvalidService(),
        dependencies=["nonexistent"],
    )

    validation = integrator.validate_architecture()
    print(f"Validation result: {'PASSED' if validation.passed else 'FAILED'}")
    if not validation.passed:
        for issue in validation.get_blocking_issues():
            print(f"  [ERROR] {issue.message}")


def demo_lifecycle_hooks():
    """Demonstrate custom lifecycle hooks."""
    print("\n" + "=" * 70)
    print("Demo 4: Custom Lifecycle Hooks")
    print("=" * 70 + "\n")

    integrator = ArchitectureIntegrator()

    # Custom hooks for a component without standard methods
    state = {"initialized": False, "started": False}

    def custom_init():
        print("Custom initialization hook called")
        state["initialized"] = True

    def custom_start():
        print("Custom startup hook called")
        state["started"] = True

    def custom_stop():
        print("Custom shutdown hook called")
        state["started"] = False

    def custom_health():
        if not state["initialized"]:
            status = ComponentStatus.UNINITIALIZED
            healthy = False
        elif not state["started"]:
            status = ComponentStatus.INITIALIZED
            healthy = True
        else:
            status = ComponentStatus.RUNNING
            healthy = True

        return ComponentHealth(
            status=status,
            healthy=healthy,
            message=f"State: init={state['initialized']}, started={state['started']}",
        )

    # Register with hooks
    integrator.register_component(
        name="custom_component",
        instance=None,  # No actual instance needed
        init_hook=custom_init,
        start_hook=custom_start,
        stop_hook=custom_stop,
        health_hook=custom_health,
    )

    print("Initializing component...")
    integrator.initialize_all()

    print("\nStarting component...")
    integrator.start_all()

    print("\nChecking health...")
    health = integrator.check_component_health("custom_component")
    print(f"Health: {health.status.value} - {health.message}")

    print("\nStopping component...")
    integrator.stop_all()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 70)
    print("Architecture Integrator Demonstration")
    print("=" * 70)

    demo_basic_usage()
    time.sleep(1)

    demo_event_handling()
    time.sleep(1)

    demo_dependency_management()
    time.sleep(1)

    demo_lifecycle_hooks()

    print("\n" + "=" * 70)
    print("Demonstration Complete")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
