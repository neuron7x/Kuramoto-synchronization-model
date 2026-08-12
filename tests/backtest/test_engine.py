# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for backtest.engine module."""

from __future__ import annotations

import numpy as np
import pytest

from backtest.engine import (
    AntiLeakageConfig,
    DataValidationConfig,
    LatencyConfig,
    OrderBookConfig,
    PortfolioConstraints,
    Result,
    SlippageConfig,
)


class TestLatencyConfig:
    def test_defaults(self):
        cfg = LatencyConfig()
        assert cfg.signal_to_order == 0
        assert cfg.order_to_execution == 0
        assert cfg.execution_to_fill == 0

    def test_total_delay(self):
        cfg = LatencyConfig(signal_to_order=1, order_to_execution=2, execution_to_fill=3)
        assert cfg.total_delay == 6

    def test_total_delay_zero(self):
        cfg = LatencyConfig()
        assert cfg.total_delay == 0

    @pytest.mark.parametrize(
        "s,o,e,expected",
        [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1), (2, 3, 4, 9)],
    )
    def test_various_delays(self, s, o, e, expected):
        cfg = LatencyConfig(signal_to_order=s, order_to_execution=o, execution_to_fill=e)
        assert cfg.total_delay == expected


class TestOrderBookConfig:
    def test_defaults(self):
        cfg = OrderBookConfig()
        assert cfg.spread_bps == 0.0
        assert cfg.infinite_depth is True
        assert len(cfg.depth_profile) == 3

    def test_custom(self):
        cfg = OrderBookConfig(spread_bps=10.0, depth_profile=(1.0, 0.5), infinite_depth=False)
        assert cfg.spread_bps == 10.0
        assert cfg.infinite_depth is False


class TestSlippageConfig:
    def test_defaults(self):
        cfg = SlippageConfig()
        assert cfg.per_unit_bps == 0.0
        assert cfg.depth_impact_bps == 0.0
        assert cfg.stochastic_bps == 0.0

    def test_custom(self):
        cfg = SlippageConfig(per_unit_bps=5.0, depth_impact_bps=2.0)
        assert cfg.per_unit_bps == 5.0


class TestPortfolioConstraints:
    def test_defaults(self):
        cfg = PortfolioConstraints()
        assert cfg.max_gross_exposure is None
        assert cfg.max_net_exposure is None
        assert cfg.target_volatility is None
        assert cfg.volatility_lookback == 20

    def test_custom(self):
        cfg = PortfolioConstraints(max_gross_exposure=1e6, volatility_lookback=60)
        assert cfg.max_gross_exposure == 1e6
        assert cfg.volatility_lookback == 60


class TestDataValidationConfig:
    def test_defaults(self):
        cfg = DataValidationConfig()
        assert cfg.enabled is True
        assert cfg.allow_warnings is True
        assert cfg.skip_validation is False

    def test_skip(self):
        cfg = DataValidationConfig(skip_validation=True)
        assert cfg.skip_validation is True


class TestAntiLeakageConfig:
    def test_defaults(self):
        cfg = AntiLeakageConfig()
        assert cfg.enforce_signal_lag is False
        assert cfg.minimum_signal_delay == 1
        assert cfg.warn_on_potential_leakage is True

    def test_enforce(self):
        cfg = AntiLeakageConfig(enforce_signal_lag=True, minimum_signal_delay=3)
        assert cfg.enforce_signal_lag is True
        assert cfg.minimum_signal_delay == 3


class TestResult:
    def test_creation(self):
        r = Result(pnl=100.0, max_dd=-10.0, trades=50)
        assert r.pnl == 100.0
        assert r.max_dd == -10.0
        assert r.trades == 50
        assert r.equity_curve is None

    def test_with_equity_curve(self):
        curve = np.array([100.0, 101.0, 99.0, 105.0])
        r = Result(pnl=5.0, max_dd=-2.0, trades=3, equity_curve=curve)
        assert r.equity_curve is not None
        assert len(r.equity_curve) == 4

    def test_all_cost_fields(self):
        r = Result(
            pnl=50.0,
            max_dd=-5.0,
            trades=10,
            latency_steps=2,
            slippage_cost=1.5,
            commission_cost=3.0,
            spread_cost=2.0,
            financing_cost=0.5,
        )
        assert r.slippage_cost == 1.5
        assert r.commission_cost == 3.0
        assert r.spread_cost == 2.0
        assert r.financing_cost == 0.5
