"""Regression tests for namespaced TradePulse package exports."""

from __future__ import annotations

import importlib


def test_backtest_namespace_reexports_public_api():
    raw_backtest = importlib.import_module("backtest")
    namespaced_backtest = importlib.import_module("tradepulse.backtest")

    assert hasattr(namespaced_backtest, "LatencyConfig")
    assert namespaced_backtest.LatencyConfig is raw_backtest.LatencyConfig

    alias_module = importlib.import_module("tradepulse.backtest.engine")
    real_module = importlib.import_module("backtest.engine")
    assert alias_module is real_module

    assert "SyntheticScenario" in dir(namespaced_backtest)


def test_execution_namespace_reexports_public_api():
    raw_execution = importlib.import_module("execution")
    namespaced_execution = importlib.import_module("tradepulse.execution")

    assert hasattr(namespaced_execution, "OrderManagementSystem")
    assert namespaced_execution.OrderManagementSystem is raw_execution.OrderManagementSystem

    router_alias = importlib.import_module("tradepulse.execution.router")
    router_real = importlib.import_module("execution.router")
    assert router_alias is router_real

    assert "ResilientExecutionRouter" in namespaced_execution.__all__
