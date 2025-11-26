"""Tests for adaptive volatility-aware exposure guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    TimeWeightedExposureTracker,
    VolatilityAdjustedSizer,
    VolatilityRegime,
)


def test_regime_guard_classification_and_cooldown() -> None:
    guard = RegimeAdaptiveExposureGuard(
        calm_threshold=0.001,
        stressed_threshold=0.01,
        critical_threshold=0.02,
        calm_multiplier=1.2,
        stressed_multiplier=0.7,
        critical_multiplier=0.4,
        half_life_seconds=1.0,
        min_samples=1,
        cooldown_seconds=10.0,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    assert guard.observe("BTC-USD", 0.0005, start.timestamp()) is VolatilityRegime.CALM
    assert pytest.approx(guard.multiplier("BTC-USD"), rel=1e-9) == 1.2

    stressed_time = start + timedelta(seconds=1)
    assert (
        guard.observe("BTC-USD", 0.025, stressed_time.timestamp())
        is VolatilityRegime.STRESSED
    )
    assert pytest.approx(guard.multiplier("BTC-USD"), rel=1e-9) == 0.7

    critical_time = start + timedelta(seconds=2)
    assert (
        guard.observe("BTC-USD", 0.03, critical_time.timestamp())
        is VolatilityRegime.CRITICAL
    )
    assert pytest.approx(guard.multiplier("BTC-USD"), rel=1e-9) == 0.4

    cooldown_block = start + timedelta(seconds=5)
    assert (
        guard.observe("BTC-USD", 0.0001, cooldown_block.timestamp())
        is VolatilityRegime.CRITICAL
    )

    cooldown_release = start + timedelta(seconds=20)
    assert guard.observe("BTC-USD", 0.0001, cooldown_release.timestamp()) in {
        VolatilityRegime.CALM,
        VolatilityRegime.NORMAL,
    }


def test_advanced_controller_respects_regime_guard_multiplier() -> None:
    guard = RegimeAdaptiveExposureGuard(
        calm_threshold=0.001,
        stressed_threshold=0.01,
        critical_threshold=0.015,
        calm_multiplier=1.0,
        stressed_multiplier=0.6,
        critical_multiplier=0.3,
        half_life_seconds=1.0,
        min_samples=1,
        cooldown_seconds=0.0,
    )

    controller = AdvancedRiskController(
        capital=1_000_000.0,
        margin_monitor=MarginMonitor(margin_limit=1.0, maintenance_margin=1.0),
        correlation_guard=CorrelationLimitGuard({}, max_exposure=10_000_000.0),
        drawdown_breaker=DrawdownBreaker(max_drawdown=0.5),
        exposure_tracker=TimeWeightedExposureTracker(half_life_seconds=10.0),
        liquidation_guard=LiquidationCascadePreventer(
            lambda _: 10_000_000.0, max_fraction=1.0
        ),
        risk_metrics=RiskMetricsCalculator(confidence=0.95),
        kelly_sizer=KellyCriterionPositionSizer(max_leverage=1.0, drawdown_buffer=1.0),
        vol_sizer=VolatilityAdjustedSizer(
            target_volatility=0.5, floor=0.1, ceiling=10.0
        ),
        regime_guard=guard,
    )

    market = MarketCondition(
        symbol="ETH-USD",
        price=2_000.0,
        volatility=0.5,
        win_probability=0.6,
        payoff_ratio=1.5,
    )
    controller.register_market_condition(market)

    first = datetime(2024, 1, 1, tzinfo=timezone.utc)
    second = first + timedelta(seconds=1)
    controller.record_return("ETH-USD", [(0.02, first), (0.03, second)])

    assert controller.volatility_regime("ETH-USD") is VolatilityRegime.CRITICAL

    request = PositionRequest(symbol="ETH-USD", notional=120_000.0)
    assert controller.evaluate_order(request, account_equity=1_000_000.0) is False
