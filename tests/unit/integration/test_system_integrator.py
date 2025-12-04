"""Tests for the unified SystemIntegrator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.architecture_integrator.component import ComponentHealth, ComponentStatus
from core.integration.system_integrator import (
    IntegrationConfig,
    SystemIntegrator,
    SystemIntegratorBuilder,
)


class TestIntegrationConfig:
    """Tests for IntegrationConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = IntegrationConfig()

        assert config.enable_orchestrator is True
        assert config.enable_agent_coordinator is True
        assert config.enable_fractal_regulator is False
        assert config.auto_start_services is True
        assert config.health_check_interval == 30.0
        assert config.component_tags == ["tradepulse"]
        assert config.regulator_config == {}

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = IntegrationConfig(
            enable_orchestrator=False,
            enable_agent_coordinator=False,
            enable_fractal_regulator=True,
            auto_start_services=False,
            health_check_interval=60.0,
            component_tags=["custom", "tags"],
            regulator_config={"window_size": 200},
        )

        assert config.enable_orchestrator is False
        assert config.enable_agent_coordinator is False
        assert config.enable_fractal_regulator is True
        assert config.auto_start_services is False
        assert config.health_check_interval == 60.0
        assert config.component_tags == ["custom", "tags"]
        assert config.regulator_config == {"window_size": 200}


class TestSystemIntegrator:
    """Tests for SystemIntegrator."""

    def test_initialization_with_default_config(self) -> None:
        """Test initialization with default configuration."""
        integrator = SystemIntegrator()

        assert integrator.config is not None
        assert not integrator.is_bootstrapped
        assert not integrator.is_started
        assert integrator.system is None
        assert integrator.orchestrator is None
        assert integrator.service_registry is None
        assert integrator.agent_coordinator is None

    def test_initialization_with_custom_config(self) -> None:
        """Test initialization with custom configuration."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)

        assert integrator.config.auto_start_services is False

    def test_architecture_integrator_property(self) -> None:
        """Test architecture integrator property."""
        integrator = SystemIntegrator()

        assert integrator.architecture_integrator is not None

    def test_register_service_registry(self) -> None:
        """Test registering a service registry."""
        integrator = SystemIntegrator()
        mock_registry = MagicMock()
        mock_registry.services.return_value = []

        integrator.register_service_registry(mock_registry)

        assert integrator.service_registry is mock_registry
        assert "service_registry" in integrator.list_components()

    def test_register_agent_coordinator(self) -> None:
        """Test registering an agent coordinator."""
        integrator = SystemIntegrator()
        mock_coordinator = MagicMock()
        mock_coordinator.get_system_health.return_value = {"health_score": "100"}
        mock_coordinator.get_coordination_summary.return_value = {"registered_agents": 0}

        integrator.register_agent_coordinator(mock_coordinator)

        assert integrator.agent_coordinator is mock_coordinator
        assert "agent_coordinator" in integrator.list_components()

    def test_register_custom_component(self) -> None:
        """Test registering a custom component."""
        integrator = SystemIntegrator()
        mock_component = MagicMock()

        integrator.register_custom_component(
            name="custom_service",
            instance=mock_component,
            description="A custom service",
            tags=["custom"],
        )

        assert "custom_service" in integrator.list_components()

    def test_bootstrap_without_components(self) -> None:
        """Test bootstrap with no registered components."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)

        integrator.bootstrap()

        assert integrator.is_bootstrapped

    def test_bootstrap_twice_logs_warning(self) -> None:
        """Test that bootstrapping twice logs a warning."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.bootstrap()

        # Second bootstrap should not raise but just return
        integrator.bootstrap()

        assert integrator.is_bootstrapped

    def test_start_all_requires_bootstrap(self) -> None:
        """Test that start_all requires bootstrap."""
        integrator = SystemIntegrator()

        with pytest.raises(RuntimeError, match="bootstrapped"):
            integrator.start_all()

    def test_start_all_after_bootstrap(self) -> None:
        """Test starting all components after bootstrap."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.bootstrap()

        result = integrator.start_all()

        assert integrator.is_started
        assert isinstance(result, list)

    def test_start_all_twice_returns_empty(self) -> None:
        """Test that starting twice returns empty list."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.bootstrap()
        integrator.start_all()

        result = integrator.start_all()

        assert result == []

    def test_stop_all_when_not_started(self) -> None:
        """Test stopping when not started returns empty list."""
        integrator = SystemIntegrator()

        result = integrator.stop_all()

        assert result == []

    def test_stop_all_when_started(self) -> None:
        """Test stopping all components when started."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.bootstrap()
        integrator.start_all()

        result = integrator.stop_all()

        assert not integrator.is_started
        assert isinstance(result, list)

    def test_restart(self) -> None:
        """Test restarting the system."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.bootstrap()
        integrator.start_all()

        integrator.restart()

        assert integrator.is_started

    def test_get_unified_health_no_components(self) -> None:
        """Test getting unified health with no components."""
        integrator = SystemIntegrator()

        health = integrator.get_unified_health()

        assert health["overall_status"] == "healthy"
        assert health["health_score"] == 100.0
        assert health["components"]["total"] == 0

    def test_get_unified_health_with_components(self) -> None:
        """Test getting unified health with components."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)

        # Add a mock component
        mock_component = MagicMock()
        integrator.register_custom_component(
            name="test_component",
            instance=mock_component,
            health_hook=lambda: ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
                message="OK",
            ),
        )

        integrator.bootstrap()
        integrator.start_all()

        health = integrator.get_unified_health()

        assert health["components"]["total"] == 1
        assert "test_component" in health["component_health"]

    def test_is_system_healthy(self) -> None:
        """Test checking if system is healthy."""
        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.bootstrap()
        integrator.start_all()

        # No components means healthy
        assert integrator.is_system_healthy()

    def test_validate_architecture(self) -> None:
        """Test validating architecture."""
        integrator = SystemIntegrator()

        result = integrator.validate_architecture()

        # With no components, should pass
        assert result.passed

    def test_list_components(self) -> None:
        """Test listing components."""
        integrator = SystemIntegrator()
        mock_component = MagicMock()

        integrator.register_custom_component("comp1", mock_component)
        integrator.register_custom_component("comp2", mock_component)

        components = integrator.list_components()

        assert "comp1" in components
        assert "comp2" in components
        assert len(components) == 2

    def test_get_dependency_graph(self) -> None:
        """Test getting dependency graph."""
        integrator = SystemIntegrator()
        mock_component = MagicMock()

        integrator.register_custom_component("base", mock_component)
        integrator.register_custom_component(
            "dependent",
            mock_component,
            dependencies=["base"],
        )

        graph = integrator.get_dependency_graph()

        assert "base" in graph
        assert "dependent" in graph
        assert "base" in graph["dependent"]

    def test_get_initialization_order(self) -> None:
        """Test getting initialization order."""
        integrator = SystemIntegrator()
        mock_component = MagicMock()

        integrator.register_custom_component("base", mock_component)
        integrator.register_custom_component(
            "dependent",
            mock_component,
            dependencies=["base"],
        )

        order = integrator.get_initialization_order()

        # Base should come before dependent
        assert list(order).index("base") < list(order).index("dependent")

    def test_get_status_summary(self) -> None:
        """Test getting status summary."""
        integrator = SystemIntegrator()

        summary = integrator.get_status_summary()

        assert isinstance(summary, dict)
        # Should have all status types
        assert "uninitialized" in summary

    def test_event_handler_registration(self) -> None:
        """Test registering event handlers."""
        integrator = SystemIntegrator()
        handler_called = []

        def test_handler(**kwargs):
            handler_called.append(kwargs)

        integrator.on("bootstrap_started", test_handler)

        config = IntegrationConfig(auto_start_services=False)
        integrator = SystemIntegrator(config)
        integrator.on("bootstrap_started", test_handler)
        integrator.bootstrap()

        assert len(handler_called) == 1


class TestSystemIntegratorBuilder:
    """Tests for SystemIntegratorBuilder."""

    def test_default_build(self) -> None:
        """Test building with default settings."""
        builder = SystemIntegratorBuilder()
        integrator = builder.build()

        assert isinstance(integrator, SystemIntegrator)
        assert integrator.system is None
        assert integrator.orchestrator is None

    def test_with_config(self) -> None:
        """Test building with custom config."""
        config = IntegrationConfig(auto_start_services=False)
        builder = SystemIntegratorBuilder()

        integrator = builder.with_config(config).build()

        assert integrator.config.auto_start_services is False

    def test_with_agent_coordinator(self) -> None:
        """Test building with agent coordinator."""
        mock_coordinator = MagicMock()
        mock_coordinator.get_system_health.return_value = {"health_score": "100"}
        mock_coordinator.get_coordination_summary.return_value = {"registered_agents": 0}

        builder = SystemIntegratorBuilder()
        integrator = (
            builder
            .with_agent_coordinator(mock_coordinator)
            .with_auto_start(False)
            .build()
        )

        assert integrator.agent_coordinator is mock_coordinator

    def test_with_service_registry(self) -> None:
        """Test building with service registry."""
        mock_registry = MagicMock()
        mock_registry.services.return_value = []

        builder = SystemIntegratorBuilder()
        integrator = (
            builder
            .with_service_registry(mock_registry)
            .with_auto_start(False)
            .build()
        )

        assert integrator.service_registry is mock_registry

    def test_with_auto_start(self) -> None:
        """Test setting auto-start."""
        builder = SystemIntegratorBuilder()

        integrator = builder.with_auto_start(False).build()

        assert integrator.config.auto_start_services is False

    def test_with_fractal_regulator(self) -> None:
        """Test enabling fractal regulator."""
        builder = SystemIntegratorBuilder()

        integrator = (
            builder
            .with_fractal_regulator(True, {"window_size": 150})
            .build()
        )

        assert integrator.config.enable_fractal_regulator is True
        assert integrator.config.regulator_config["window_size"] == 150

    def test_add_custom_component(self) -> None:
        """Test adding custom components via builder."""
        mock_component = MagicMock()
        builder = SystemIntegratorBuilder()

        integrator = (
            builder
            .with_auto_start(False)
            .add_custom_component("custom", mock_component, description="Test")
            .build()
        )

        assert "custom" in integrator.list_components()

    def test_method_chaining(self) -> None:
        """Test that builder methods support chaining."""
        mock_coordinator = MagicMock()
        mock_coordinator.get_system_health.return_value = {"health_score": "100"}
        mock_coordinator.get_coordination_summary.return_value = {"registered_agents": 0}

        mock_registry = MagicMock()
        mock_registry.services.return_value = []

        builder = SystemIntegratorBuilder()
        integrator = (
            builder
            .with_config(IntegrationConfig())
            .with_service_registry(mock_registry)
            .with_agent_coordinator(mock_coordinator)
            .with_auto_start(False)
            .with_fractal_regulator(True)
            .add_custom_component("test", MagicMock())
            .build()
        )

        assert isinstance(integrator, SystemIntegrator)
        assert integrator.service_registry is mock_registry
        assert integrator.agent_coordinator is mock_coordinator
