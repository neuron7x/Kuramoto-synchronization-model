# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for risk and trading mode metrics in execution/metrics.py."""

from __future__ import annotations

import time

import pytest
from prometheus_client import CollectorRegistry

from execution.metrics import (
    RiskMetrics,
    TradingModeMetrics,
    get_risk_metrics,
    get_trading_mode_metrics,
)


def _sample_value(
    registry: CollectorRegistry, name: str, labels: dict[str, str] | None = None
) -> float | None:
    """Helper to extract metric samples from the registry."""
    return registry.get_sample_value(name, labels or {})


class TestRiskMetrics:
    """Tests for RiskMetrics class."""

    def test_kill_switch_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_kill_switch(True, env="prod")
        value = _sample_value(registry, "geosync_risk_kill_switch", {"env": "prod"})
        assert value == 1.0

        metrics.record_kill_switch(False, env="prod")
        value = _sample_value(registry, "geosync_risk_kill_switch", {"env": "prod"})
        assert value == 0.0

    def test_gross_exposure_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_gross_exposure(50000.0, env="staging")
        value = _sample_value(registry, "geosync_risk_gross_exposure", {"env": "staging"})
        assert value == 50000.0

    def test_daily_drawdown_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_daily_drawdown(5.5, mode="percent", env="prod")
        value = _sample_value(
            registry,
            "geosync_risk_daily_drawdown",
            {"env": "prod", "mode": "percent"},
        )
        assert value == 5.5

    def test_circuit_state_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_circuit_state("open")
        open_value = _sample_value(registry, "geosync_risk_circuit_state", {"state": "open"})
        closed_value = _sample_value(registry, "geosync_risk_circuit_state", {"state": "closed"})
        half_open_value = _sample_value(
            registry, "geosync_risk_circuit_state", {"state": "half_open"}
        )

        assert open_value == 1.0
        assert closed_value == 0.0
        assert half_open_value == 0.0

        # Now switch to closed
        metrics.record_circuit_state("closed")
        open_value = _sample_value(registry, "geosync_risk_circuit_state", {"state": "open"})
        closed_value = _sample_value(registry, "geosync_risk_circuit_state", {"state": "closed"})
        assert open_value == 0.0
        assert closed_value == 1.0

    def test_rejection_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_rejection("position_limit")
        metrics.record_rejection("position_limit")
        metrics.record_rejection("notional_limit")

        position_count = _sample_value(
            registry, "geosync_risk_rejections_total", {"reason": "position_limit"}
        )
        notional_count = _sample_value(
            registry, "geosync_risk_rejections_total", {"reason": "notional_limit"}
        )

        assert position_count == 2.0
        assert notional_count == 1.0

    def test_circuit_trip_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_circuit_trip("high_volatility")
        value = _sample_value(
            registry,
            "geosync_risk_circuit_trips_total",
            {"reason": "high_volatility"},
        )
        assert value == 1.0

    def test_open_orders_recording(self) -> None:
        registry = CollectorRegistry()
        metrics = RiskMetrics(registry)

        metrics.record_open_orders(15, env="prod")
        value = _sample_value(registry, "geosync_risk_open_orders", {"env": "prod"})
        assert value == 15.0

    def test_disabled_when_prometheus_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr("execution.metrics.PROMETHEUS_AVAILABLE", False)
        metrics = RiskMetrics()
        assert not metrics.enabled

        # Should not raise
        metrics.record_kill_switch(True)
        metrics.record_gross_exposure(100.0)
        metrics.record_rejection("test")


class TestTradingModeMetrics:
    """Tests for TradingModeMetrics class."""

    def test_set_mode_initial(self) -> None:
        registry = CollectorRegistry()
        metrics = TradingModeMetrics(registry)

        metrics.set_mode("LIVE", reason="initial")

        live_value = _sample_value(registry, "geosync_trading_mode", {"mode": "LIVE"})
        paper_value = _sample_value(registry, "geosync_trading_mode", {"mode": "PAPER"})
        backtest_value = _sample_value(registry, "geosync_trading_mode", {"mode": "BACKTEST"})

        assert live_value == 1.0
        assert paper_value == 0.0
        assert backtest_value == 0.0
        assert metrics.current_mode == "LIVE"

    def test_mode_transition(self) -> None:
        registry = CollectorRegistry()
        metrics = TradingModeMetrics(registry)

        # Set initial mode
        metrics.set_mode("BACKTEST", reason="initial")
        assert metrics.current_mode == "BACKTEST"

        # Transition to PAPER
        metrics.set_mode("PAPER", reason="manual")

        paper_value = _sample_value(registry, "geosync_trading_mode", {"mode": "PAPER"})
        backtest_value = _sample_value(registry, "geosync_trading_mode", {"mode": "BACKTEST"})

        assert paper_value == 1.0
        assert backtest_value == 0.0
        assert metrics.current_mode == "PAPER"

        # Check transition was recorded
        transition_count = _sample_value(
            registry,
            "geosync_trading_mode_transitions_total",
            {"from_mode": "BACKTEST", "to_mode": "PAPER", "reason": "manual"},
        )
        assert transition_count == 1.0

    def test_mode_duration_tracking(self) -> None:
        registry = CollectorRegistry()
        metrics = TradingModeMetrics(registry)

        metrics.set_mode("LIVE", reason="initial")
        time.sleep(0.1)  # Small delay to ensure duration > 0
        metrics.update_duration()

        duration = _sample_value(
            registry, "geosync_trading_mode_duration_seconds", {"mode": "LIVE"}
        )
        assert duration is not None
        assert duration >= 0.05  # Should be at least 50ms

    def test_transition_latency(self) -> None:
        registry = CollectorRegistry()
        metrics = TradingModeMetrics(registry)

        metrics.record_transition_latency("PAPER", "LIVE", 0.5)

        latency_count = _sample_value(
            registry,
            "geosync_trading_mode_transition_latency_seconds_count",
            {"from_mode": "PAPER", "to_mode": "LIVE"},
        )
        latency_sum = _sample_value(
            registry,
            "geosync_trading_mode_transition_latency_seconds_sum",
            {"from_mode": "PAPER", "to_mode": "LIVE"},
        )

        assert latency_count == 1.0
        assert latency_sum == pytest.approx(0.5)

    def test_case_normalization(self) -> None:
        registry = CollectorRegistry()
        metrics = TradingModeMetrics(registry)

        # Mode should be uppercased
        metrics.set_mode("live", reason="test")
        assert metrics.current_mode == "LIVE"

        live_value = _sample_value(registry, "geosync_trading_mode", {"mode": "LIVE"})
        assert live_value == 1.0

    def test_disabled_when_prometheus_unavailable(self, monkeypatch) -> None:
        monkeypatch.setattr("execution.metrics.PROMETHEUS_AVAILABLE", False)
        metrics = TradingModeMetrics()
        assert not metrics.enabled

        # Should not raise
        metrics.set_mode("LIVE")
        metrics.record_transition_latency("PAPER", "LIVE", 0.1)
        metrics.update_duration()


class TestGlobalMetricsSingleton:
    """Tests for global metrics singleton functions."""

    def test_get_risk_metrics_returns_same_instance(self) -> None:
        import execution.metrics as m

        # Reset global state
        m._GLOBAL_METRICS = None

        registry = CollectorRegistry()
        metrics1 = get_risk_metrics(registry)
        metrics2 = get_risk_metrics()

        assert metrics1 is metrics2

        # Cleanup
        m._GLOBAL_METRICS = None

    def test_get_trading_mode_metrics_returns_same_instance(self) -> None:
        import execution.metrics as m

        # Reset global state
        m._GLOBAL_MODE_METRICS = None

        registry = CollectorRegistry()
        metrics1 = get_trading_mode_metrics(registry)
        metrics2 = get_trading_mode_metrics()

        assert metrics1 is metrics2

        # Cleanup
        m._GLOBAL_MODE_METRICS = None
