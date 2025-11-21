"""Tests for the Unified System Integrator."""

import pytest

from application.system import ExchangeAdapterConfig, TradePulseSystemConfig
from application.unified_integrator import (
    UnifiedIntegratorConfig,
    UnifiedSystemIntegrator,
    build_unified_system,
)
from execution.connectors import BinanceConnector


class TestUnifiedIntegratorConfig:
    """Tests for UnifiedIntegratorConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = UnifiedIntegratorConfig()
        assert config.enable_risk_manager is True
        assert config.enable_regime_analyzer is True
        assert config.enable_position_sizer is True
        assert config.enable_agent_coordinator is True
        assert config.enable_fractal_regulator is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = UnifiedIntegratorConfig(
            enable_risk_manager=False,
            enable_regime_analyzer=True,
            risk_manager_config={"max_risk": 0.05},
        )
        assert config.enable_risk_manager is False
        assert config.enable_regime_analyzer is True
        assert config.risk_manager_config == {"max_risk": 0.05}


class TestUnifiedSystemIntegrator:
    """Tests for UnifiedSystemIntegrator."""

    @pytest.fixture
    def minimal_system_config(self):
        """Create a minimal system configuration for testing."""
        venues = [
            ExchangeAdapterConfig(name="test_binance", connector=BinanceConnector())
        ]
        return TradePulseSystemConfig(venues=venues)

    @pytest.fixture
    def integrator(self, minimal_system_config):
        """Create a test integrator instance."""
        from application.system import TradePulseSystem

        system = TradePulseSystem(minimal_system_config)
        config = UnifiedIntegratorConfig(
            enable_risk_manager=True,
            enable_regime_analyzer=True,
            enable_position_sizer=True,
            enable_agent_coordinator=True,
        )
        return UnifiedSystemIntegrator(system, config)

    def test_initialization(self, integrator):
        """Test integrator initialization."""
        assert integrator is not None
        assert integrator._integrator is not None
        assert integrator._config is not None
        assert integrator._system is not None

    def test_component_registration(self, integrator):
        """Test that all components are registered."""
        # Check service components
        assert integrator._integrator.registry.has_component("market_data_service")
        assert integrator._integrator.registry.has_component("backtesting_service")
        assert integrator._integrator.registry.has_component("execution_service")

        # Check module components
        assert integrator._integrator.registry.has_component("adaptive_risk_manager")
        assert integrator._integrator.registry.has_component("market_regime_analyzer")
        assert integrator._integrator.registry.has_component("dynamic_position_sizer")
        assert integrator._integrator.registry.has_component("agent_coordinator")

    def test_dependency_graph(self, integrator):
        """Test that dependency graph is correct."""
        graph = integrator.get_dependency_graph()

        # Services have no dependencies or depend on other services
        assert "market_data_service" in graph
        assert "backtesting_service" in graph
        assert "execution_service" in graph

        # Modules depend on services
        assert "market_data_service" in graph["adaptive_risk_manager"]
        assert "market_data_service" in graph["market_regime_analyzer"]

        # Position sizer depends on other modules
        assert "adaptive_risk_manager" in graph["dynamic_position_sizer"]
        assert "market_regime_analyzer" in graph["dynamic_position_sizer"]

    def test_initialization_order(self, integrator):
        """Test that initialization order respects dependencies."""
        order = integrator._integrator.get_initialization_order()

        # Services should come before modules that depend on them
        market_data_idx = order.index("market_data_service")
        risk_manager_idx = order.index("adaptive_risk_manager")
        assert market_data_idx < risk_manager_idx

        # Risk manager should come before position sizer
        position_sizer_idx = order.index("dynamic_position_sizer")
        assert risk_manager_idx < position_sizer_idx

    def test_lifecycle_management(self, integrator):
        """Test initialize, start, and stop lifecycle."""
        # Initialize
        integrator.initialize()

        # Start
        integrator.start()
        assert integrator.is_system_healthy()

        # Stop
        integrator.stop()

    def test_health_monitoring(self, integrator):
        """Test system health monitoring."""
        integrator.initialize()
        integrator.start()

        # Get overall health
        is_healthy = integrator.is_system_healthy()
        assert is_healthy is True

        # Get detailed health
        health_map = integrator.get_system_health()
        assert len(health_map) > 0

        # All components should be healthy
        for name, health in health_map.items():
            assert health.healthy is True

        integrator.stop()

    def test_architecture_validation(self, integrator):
        """Test architecture validation."""
        is_valid = integrator.validate_architecture()
        assert is_valid is True

    def test_component_access(self, integrator):
        """Test accessing registered components."""
        # Access via get_component
        risk_manager = integrator.get_component("adaptive_risk_manager")
        assert risk_manager is not None

        regime_analyzer = integrator.get_component("market_regime_analyzer")
        assert regime_analyzer is not None

        # Access via service_registry
        service_registry = integrator.service_registry
        assert service_registry is not None
        assert service_registry.market_data is not None

    def test_component_not_found(self, integrator):
        """Test accessing non-existent component raises error."""
        with pytest.raises(KeyError):
            integrator.get_component("nonexistent_component")

    def test_selective_components(self, minimal_system_config):
        """Test selective component enablement."""
        from application.system import TradePulseSystem

        system = TradePulseSystem(minimal_system_config)
        config = UnifiedIntegratorConfig(
            enable_risk_manager=True,
            enable_regime_analyzer=False,
            enable_position_sizer=False,
            enable_agent_coordinator=False,
        )
        integrator = UnifiedSystemIntegrator(system, config)

        # Should have services and risk manager only
        assert integrator._integrator.registry.has_component("market_data_service")
        assert integrator._integrator.registry.has_component("adaptive_risk_manager")
        assert not integrator._integrator.registry.has_component(
            "market_regime_analyzer"
        )
        assert not integrator._integrator.registry.has_component(
            "dynamic_position_sizer"
        )
        assert not integrator._integrator.registry.has_component("agent_coordinator")


class TestBuildUnifiedSystem:
    """Tests for build_unified_system convenience function."""

    def test_build_with_defaults(self):
        """Test building system with default configuration."""
        integrator = build_unified_system()
        assert integrator is not None
        assert isinstance(integrator, UnifiedSystemIntegrator)

    def test_build_with_custom_config(self):
        """Test building system with custom configuration."""
        integrator_config = UnifiedIntegratorConfig(
            enable_risk_manager=True,
            enable_regime_analyzer=False,
        )
        integrator = build_unified_system(integrator_config=integrator_config)
        assert integrator is not None

        # Check that only risk manager is enabled
        assert integrator._integrator.registry.has_component("adaptive_risk_manager")
        assert not integrator._integrator.registry.has_component(
            "market_regime_analyzer"
        )

    def test_full_lifecycle_with_builder(self):
        """Test full lifecycle using builder function."""
        integrator = build_unified_system()

        # Initialize and start
        integrator.initialize()
        integrator.start()

        # Verify system is healthy
        assert integrator.is_system_healthy()

        # Validate architecture
        assert integrator.validate_architecture()

        # Stop
        integrator.stop()


@pytest.mark.integration
class TestUnifiedSystemIntegration:
    """Integration tests for the unified system."""

    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        # Build system
        integrator = build_unified_system()

        # Initialize
        integrator.initialize()

        # Start
        integrator.start()

        # Get components and verify they work together
        risk_manager = integrator.get_component("adaptive_risk_manager")
        regime_analyzer = integrator.get_component("market_regime_analyzer")
        position_sizer = integrator.get_component("dynamic_position_sizer")
        agent_coordinator = integrator.get_component("agent_coordinator")

        assert risk_manager is not None
        assert regime_analyzer is not None
        assert position_sizer is not None
        assert agent_coordinator is not None

        # Verify services
        service_registry = integrator.service_registry
        assert service_registry.market_data is not None
        assert service_registry.backtesting is not None
        assert service_registry.execution is not None

        # Check system health
        assert integrator.is_system_healthy()

        # Validate architecture
        assert integrator.validate_architecture()

        # Stop
        integrator.stop()

    def test_component_cooperation(self):
        """Test that components can cooperate."""
        integrator = build_unified_system()
        integrator.initialize()
        integrator.start()

        # Get components
        risk_manager = integrator.get_component("adaptive_risk_manager")
        regime_analyzer = integrator.get_component("market_regime_analyzer")

        # Both components should be operational
        health_map = integrator.get_system_health()
        assert health_map["adaptive_risk_manager"].healthy
        assert health_map["market_regime_analyzer"].healthy

        integrator.stop()
