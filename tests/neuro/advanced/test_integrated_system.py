# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the integrated neuro trading system."""

from __future__ import annotations

import numpy as np
import pytest

from core.neuro.advanced import IntegratedNeuroTradingSystem, NeuroAdvancedConfig


@pytest.mark.asyncio
async def test_integrated_system_produces_decision() -> None:
    cfg = NeuroAdvancedConfig()
    system = IntegratedNeuroTradingSystem(cfg)

    prices = np.maximum(1.0, np.cumsum(np.random.default_rng(42).normal(0.0, 0.5, size=64)) + 100)
    market_data = {"series": {"EURUSD": prices.tolist()}}
    portfolio_state = {"strategies": ["fractal_momentum", "fractal_mean_reversion"]}

    result = await system.process_trading_cycle(market_data, portfolio_state)

    assert "final_decision" in result
    assert "modulated_candidates" in result
    assert result["fractal_features"]["n"] == len(prices)
    assert "asset_fractal_features" in result
    assert set(result["asset_fractal_features"].keys()) == {"EURUSD"}


@pytest.mark.asyncio
async def test_integrated_system_updates_learning_state() -> None:
    system = IntegratedNeuroTradingSystem()
    rng = np.random.default_rng(7)

    prices = np.maximum(1.0, np.cumsum(rng.normal(0.0, 0.5, size=64)) + 50)
    market_data = {"series": {"BTC": prices.tolist()}}
    portfolio_state = {"strategies": ["fractal_momentum"]}
    cycle = await system.process_trading_cycle(market_data, portfolio_state)

    decision = cycle["final_decision"]
    execution = {
        "trades": [
            {
                "asset": decision.get("asset", "BTC"),
                "strategy": decision.get("strategy", "fractal_momentum"),
                "pnl_percentage": 0.01,
                "signal_strength": 0.7,
                "expected_reward": 0.005,
            }
        ],
        "volatility": cycle["fractal_features"]["volatility"],
        "trend_strength": cycle["fractal_features"]["trend_strength"],
        "regime": cycle["fractal_features"]["regime"],
        "context_fit": 1.0,
    }

    updates = await system.update_from_execution(execution)
    assert "updates" in updates
    assert "dpa" in updates["updates"]
    assert "alerts" in updates
