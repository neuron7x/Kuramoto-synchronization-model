# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""State edge tests for advanced execution risk orchestration."""

from __future__ import annotations

from datetime import datetime, timezone

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
)


def _tradeable_market() -> MarketCondition:
    return MarketCondition(
        symbol="BTC",
        price=50_000.0,
        volatility=0.3,
        win_probability=0.60,
        payoff_ratio=2.0,
    )


def _controller(
    *,
    margin_monitor: MarginMonitor | None = None,
    exposure_tracker: TimeWeightedExposureTracker | None = None,
    regime_guard: RegimeAdaptiveExposureGuard | None = None,
) -> AdvancedRiskController:
    return AdvancedRiskController(
        capital=100_000.0,
        margin_monitor=margin_monitor or MarginMonitor(
            margin_limit=0.9,
            maintenance_margin=0.95,
        ),
        correlation_guard=CorrelationLimitGuard({}, max_exposure=500_000.0),
        drawdown_breaker=DrawdownBreaker(max_drawdown=0.2),
        exposure_tracker=exposure_tracker or TimeWeightedExposureTracker(),
        liquidation_guard=LiquidationCascadePreventer(
            liquidity_provider=lambda symbol: 1_000_000.0,
            max_fraction=0.5,
        ),
        risk_metrics=RiskMetricsCalculator(),
        kelly_sizer=KellyCriterionPositionSizer(),
        vol_sizer=VolatilityAdjustedSizer(),
        regime_guard=regime_guard,
    )


def test_margin_rejection_preserves_portfolio_commit_state() -> None:
    margin_monitor = MarginMonitor(margin_limit=0.01, maintenance_margin=0.01)
    controller = _controller(margin_monitor=margin_monitor)
    controller.register_market_condition(_tradeable_market())

    accepted = controller.evaluate_order(
        PositionRequest(symbol="BTC", notional=5_000.0),
        account_equity=100_000.0,
    )

    assert accepted is False
    assert margin_monitor.utilisation == 0.05
    assert controller.state.positions == {}
    assert controller.state.equity == 100_000.0


def test_exposure_cap_rejection_records_pressure_without_position_commit() -> None:
    exposure_tracker = TimeWeightedExposureTracker()
    controller = _controller(exposure_tracker=exposure_tracker)
    controller.register_market_condition(_tradeable_market())

    accepted = controller.evaluate_order(
        PositionRequest(symbol="BTC", notional=20_000.0),
        account_equity=100_000.0,
    )

    assert accepted is False
    assert exposure_tracker.exposure == 20_000.0
    assert controller.state.positions == {}
    assert controller.state.equity == 100_000.0


def test_record_return_keeps_bounded_tail_and_updates_regime_guard() -> None:
    regime_guard = RegimeAdaptiveExposureGuard(min_samples=1, cooldown_seconds=0.0)
    controller = _controller(regime_guard=regime_guard)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)

    controller.record_return("BTC", [(0.001, timestamp)] * 2_100)

    assert len(controller.state.returns_history["BTC"]) == 2_048
    assert regime_guard.regime("BTC").name in {"CALM", "NORMAL"}
