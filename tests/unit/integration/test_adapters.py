# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the unified system integration adapters."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.architecture_integrator.component import ComponentStatus
from core.integration.adapters import (
    AgentCoordinatorAdapter,
    ServiceRegistryAdapter,
    create_agent_coordinator_adapter,
    create_service_registry_adapter,
)


class TestServiceRegistryAdapter:
    """Tests for ServiceRegistryAdapter."""

    def test_initialization(self) -> None:
        """Test adapter initialization."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)

        assert adapter._registry is mock_registry
        assert not adapter._initialized
        assert not adapter._started

    def test_initialize(self) -> None:
        """Test initialize method."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)

        adapter.initialize()

        assert adapter._initialized

    def test_start(self) -> None:
        """Test start method."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)

        adapter.start()

        mock_registry.start_all.assert_called_once()
        assert adapter._started

    def test_stop(self) -> None:
        """Test stop method."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)
        adapter._started = True

        adapter.stop()

        mock_registry.stop_all.assert_called_once()
        assert not adapter._started

    def test_health_check_uninitialized(self) -> None:
        """Test health check when not initialized."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)

        health = adapter.health_check()

        assert health.status == ComponentStatus.UNINITIALIZED
        assert not health.healthy
        assert "not initialized" in health.message

    def test_health_check_initialized_not_started(self) -> None:
        """Test health check when initialized but not started."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)
        adapter._initialized = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.INITIALIZED
        assert health.healthy
        assert "not started" in health.message

    def test_health_check_running_healthy(self) -> None:
        """Test health check when running and all services healthy."""
        mock_registry = MagicMock()
        mock_service1 = MagicMock()
        mock_service1.name = "market_data"

        # Import ServiceState at runtime (same as adapter to avoid circular imports)
        from application.microservices.base import ServiceState

        mock_service1.state = ServiceState.RUNNING

        mock_registry.services.return_value = [mock_service1]

        adapter = ServiceRegistryAdapter(mock_registry)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.RUNNING
        assert health.healthy
        assert "1 services operational" in health.message
        assert health.metrics["total_services"] == 1.0
        assert health.metrics["healthy_services"] == 1.0

    def test_health_check_running_with_errors(self) -> None:
        """Test health check when some services have errors."""
        mock_registry = MagicMock()

        from application.microservices.base import ServiceState

        mock_service1 = MagicMock()
        mock_service1.name = "market_data"
        mock_service1.state = ServiceState.RUNNING

        mock_service2 = MagicMock()
        mock_service2.name = "execution"
        mock_service2.state = ServiceState.ERROR

        mock_registry.services.return_value = [mock_service1, mock_service2]

        adapter = ServiceRegistryAdapter(mock_registry)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert not health.healthy
        assert "execution" in health.message

    def test_registry_property(self) -> None:
        """Test registry property accessor."""
        mock_registry = MagicMock()
        adapter = ServiceRegistryAdapter(mock_registry)

        assert adapter.registry is mock_registry

    def test_get_service_names(self) -> None:
        """Test getting service names."""
        mock_registry = MagicMock()
        mock_service1 = MagicMock()
        mock_service1.name = "market_data"
        mock_service2 = MagicMock()
        mock_service2.name = "execution"
        mock_registry.services.return_value = [mock_service1, mock_service2]

        adapter = ServiceRegistryAdapter(mock_registry)
        names = adapter.get_service_names()

        assert names == ["market_data", "execution"]


class TestAgentCoordinatorAdapter:
    """Tests for AgentCoordinatorAdapter."""

    def test_initialization(self) -> None:
        """Test adapter initialization."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)

        assert adapter._coordinator is mock_coordinator
        assert not adapter._initialized
        assert not adapter._started

    def test_initialize(self) -> None:
        """Test initialize method."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)

        adapter.initialize()

        assert adapter._initialized

    def test_start(self) -> None:
        """Test start method."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)

        adapter.start()

        assert adapter._started

    def test_stop(self) -> None:
        """Test stop method triggers emergency stop."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)
        adapter._started = True

        adapter.stop()

        mock_coordinator.make_decision.assert_called_once()
        call_args = mock_coordinator.make_decision.call_args
        assert call_args[0][0] == "emergency_stop"
        assert not adapter._started

    def test_health_check_uninitialized(self) -> None:
        """Test health check when not initialized."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)

        health = adapter.health_check()

        assert health.status == ComponentStatus.UNINITIALIZED
        assert not health.healthy

    def test_health_check_initialized_not_started(self) -> None:
        """Test health check when initialized but not started."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)
        adapter._initialized = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.INITIALIZED
        assert health.healthy

    def test_health_check_running_healthy(self) -> None:
        """Test health check when running and healthy."""
        mock_coordinator = MagicMock()
        # AgentCoordinator.get_system_health returns health_score as a formatted string
        mock_coordinator.get_system_health.return_value = {
            "health_score": "85.0",
            "total_agents": 3,
            "active_agents": 2,
            "error_agents": 0,
            "queued_tasks": 1,
            "active_tasks": 1,
        }

        adapter = AgentCoordinatorAdapter(mock_coordinator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.RUNNING
        assert health.healthy
        assert health.metrics["health_score"] == 85.0

    def test_health_check_with_error_agents(self) -> None:
        """Test health check when agents have errors."""
        mock_coordinator = MagicMock()
        mock_coordinator.get_system_health.return_value = {
            "health_score": "60.0",
            "total_agents": 3,
            "active_agents": 1,
            "error_agents": 2,
            "queued_tasks": 0,
            "active_tasks": 0,
        }

        adapter = AgentCoordinatorAdapter(mock_coordinator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert not health.healthy
        assert "2 agents in error state" in health.message

    def test_health_check_low_health_score(self) -> None:
        """Test health check when health score is low."""
        mock_coordinator = MagicMock()
        mock_coordinator.get_system_health.return_value = {
            "health_score": "30.0",
            "total_agents": 1,
            "active_agents": 0,
            "error_agents": 0,
            "queued_tasks": 10,
            "active_tasks": 0,
        }

        adapter = AgentCoordinatorAdapter(mock_coordinator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert not health.healthy
        assert "low" in health.message.lower()

    def test_coordinator_property(self) -> None:
        """Test coordinator property accessor."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)

        assert adapter.coordinator is mock_coordinator

    def test_get_agent_count(self) -> None:
        """Test getting agent count."""
        mock_coordinator = MagicMock()
        mock_coordinator.get_coordination_summary.return_value = {"registered_agents": 5}

        adapter = AgentCoordinatorAdapter(mock_coordinator)
        count = adapter.get_agent_count()

        assert count == 5

    def test_process_pending_tasks_when_not_started(self) -> None:
        """Test processing tasks when not started returns empty list."""
        mock_coordinator = MagicMock()
        adapter = AgentCoordinatorAdapter(mock_coordinator)

        result = adapter.process_pending_tasks()

        assert result == []
        mock_coordinator.process_tasks.assert_not_called()

    def test_process_pending_tasks_when_started(self) -> None:
        """Test processing tasks when started."""
        mock_coordinator = MagicMock()
        mock_coordinator.process_tasks.return_value = ["task_1", "task_2"]

        adapter = AgentCoordinatorAdapter(mock_coordinator)
        adapter._started = True

        result = adapter.process_pending_tasks()

        assert result == ["task_1", "task_2"]
        mock_coordinator.process_tasks.assert_called_once()


class TestFactoryFunctions:
    """Tests for adapter factory functions."""

    def test_create_service_registry_adapter(self) -> None:
        """Test factory function for ServiceRegistryAdapter."""
        mock_registry = MagicMock()

        adapter = create_service_registry_adapter(mock_registry)

        assert isinstance(adapter, ServiceRegistryAdapter)
        assert adapter.registry is mock_registry

    def test_create_agent_coordinator_adapter(self) -> None:
        """Test factory function for AgentCoordinatorAdapter."""
        mock_coordinator = MagicMock()

        adapter = create_agent_coordinator_adapter(mock_coordinator)

        assert isinstance(adapter, AgentCoordinatorAdapter)
        assert adapter.coordinator is mock_coordinator
