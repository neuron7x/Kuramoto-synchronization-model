# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.risk.advanced — target uncovered lines."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execution.risk.advanced import (
    AdvancedRiskController,
    CorrelationLimitGuard,
    DrawdownBreaker,
    KellyCriterionPositionSizer,
    LiquidationCascadePreventer,
    MarginMonitor,
    MarketCondition,
    PositionRequest,
    RegimeAdaptiveExposureGuard,
    RiskMetricsCalculator,
    RiskParityAllocator,
    TimeWeightedExposureTracker,
    VolatilityAdjustedSizer,
    VolatilityRegime,
)

# ── RegimeAdaptiveExposureGuard ─────────────────────────────────────


class TestRegimeAdaptiveExposureGuard:
    def test_init_validation(self):
        with pytest.raises(ValueError, match="calm_threshold"):
            RegimeAdaptiveExposureGuard(calm_threshold=0)
        with pytest.raises(ValueError, match="thresholds"):
            RegimeAdaptiveExposureGuard(calm_threshold=0.05, stressed_threshold=0.01)
        with pytest.raises(ValueError, match="multipliers"):
            RegimeAdaptiveExposureGuard(calm_multiplier=-1)
        with pytest.raises(ValueError, match="half_life"):
            RegimeAdaptiveExposureGuard(half_life_seconds=0)
        with pytest.raises(ValueError, match="min_samples"):
            RegimeAdaptiveExposureGuard(min_samples=0)
        with pytest.raises(ValueError, match="cooldown"):
            RegimeAdaptiveExposureGuard(cooldown_seconds=-1)

    def test_regime_unknown_symbol_returns_normal(self):
        guard = RegimeAdaptiveExposureGuard()
        assert guard.regime("UNKNOWN") == VolatilityRegime.NORMAL

    def test_multiplier_unknown_symbol_returns_one(self):
        guard = RegimeAdaptiveExposureGuard()
        assert guard.multiplier("UNKNOWN") == 1.0

    def test_calm_regime_after_low_vol(self):
        guard = RegimeAdaptiveExposureGuard(min_samples=1)
        for i in range(10):
            guard.observe("BTC", 0.001, timestamp=float(i))
        assert guard.regime("BTC") == VolatilityRegime.CALM
        assert guard.multiplier("BTC") == 1.1

    def test_normal_regime(self):
        guard = RegimeAdaptiveExposureGuard(min_samples=1)
        for i in range(10):
            guard.observe("BTC", 0.01, timestamp=float(i))
        assert guard.regime("BTC") == VolatilityRegime.NORMAL
        assert guard.multiplier("BTC") == 1.0

    def test_stressed_regime(self):
        guard = RegimeAdaptiveExposureGuard(min_samples=1)
        for i in range(10):
            guard.observe("BTC", 0.03, timestamp=float(i))
        assert guard.regime("BTC") == VolatilityRegime.STRESSED

    def test_critical_regime(self):
        guard = RegimeAdaptiveExposureGuard(min_samples=1)
        for i in range(10):
            guard.observe("BTC", 0.05, timestamp=float(i))
        assert guard.regime("BTC") == VolatilityRegime.CRITICAL

    def test_cooldown_prevents_downgrade(self):
        guard = RegimeAdaptiveExposureGuard(
            min_samples=1,
            cooldown_seconds=100.0,
        )
        # Move to stressed
        for i in range(5):
            guard.observe("BTC", 0.03, timestamp=float(i))
        assert guard.regime("BTC") == VolatilityRegime.STRESSED
        # Low vol but within cooldown -> stays stressed
        regime = guard.observe("BTC", 0.001, timestamp=6.0)
        assert regime == VolatilityRegime.STRESSED

    def test_cooldown_expired_allows_downgrade(self):
        guard = RegimeAdaptiveExposureGuard(
            min_samples=1,
            cooldown_seconds=5.0,
        )
        for i in range(5):
            guard.observe("BTC", 0.03, timestamp=float(i))
        # After cooldown + enough calm observations to decay EWMA
        for i in range(20):
            guard.observe("BTC", 0.001, timestamp=100.0 + float(i))
        assert guard.regime("BTC") in (VolatilityRegime.CALM, VolatilityRegime.NORMAL)

    def test_below_min_samples_returns_previous(self):
        guard = RegimeAdaptiveExposureGuard(min_samples=5)
        r = guard.observe("X", 0.001, timestamp=0.0)
        assert r == VolatilityRegime.NORMAL  # default


# ── MarketCondition ─────────────────────────────────────────────────


class TestMarketCondition:
    def test_valid(self):
        mc = MarketCondition(symbol="BTC", price=100, volatility=0.2)
        assert mc.symbol == "BTC"

    def test_price_zero_raises(self):
        with pytest.raises(ValueError, match="price"):
            MarketCondition(symbol="BTC", price=0, volatility=0.2)

    def test_negative_volatility_raises(self):
        with pytest.raises(ValueError, match="volatility"):
            MarketCondition(symbol="BTC", price=100, volatility=-0.1)

    def test_win_prob_out_of_range(self):
        with pytest.raises(ValueError, match="win_probability"):
            MarketCondition(symbol="BTC", price=100, volatility=0.2, win_probability=0.0)
        with pytest.raises(ValueError, match="win_probability"):
            MarketCondition(symbol="BTC", price=100, volatility=0.2, win_probability=1.0)

    def test_payoff_ratio_zero_raises(self):
        with pytest.raises(ValueError, match="payoff_ratio"):
            MarketCondition(symbol="BTC", price=100, volatility=0.2, payoff_ratio=0)


# ── KellyCriterionPositionSizer ─────────────────────────────────────


class TestKelly:
    def test_fraction_positive_edge(self):
        sizer = KellyCriterionPositionSizer(max_leverage=3.0, drawdown_buffer=0.5)
        mc = MarketCondition(
            symbol="BTC",
            price=100,
            volatility=0.2,
            win_probability=0.6,
            payoff_ratio=2.0,
        )
        f = sizer.fraction(mc)
        assert 0.0 <= f <= 3.0

    def test_fraction_negative_edge(self):
        sizer = KellyCriterionPositionSizer()
        mc = MarketCondition(
            symbol="BTC",
            price=100,
            volatility=0.2,
            win_probability=0.3,
            payoff_ratio=1.0,
        )
        assert sizer.fraction(mc) == 0.0

    def test_missing_win_prob_raises(self):
        sizer = KellyCriterionPositionSizer()
        mc = MarketCondition(symbol="BTC", price=100, volatility=0.2)
        with pytest.raises(ValueError, match="win_probability"):
            sizer.fraction(mc)

    def test_max_leverage_clamped(self):
        sizer = KellyCriterionPositionSizer(max_leverage=0.5, drawdown_buffer=1.0)
        mc = MarketCondition(
            symbol="BTC",
            price=100,
            volatility=0.2,
            win_probability=0.9,
            payoff_ratio=3.0,
        )
        assert sizer.fraction(mc) <= 1.0  # max_leverage clamped to 1.0


# ── VolatilityAdjustedSizer ─────────────────────────────────────────


class TestVolSizer:
    def test_zero_vol_returns_ceiling(self):
        sizer = VolatilityAdjustedSizer(target_volatility=0.15, ceiling=5.0)
        mc = MarketCondition(symbol="X", price=100, volatility=0.0)
        assert sizer.scaling_factor(mc) == 5.0

    def test_normal_vol(self):
        sizer = VolatilityAdjustedSizer(target_volatility=0.15)
        mc = MarketCondition(symbol="X", price=100, volatility=0.15)
        assert abs(sizer.scaling_factor(mc) - 1.0) < 1e-9

    def test_high_vol_floors(self):
        sizer = VolatilityAdjustedSizer(target_volatility=0.15, floor=0.05)
        mc = MarketCondition(symbol="X", price=100, volatility=100.0)
        assert sizer.scaling_factor(mc) == 0.05

    def test_init_validation(self):
        with pytest.raises(ValueError, match="target_volatility"):
            VolatilityAdjustedSizer(target_volatility=0)


# ── RiskMetricsCalculator ──────────────────────────────────────────


class TestRiskMetrics:
    def test_var_empty_returns_zero(self):
        calc = RiskMetricsCalculator()
        assert calc.value_at_risk([]) == 0.0

    def test_cvar_empty_returns_zero(self):
        calc = RiskMetricsCalculator()
        assert calc.conditional_value_at_risk([]) == 0.0

    def test_var_all_positive_returns(self):
        calc = RiskMetricsCalculator()
        assert calc.value_at_risk([0.01, 0.02, 0.03]) == 0.0

    def test_cvar_all_positive_returns(self):
        calc = RiskMetricsCalculator()
        assert calc.conditional_value_at_risk([0.01, 0.02, 0.03]) == 0.0

    def test_var_with_losses(self):
        returns = [
            -0.05,
            -0.03,
            -0.01,
            0.02,
            0.04,
            -0.02,
            0.01,
            -0.04,
            0.03,
            0.05,
            -0.06,
            0.02,
            -0.01,
            0.04,
            -0.03,
            0.01,
            -0.02,
            0.03,
            -0.05,
            0.01,
        ]
        calc = RiskMetricsCalculator(confidence=0.95)
        var = calc.value_at_risk(returns)
        assert var > 0

    def test_cvar_with_losses(self):
        returns = [
            -0.05,
            -0.03,
            -0.01,
            0.02,
            0.04,
            -0.02,
            0.01,
            -0.04,
            0.03,
            0.05,
            -0.06,
            0.02,
            -0.01,
            0.04,
            -0.03,
            0.01,
        ]
        calc = RiskMetricsCalculator(confidence=0.95)
        cvar = calc.conditional_value_at_risk(returns)
        assert cvar > 0

    def test_horizon_days_scaling(self):
        returns = [-0.05, -0.03, 0.02, -0.01, -0.04]
        calc = RiskMetricsCalculator()
        var1 = calc.value_at_risk(returns, horizon_days=1)
        var5 = calc.value_at_risk(returns, horizon_days=5)
        assert var5 > var1

    def test_confidence_validation(self):
        with pytest.raises(ValueError, match="confidence"):
            RiskMetricsCalculator(confidence=0.0)
        with pytest.raises(ValueError, match="confidence"):
            RiskMetricsCalculator(confidence=1.0)


# ── MarginMonitor ───────────────────────────────────────────────────


class TestMarginMonitor:
    def test_within_limit(self):
        mm = MarginMonitor(margin_limit=0.8, maintenance_margin=0.9)
        assert mm.update(80, 200) is True
        assert mm.utilisation == 80 / 200

    def test_exceeds_limit(self):
        mm = MarginMonitor(margin_limit=0.5, maintenance_margin=0.5)
        assert mm.update(200, 100) is False

    def test_zero_equity_raises(self):
        mm = MarginMonitor(margin_limit=0.8, maintenance_margin=0.9)
        with pytest.raises(ValueError, match="account_equity"):
            mm.update(10, 0)

    def test_init_validation(self):
        with pytest.raises(ValueError, match="margin_limit"):
            MarginMonitor(margin_limit=0, maintenance_margin=0.5)
        with pytest.raises(ValueError, match="maintenance_margin"):
            MarginMonitor(margin_limit=0.5, maintenance_margin=0)


# ── CorrelationLimitGuard ───────────────────────────────────────────


class TestCorrelationGuard:
    def test_within_limits(self):
        corr = {("BTC", "ETH"): 0.5, ("ETH", "BTC"): 0.5}
        guard = CorrelationLimitGuard(corr, max_exposure=200)
        assert guard.within_limits({"BTC": 100, "ETH": 50}) is True

    def test_exceeds_limits(self):
        corr = {("BTC", "ETH"): 0.9, ("ETH", "BTC"): 0.9}
        guard = CorrelationLimitGuard(corr, max_exposure=10)
        assert guard.within_limits({"BTC": 100, "ETH": 100}) is False

    def test_effective_exposure_positive(self):
        corr = {("A", "B"): 0.3, ("B", "A"): 0.3}
        guard = CorrelationLimitGuard(corr, max_exposure=1000)
        exp = guard.effective_exposure({"A": 50, "B": 50})
        assert exp > 0


# ── DrawdownBreaker ─────────────────────────────────────────────────


class TestDrawdownBreaker:
    def test_no_drawdown_ok(self):
        db = DrawdownBreaker(max_drawdown=0.15)
        assert db.record_equity(100) is True
        assert db.record_equity(110) is True
        assert db.current_drawdown == 0.0

    def test_drawdown_trips(self):
        db = DrawdownBreaker(max_drawdown=0.10)
        db.record_equity(100)
        assert db.record_equity(85) is False

    def test_equity_zero_raises(self):
        db = DrawdownBreaker()
        with pytest.raises(ValueError, match="equity"):
            db.record_equity(0)

    def test_init_validation(self):
        with pytest.raises(ValueError, match="max_drawdown"):
            DrawdownBreaker(max_drawdown=0)
        with pytest.raises(ValueError, match="max_drawdown"):
            DrawdownBreaker(max_drawdown=1.0)


# ── TimeWeightedExposureTracker ─────────────────────────────────────


class TestExposureTracker:
    def test_first_update(self):
        tracker = TimeWeightedExposureTracker()
        exp = tracker.update(100, 1000.0)
        assert exp == 100

    def test_decay(self):
        tracker = TimeWeightedExposureTracker(half_life_seconds=10.0)
        tracker.update(100, 0.0)
        exp = tracker.update(0, 100.0)
        assert exp < 100  # decayed

    def test_property(self):
        tracker = TimeWeightedExposureTracker()
        assert tracker.exposure == 0.0
        tracker.update(50, 0.0)
        assert tracker.exposure == 50.0

    def test_init_validation(self):
        with pytest.raises(ValueError, match="half_life"):
            TimeWeightedExposureTracker(half_life_seconds=0)


# ── RiskParityAllocator ────────────────────────────────────────────


class TestRiskParity:
    def test_equal_vol(self):
        allocator = RiskParityAllocator()
        w = allocator.weights({"A": 0.2, "B": 0.2})
        assert abs(w["A"] - w["B"]) < 1e-9

    def test_zero_vol_excluded(self):
        allocator = RiskParityAllocator()
        w = allocator.weights({"A": 0.2, "B": 0.0})
        assert "B" not in w  # zero vol excluded from inv_vols

    def test_all_zero_vol(self):
        allocator = RiskParityAllocator()
        w = allocator.weights({"A": 0.0, "B": 0.0})
        assert w["A"] == 0.0

    def test_min_weight(self):
        allocator = RiskParityAllocator(minimum_weight=0.3)
        w = allocator.weights({"A": 0.1, "B": 0.5})
        for v in w.values():
            assert v >= 0.3


# ── LiquidationCascadePreventer ─────────────────────────────────────


class TestLiquidationCascade:
    def test_valid(self):
        preventer = LiquidationCascadePreventer(
            liquidity_provider=lambda s: 1000,
            max_fraction=0.1,
        )
        assert preventer.validate({"BTC": 50}) is True

    def test_exceeds_fraction(self):
        preventer = LiquidationCascadePreventer(
            liquidity_provider=lambda s: 100,
            max_fraction=0.1,
        )
        assert preventer.validate({"BTC": 50}) is False

    def test_zero_liquidity(self):
        preventer = LiquidationCascadePreventer(
            liquidity_provider=lambda s: 0,
            max_fraction=0.1,
        )
        assert preventer.validate({"BTC": 10}) is False


# ── AdvancedRiskController ──────────────────────────────────────────


def _build_controller(*, with_regime: bool = False) -> AdvancedRiskController:
    regime = RegimeAdaptiveExposureGuard(min_samples=1) if with_regime else None
    return AdvancedRiskController(
        capital=100_000,
        margin_monitor=MarginMonitor(margin_limit=0.9, maintenance_margin=0.95),
        correlation_guard=CorrelationLimitGuard({}, max_exposure=500_000),
        drawdown_breaker=DrawdownBreaker(max_drawdown=0.2),
        exposure_tracker=TimeWeightedExposureTracker(),
        liquidation_guard=LiquidationCascadePreventer(
            liquidity_provider=lambda s: 1_000_000,
            max_fraction=0.5,
        ),
        risk_metrics=RiskMetricsCalculator(),
        kelly_sizer=KellyCriterionPositionSizer(),
        vol_sizer=VolatilityAdjustedSizer(),
        regime_guard=regime,
    )


class TestAdvancedRiskController:
    def test_init_validation(self):
        with pytest.raises(ValueError, match="capital"):
            AdvancedRiskController(
                capital=0,
                margin_monitor=MarginMonitor(0.9, 0.9),
                correlation_guard=CorrelationLimitGuard({}, 1),
                drawdown_breaker=DrawdownBreaker(),
                exposure_tracker=TimeWeightedExposureTracker(),
                liquidation_guard=LiquidationCascadePreventer(lambda s: 1),
                risk_metrics=RiskMetricsCalculator(),
                kelly_sizer=KellyCriterionPositionSizer(),
                vol_sizer=VolatilityAdjustedSizer(),
            )

    def test_register_market_condition(self):
        ctrl = _build_controller()
        mc = MarketCondition(
            symbol="BTC",
            price=50000,
            volatility=0.3,
            win_probability=0.55,
            payoff_ratio=2.0,
        )
        ctrl.register_market_condition(mc)
        assert ctrl.state.market_data["BTC"] is mc

    def test_evaluate_order_passes(self):
        ctrl = _build_controller()
        mc = MarketCondition(
            symbol="BTC",
            price=50000,
            volatility=0.3,
            win_probability=0.55,
            payoff_ratio=2.0,
        )
        ctrl.register_market_condition(mc)
        req = PositionRequest(symbol="BTC", notional=100)
        result = ctrl.evaluate_order(req, account_equity=100_000)
        assert isinstance(result, bool)

    def test_evaluate_order_missing_market_raises(self):
        ctrl = _build_controller()
        req = PositionRequest(symbol="XYZ", notional=100)
        with pytest.raises(ValueError, match="Missing market data"):
            ctrl.evaluate_order(req, account_equity=100_000)

    def test_record_return_scalars(self):
        ctrl = _build_controller(with_regime=True)
        ctrl.record_return("BTC", [0.01, -0.02, 0.005])
        assert len(ctrl.state.returns_history["BTC"]) == 3

    def test_record_return_tuples(self):
        ctrl = _build_controller(with_regime=True)
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ctrl.record_return("BTC", [(0.01, ts), (-0.02, ts)])
        assert len(ctrl.state.returns_history["BTC"]) == 2

    def test_record_return_invalid_tuple_raises(self):
        ctrl = _build_controller()
        with pytest.raises(ValueError, match="tuples must contain"):
            ctrl.record_return("BTC", [(0.01, "ts", "extra")])

    def test_record_return_invalid_timestamp_type_raises(self):
        ctrl = _build_controller()
        with pytest.raises(TypeError, match="timestamp must be"):
            ctrl.record_return("BTC", [(0.01, "not-a-datetime")])

    def test_portfolio_var_and_cvar(self):
        ctrl = _build_controller()
        ctrl.record_return(
            "BTC", [-0.05, -0.03, 0.02, -0.01, -0.04, 0.03, -0.02, 0.01, -0.06, 0.04]
        )
        var = ctrl.portfolio_var("BTC")
        cvar = ctrl.portfolio_cvar("BTC")
        assert var >= 0
        assert cvar >= 0

    def test_volatility_regime_requires_guard(self):
        ctrl = _build_controller(with_regime=False)
        with pytest.raises(RuntimeError, match="not configured"):
            ctrl.volatility_regime("BTC")

    def test_volatility_regime_with_guard(self):
        ctrl = _build_controller(with_regime=True)
        assert ctrl.volatility_regime("BTC") == VolatilityRegime.NORMAL

    def test_evaluate_order_with_regime(self):
        ctrl = _build_controller(with_regime=True)
        mc = MarketCondition(
            symbol="BTC",
            price=50000,
            volatility=0.3,
            win_probability=0.55,
            payoff_ratio=2.0,
        )
        ctrl.register_market_condition(mc)
        for i in range(5):
            ctrl.record_return("BTC", [0.001])
        req = PositionRequest(symbol="BTC", notional=100)
        result = ctrl.evaluate_order(req, account_equity=100_000)
        assert isinstance(result, bool)
