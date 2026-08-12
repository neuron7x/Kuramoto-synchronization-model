# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pytest

from domain.order import OrderSide
from execution.liquidation import (
    LiquidationEngine,
    LiquidationEngineConfig,
    LiquidationPlan,
    MarginAccountState,
    PositionExposure,
)


def make_position(
    symbol: str,
    quantity: float,
    price: float,
    maintenance_rate: float,
    initial_rate: float | None = None,
) -> PositionExposure:
    return PositionExposure(
        symbol=symbol,
        quantity=quantity,
        mark_price=price,
        maintenance_margin_rate=maintenance_rate,
        initial_margin_rate=initial_rate,
    )


def test_plan_when_margin_is_healthy_returns_empty_plan() -> None:
    account = MarginAccountState(
        equity=5_000.0,
        positions=[
            make_position("BTC-PERP", 1.0, 25_000.0, 0.1),
            make_position("ETH-PERP", -2.0, 1_800.0, 0.1),
        ],
    )

    engine = LiquidationEngine(lambda *_args: None)
    plan = engine.plan(account)

    assert isinstance(plan, LiquidationPlan)
    assert plan.actions == ()
    assert plan.pre_margin_ratio == pytest.approx(plan.post_margin_ratio)
    assert not plan.should_liquidate


def test_plan_reduces_position_to_restore_margin() -> None:
    account = MarginAccountState(
        equity=100.0,
        positions=[
            make_position("BTC-PERP", 2.0, 100.0, 0.2),  # maintenance: 40
            make_position("ETH-PERP", 1.0, 200.0, 0.4),  # maintenance: 80
        ],
    )
    engine = LiquidationEngine(
        lambda *_args: None, config=LiquidationEngineConfig(target_margin_ratio=1.1)
    )

    plan = engine.plan(account)

    assert plan.should_liquidate
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.symbol == "ETH-PERP"
    assert action.side is OrderSide.SELL
    # Reduction should cover the deficit and achieve the 1.1 ratio.
    assert action.maintenance_reduction == pytest.approx(plan.required_reduction, rel=1e-6)
    assert plan.post_margin_ratio >= 1.1


def test_liquidate_executes_orders() -> None:
    submitted: list[tuple[str, OrderSide, float]] = []

    def submit(symbol: str, side: OrderSide, quantity: float) -> None:
        submitted.append((symbol, side, quantity))

    account = MarginAccountState(
        equity=5.0,
        positions=[
            make_position("SOL-PERP", -4.0, 25.0, 0.15),
        ],
    )

    engine = LiquidationEngine(submit)
    plan = engine.liquidate(account)

    assert plan.should_liquidate
    assert len(submitted) == 1
    symbol, side, qty = submitted[0]
    assert symbol == "SOL-PERP"
    assert side is OrderSide.BUY
    assert qty == pytest.approx(plan.actions[0].quantity)


def test_plan_respects_minimum_order_quantity() -> None:
    account = MarginAccountState(
        equity=40.0,
        positions=[
            make_position("BTC-PERP", 0.05, 30_000.0, 0.2),
        ],
    )
    config = LiquidationEngineConfig(target_margin_ratio=1.05, min_order_quantity=0.1)
    engine = LiquidationEngine(lambda *_args: None, config=config)

    plan = engine.plan(account)

    # Position is smaller than the minimum order size so it must be skipped.
    assert not plan.should_liquidate


def test_short_position_liquidation_side_is_buy() -> None:
    account = MarginAccountState(
        equity=10.0,
        positions=[
            make_position("ETH-PERP", -1.0, 1_700.0, 0.2),
        ],
    )
    engine = LiquidationEngine(lambda *_args: None)
    plan = engine.plan(account)

    assert plan.should_liquidate
    assert plan.actions[0].side is OrderSide.BUY
