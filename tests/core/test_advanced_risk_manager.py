# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.risk_monitoring.advanced_risk_manager module."""

from __future__ import annotations

import pytest

from core.risk_monitoring.advanced_risk_manager import (
    FreeEnergyState,
    LiquidityMetrics,
    MarketDepthData,
    RiskState,
    StressResponseProtocol,
)


class TestStressResponseProtocol:
    def test_values(self):
        assert StressResponseProtocol.NORMAL.value == "normal"
        assert StressResponseProtocol.DEFENSIVE.value == "defensive"
        assert StressResponseProtocol.PROTECTIVE.value == "protective"
        assert StressResponseProtocol.HALT.value == "halt"
        assert StressResponseProtocol.EMERGENCY.value == "emergency"

    def test_ordering_lt(self):
        assert StressResponseProtocol.NORMAL < StressResponseProtocol.DEFENSIVE
        assert StressResponseProtocol.DEFENSIVE < StressResponseProtocol.HALT

    def test_ordering_gt(self):
        assert StressResponseProtocol.EMERGENCY > StressResponseProtocol.NORMAL
        assert StressResponseProtocol.HALT > StressResponseProtocol.DEFENSIVE

    def test_ordering_le_ge(self):
        assert StressResponseProtocol.NORMAL <= StressResponseProtocol.NORMAL
        assert StressResponseProtocol.EMERGENCY >= StressResponseProtocol.HALT

    def test_cross_type_comparison_returns_not_implemented(self):
        # Comparing with non-StressResponseProtocol returns NotImplemented
        assert (StressResponseProtocol.NORMAL.__lt__("normal")) is NotImplemented
        assert (StressResponseProtocol.NORMAL.__gt__(42)) is NotImplemented


class TestRiskState:
    def test_values(self):
        assert RiskState.OPTIMAL.value == "optimal"
        assert RiskState.STABLE.value == "stable"
        assert RiskState.ELEVATED.value == "elevated"
        assert RiskState.STRESSED.value == "stressed"
        assert RiskState.CRITICAL.value == "critical"

    def test_ordering(self):
        assert RiskState.OPTIMAL < RiskState.STABLE
        assert RiskState.STABLE < RiskState.ELEVATED
        assert RiskState.CRITICAL > RiskState.STRESSED

    def test_le_ge(self):
        assert RiskState.OPTIMAL <= RiskState.OPTIMAL
        assert RiskState.CRITICAL >= RiskState.CRITICAL

    def test_cross_type_not_implemented(self):
        assert (RiskState.STABLE.__lt__("stable")) is NotImplemented


class TestMarketDepthData:
    def test_defaults(self):
        d = MarketDepthData()
        assert d.bids == []
        assert d.asks == []
        assert d.symbol == ""

    def test_with_data(self):
        d = MarketDepthData(
            bids=[(100.0, 1000.0), (99.5, 2000.0)],
            asks=[(100.5, 1500.0), (101.0, 2500.0)],
            symbol="BTCUSD",
        )
        assert len(d.bids) == 2
        assert d.symbol == "BTCUSD"

    def test_get_mid_price(self):
        d = MarketDepthData(bids=[(100.0, 1000.0)], asks=[(100.5, 1500.0)])
        assert d.get_mid_price() == pytest.approx(100.25)

    def test_get_mid_price_empty_bids(self):
        d = MarketDepthData(asks=[(100.5, 1500.0)])
        assert d.get_mid_price() is None

    def test_get_mid_price_empty_asks(self):
        d = MarketDepthData(bids=[(100.0, 1000.0)])
        assert d.get_mid_price() is None

    def test_get_mid_price_zero_bid(self):
        d = MarketDepthData(bids=[(0.0, 1000.0)], asks=[(100.0, 500.0)])
        assert d.get_mid_price() is None

    def test_spread_bps_normal(self):
        d = MarketDepthData(bids=[(100.0, 1000.0)], asks=[(100.1, 1000.0)])
        # spread = 0.1, bps = 0.1/100 * 10000 = 10
        assert d.get_spread_bps() == pytest.approx(10.0)

    def test_spread_bps_empty_raises_inf(self):
        d = MarketDepthData()
        assert d.get_spread_bps() == float("inf")

    def test_spread_bps_zero_bid(self):
        d = MarketDepthData(bids=[(0.0, 100)], asks=[(1.0, 100)])
        assert d.get_spread_bps() == float("inf")


class TestLiquidityMetrics:
    def test_defaults(self):
        m = LiquidityMetrics()
        assert m.bid_depth_value == 0.0
        assert m.ask_depth_value == 0.0
        assert m.imbalance_ratio == 0.0
        assert m.liquidity_score == 1.0

    def test_custom_values(self):
        m = LiquidityMetrics(
            bid_depth_value=50000.0,
            ask_depth_value=45000.0,
            imbalance_ratio=0.1,
            spread_bps=5.0,
            liquidity_score=0.8,
        )
        assert m.bid_depth_value == 50000.0
        assert m.imbalance_ratio == 0.1

    def test_to_dict(self):
        m = LiquidityMetrics(bid_depth_value=1000.0, spread_bps=10.0)
        d = m.to_dict()
        assert d["bid_depth_value"] == 1000.0
        assert d["spread_bps"] == 10.0
        assert "timestamp" in d


class TestFreeEnergyState:
    def test_defaults(self):
        fe = FreeEnergyState()
        assert fe.current_free_energy == 0.0
        assert fe.precision == 1.0
        assert fe.stability_metric == 1.0
        assert fe.is_monotonic is True

    def test_custom(self):
        fe = FreeEnergyState(
            current_free_energy=0.5,
            prediction_error=0.1,
            precision=2.0,
            entropy=0.3,
        )
        assert fe.current_free_energy == 0.5
        assert fe.prediction_error == 0.1

    def test_to_dict(self):
        fe = FreeEnergyState(current_free_energy=0.7, entropy=0.2)
        d = fe.to_dict()
        assert d["current_free_energy"] == 0.7
        assert d["entropy"] == 0.2
        assert d["is_monotonic"] is True
