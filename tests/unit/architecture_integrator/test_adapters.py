# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core/architecture_integrator/adapters.py module."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.architecture_integrator.adapters import (
    GeoSyncOrchestratorAdapter,
    GeoSyncSystemAdapter,
    create_orchestrator_component_adapter,
    create_system_component_adapter,
)
from core.architecture_integrator.component import ComponentStatus


class TestGeoSyncSystemAdapter:
    """Tests for GeoSyncSystemAdapter class."""

    def test_initialization(self) -> None:
        """Test adapter initialization."""
        mock_system = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)

        assert adapter._system == mock_system
        assert adapter._initialized is False
        assert adapter._started is False

    def test_initialize(self) -> None:
        """Test initialize method."""
        mock_system = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)

        adapter.initialize()

        assert adapter._initialized is True

    def test_stop_without_live_loop_attribute_does_not_raise(self) -> None:
        """`hasattr(system, "live_loop") and system.live_loop` -- conjunctive.

        A system with NO live_loop attribute must stop cleanly. Under And->Or the
        short-circuit is lost and `system.live_loop` is dereferenced on a system
        that has no such attribute (AttributeError) -- the `pass` body hid this
        until the missing-attribute state was attacked.
        """
        adapter = GeoSyncSystemAdapter(MagicMock(spec=[]))
        adapter.stop()  # must not raise
        assert adapter._started is False

    def test_start_without_live_loop(self) -> None:
        """Test start when system has no live loop."""
        mock_system = MagicMock(spec=[])
        adapter = GeoSyncSystemAdapter(mock_system)

        adapter.start()

        assert adapter._started is True

    def test_start_with_live_loop(self) -> None:
        """Test start when system has live loop."""
        mock_system = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)

        adapter.start()

        assert adapter._started is True
        mock_system.ensure_live_loop.assert_called_once()

    def test_stop(self) -> None:
        """Test stop method."""
        mock_system = MagicMock()
        mock_system.live_loop = None
        adapter = GeoSyncSystemAdapter(mock_system)
        adapter._started = True

        adapter.stop()

        assert adapter._started is False

    def test_stop_with_live_loop(self) -> None:
        """Test stop with active live loop."""
        mock_system = MagicMock()
        mock_system.live_loop = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)
        adapter._started = True

        adapter.stop()

        assert adapter._started is False

    def test_health_check_uninitialized(self) -> None:
        """Test health check when not initialized."""
        mock_system = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)

        health = adapter.health_check()

        assert health.status == ComponentStatus.UNINITIALIZED
        assert health.healthy is False
        assert "not initialized" in health.message

    def test_health_check_initialized_not_started(self) -> None:
        """Test health check when initialized but not started."""
        mock_system = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)
        adapter._initialized = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.INITIALIZED
        assert health.healthy is True
        assert "not started" in health.message

    def test_health_check_running_healthy(self) -> None:
        """Test health check when running without errors."""
        mock_system = MagicMock()
        mock_system.last_ingestion_error = None
        mock_system.last_signal_error = None
        mock_system.last_execution_error = None
        adapter = GeoSyncSystemAdapter(mock_system)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.RUNNING
        assert health.healthy is True
        assert "operational" in health.message

    def test_health_check_with_errors(self) -> None:
        """Test health check with various errors."""
        mock_system = MagicMock()
        mock_system.last_ingestion_error = "Connection failed"
        mock_system.last_signal_error = None
        mock_system.last_execution_error = "Order rejected"
        adapter = GeoSyncSystemAdapter(mock_system)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert health.healthy is False
        assert "Ingestion" in health.message
        assert "Execution" in health.message

    def test_system_property(self) -> None:
        """Test system property access."""
        mock_system = MagicMock()
        adapter = GeoSyncSystemAdapter(mock_system)

        assert adapter.system == mock_system


class TestGeoSyncOrchestratorAdapter:
    """Tests for GeoSyncOrchestratorAdapter class."""

    def test_initialization(self) -> None:
        """Test adapter initialization."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)

        assert adapter._orchestrator == mock_orchestrator
        assert adapter._initialized is False
        assert adapter._started is False

    def test_initialize(self) -> None:
        """Test initialize method."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)

        adapter.initialize()

        assert adapter._initialized is True

    def test_start(self) -> None:
        """Test start method."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)

        adapter.start()

        assert adapter._started is True
        mock_orchestrator.ensure_live_loop.assert_called_once()

    def test_stop(self) -> None:
        """Test stop method."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)
        adapter._started = True

        adapter.stop()

        assert adapter._started is False

    def test_health_check_uninitialized(self) -> None:
        """Test health check when not initialized."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)

        health = adapter.health_check()

        assert health.status == ComponentStatus.UNINITIALIZED
        assert health.healthy is False

    def test_health_check_initialized_not_started(self) -> None:
        """Test health check when initialized but not started."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)
        adapter._initialized = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.INITIALIZED
        assert health.healthy is True

    def test_health_check_running_healthy(self) -> None:
        """Test health check when running without issues."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.fractal_regulator = None
        del mock_orchestrator.services  # Remove services attribute
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.RUNNING
        assert health.healthy is True

    def test_health_check_services_not_started(self) -> None:
        """Test health check when services not started."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.fractal_regulator = None
        mock_orchestrator.services._started = False
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert health.healthy is False
        assert "Services not started" in health.message

    def test_health_check_in_crisis(self) -> None:
        """Test health check when system is in crisis."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.fractal_regulator = True
        mock_orchestrator.is_system_in_crisis.return_value = True
        mock_metrics = MagicMock()
        mock_metrics.csi = 0.8
        mock_orchestrator.get_system_health_metrics.return_value = mock_metrics
        del mock_orchestrator.services
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert health.healthy is False
        assert "crisis" in health.message.lower()
        assert health.metrics.get("csi") == 0.8

    def test_health_check_in_crisis_no_metrics(self) -> None:
        """Test health check in crisis with no metrics available."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.fractal_regulator = True
        mock_orchestrator.is_system_in_crisis.return_value = True
        mock_orchestrator.get_system_health_metrics.return_value = None
        del mock_orchestrator.services
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)
        adapter._initialized = True
        adapter._started = True

        health = adapter.health_check()

        assert health.status == ComponentStatus.DEGRADED
        assert "N/A" in health.message

    def test_orchestrator_property(self) -> None:
        """Test orchestrator property access."""
        mock_orchestrator = MagicMock()
        adapter = GeoSyncOrchestratorAdapter(mock_orchestrator)

        assert adapter.orchestrator == mock_orchestrator


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_system_component_adapter(self) -> None:
        """Test create_system_component_adapter factory."""
        mock_system = MagicMock()

        adapter = create_system_component_adapter(mock_system)

        assert isinstance(adapter, GeoSyncSystemAdapter)
        assert adapter.system == mock_system

    def test_create_orchestrator_component_adapter(self) -> None:
        """Test create_orchestrator_component_adapter factory."""
        mock_orchestrator = MagicMock()

        adapter = create_orchestrator_component_adapter(mock_orchestrator)

        assert isinstance(adapter, GeoSyncOrchestratorAdapter)
        assert adapter.orchestrator == mock_orchestrator


class TestOrchestratorServicesHealthGuard:
    """The `hasattr(services, "_started") and not services._started` guard at adapters.py:155.

    A started orchestrator whose ServiceRegistry is NOT started is DEGRADED; if the registry IS
    started it must report RUNNING. Under `And -> Or` the guard fires whenever `services` merely
    HAS a `_started` attribute, so a fully-started system is misreported as DEGRADED. Nothing
    exercised the started-registry arm, so the mutant survived. Both arms are pinned here with a
    controlled fake (not MagicMock, whose auto-attributes make `_started` unconditionally truthy
    and hide the distinction).
    """

    class _Registry:
        def __init__(self, started: bool) -> None:
            self._started = started

    class _Orchestrator:
        def __init__(self, *, services_started: bool) -> None:
            self.services = TestOrchestratorServicesHealthGuard._Registry(services_started)
            self.fractal_regulator = None  # skip the crisis branch, reach the RUNNING return

    def _started_adapter(self, *, services_started: bool) -> GeoSyncOrchestratorAdapter:
        adapter = GeoSyncOrchestratorAdapter(self._Orchestrator(services_started=services_started))
        adapter._initialized = True
        adapter._started = True
        return adapter

    def test_running_registry_is_healthy(self) -> None:
        health = self._started_adapter(services_started=True).health_check()
        assert health.status == ComponentStatus.RUNNING, (
            "a started ServiceRegistry was misreported as DEGRADED"
        )
        assert health.healthy is True

    def test_unstarted_registry_is_degraded(self) -> None:
        health = self._started_adapter(services_started=False).health_check()
        assert health.status == ComponentStatus.DEGRADED
        assert health.healthy is False
        assert "not started" in health.message.lower()
