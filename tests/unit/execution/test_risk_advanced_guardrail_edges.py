# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guardrail edge tests for advanced execution risk orchestration."""

from __future__ import annotations

from execution.risk.advanced import (
    AdvancedRiskController,
    CorrelationLimitGuard,
    DrawdownBreaker,
    KellyCriterionPositionSizer,
    LiquidationCascadePreventer,
    MarginMonitor,
    MarketCondition,
    PositionRequest,
    RiskMetricsCalculator,
    TimeWeightedExposureTracker,
    VolatilityAdjustedSizer,
)


def _controller(
    *,
    correlation_limit: float = 500_000.0,
    liquidity: float = 1_000_000.0,
    max_liquidity_fraction: float = 0.5,
    drawdown_limit: float = 0.2,
) -> AdvancedRiskController:
    return AdvancedRiskController(
        capital=100_000.0,
        margin_monitor=MarginMonitor(margin_limit=0.9, maintenance_margin=0.95),
        correlation_guard=CorrelationLimitGuard({}, max_exposure=correlation_limit),
        drawdown_breaker=DrawdownBreaker(max_drawdown=drawdown_limit),
        exposure_tracker=TimeWeightedExposureTracker(),
        liquidation_guard=LiquidationCascadePreventer(
            liquidity_provider=lambda symbol: liquidity,
            max_fraction=max_liquidity_fraction,
        ),
        risk_metrics=RiskMetricsCalculator(),
        kelly_sizer=KellyCriterionPositionSizer(),
        vol_sizer=VolatilityAdjustedSizer(),
    )


def _register_tradeable_market(controller: AdvancedRiskController) -> None:
    controller.register_market_condition(
        MarketCondition(
            symbol="BTC",
            price=50_000.0,
            volatility=0.3,
            win_probability=0.60,
            payoff_ratio=2.0,
        )
    )


def test_correlation_rejection_does_not_mutate_positions_or_margin() -> None:
    controller = _controller(correlation_limit=50.0)
    _register_tradeable_market(controller)

    accepted = controller.evaluate_order(
        PositionRequest(symbol="BTC", notional=1_000.0),
        account_equity=100_000.0,
    )

    assert accepted is False
    assert controller.state.positions == {}
    assert controller.state.equity == 100_000.0


def test_liquidity_rejection_does_not_commit_position_state() -> None:
    controller = _controller(liquidity=100.0, max_liquidity_fraction=0.1)
    _register_tradeable_market(controller)

    accepted = controller.evaluate_order(
        PositionRequest(symbol="BTC", notional=50.0),
        account_equity=100_000.0,
    )

    assert accepted is False
    assert controller.state.positions == {}
    assert controller.state.equity == 100_000.0


def test_drawdown_breaker_rejection_preserves_existing_positions() -> None:
    controller = _controller(drawdown_limit=0.1)
    _register_tradeable_market(controller)

    first = controller.evaluate_order(
        PositionRequest(symbol="BTC", notional=100.0),
        account_equity=100_000.0,
    )
    second = controller.evaluate_order(
        PositionRequest(symbol="BTC", notional=50.0),
        account_equity=80_000.0,
    )

    assert first is True
    assert second is False
    assert controller.state.positions == {"BTC": 100.0}
    assert controller.state.equity == 100_000.0
