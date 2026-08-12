# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.metrics — target uncovered lines."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from execution.metrics import (
    RiskMetrics,
    TradingModeMetrics,
    get_risk_metrics,
    get_trading_mode_metrics,
)

# ── Helpers to avoid global singleton collisions ────────────────────


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level singleton caches between tests."""
    import execution.metrics as mod

    old_risk = mod._GLOBAL_METRICS
    old_mode = mod._GLOBAL_MODE_METRICS
    mod._GLOBAL_METRICS = None
    mod._GLOBAL_MODE_METRICS = None
    yield
    mod._GLOBAL_METRICS = old_risk
    mod._GLOBAL_MODE_METRICS = old_mode


# ── RiskMetrics with prometheus available ───────────────────────────


class TestRiskMetricsWithPrometheus:
    @pytest.fixture()
    def registry(self):
        from prometheus_client import CollectorRegistry

        return CollectorRegistry()

    def test_construction(self, registry):
        m = RiskMetrics(registry=registry)
        assert m.enabled is True

    def test_record_kill_switch(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_kill_switch(True, env="test")
        m.record_kill_switch(False, env="test")

    def test_record_gross_exposure(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_gross_exposure(1234.5, env="test")

    def test_record_daily_drawdown(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_daily_drawdown(0.05, mode="percent", env="test")
        m.record_daily_drawdown(500.0, mode="notional", env="test")

    def test_record_circuit_state(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_circuit_state("closed")
        m.record_circuit_state("open")
        m.record_circuit_state("half_open")

    def test_record_rejection(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_rejection("max_notional")

    def test_record_circuit_trip(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_circuit_trip("drawdown")

    def test_record_open_orders(self, registry):
        m = RiskMetrics(registry=registry)
        m.record_open_orders(5, env="test")


# ── RiskMetrics with prometheus unavailable ─────────────────────────


class TestRiskMetricsDisabled:
    def test_all_methods_noop_when_disabled(self):
        with patch("execution.metrics.PROMETHEUS_AVAILABLE", False):
            m = RiskMetrics()
            assert m.enabled is False
            # All record methods should silently do nothing
            m.record_kill_switch(True)
            m.record_gross_exposure(100)
            m.record_daily_drawdown(0.1)
            m.record_circuit_state("open")
            m.record_rejection("test")
            m.record_circuit_trip("test")
            m.record_open_orders(3)


# ── get_risk_metrics singleton ──────────────────────────────────────


class TestGetRiskMetrics:
    def test_returns_same_instance(self):
        from prometheus_client import CollectorRegistry

        reg = CollectorRegistry()
        a = get_risk_metrics(registry=reg)
        b = get_risk_metrics(registry=reg)
        assert a is b

    def test_accepts_registry(self):
        from prometheus_client import CollectorRegistry

        reg = CollectorRegistry()
        m = get_risk_metrics(registry=reg)
        assert m is not None


# ── TradingModeMetrics with prometheus ──────────────────────────────


class TestTradingModeMetrics:
    @pytest.fixture()
    def registry(self):
        from prometheus_client import CollectorRegistry

        return CollectorRegistry()

    def test_construction(self, registry):
        m = TradingModeMetrics(registry=registry)
        assert m.enabled is True
        assert m.current_mode == "unknown"

    def test_set_mode_initial(self, registry):
        m = TradingModeMetrics(registry=registry)
        m.set_mode("BACKTEST", reason="initial")
        assert m.current_mode == "BACKTEST"

    def test_set_mode_transition(self, registry):
        m = TradingModeMetrics(registry=registry)
        m.set_mode("PAPER", reason="initial")
        m.set_mode("LIVE", reason="manual")
        assert m.current_mode == "LIVE"

    def test_record_transition_latency(self, registry):
        m = TradingModeMetrics(registry=registry)
        m.record_transition_latency("paper", "live", 0.05)

    def test_update_duration(self, registry):
        m = TradingModeMetrics(registry=registry)
        m.set_mode("LIVE")
        m.update_duration()

    def test_update_duration_unknown_noop(self, registry):
        m = TradingModeMetrics(registry=registry)
        m.update_duration()  # current_mode is "unknown", should be noop


# ── TradingModeMetrics disabled ─────────────────────────────────────


class TestTradingModeMetricsDisabled:
    def test_all_methods_noop_when_disabled(self):
        with patch("execution.metrics.PROMETHEUS_AVAILABLE", False):
            m = TradingModeMetrics()
            assert m.enabled is False
            m.set_mode("LIVE")
            m.record_transition_latency("PAPER", "LIVE", 0.1)
            m.update_duration()


# ── get_trading_mode_metrics singleton ──────────────────────────────


class TestGetTradingModeMetrics:
    def test_returns_same_instance(self):
        from prometheus_client import CollectorRegistry

        reg = CollectorRegistry()
        a = get_trading_mode_metrics(registry=reg)
        b = get_trading_mode_metrics(registry=reg)
        assert a is b

    def test_accepts_registry(self):
        from prometheus_client import CollectorRegistry

        reg = CollectorRegistry()
        m = get_trading_mode_metrics(registry=reg)
        assert m is not None
