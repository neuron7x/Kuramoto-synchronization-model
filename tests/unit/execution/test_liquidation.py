# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.liquidation — target uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain import OrderSide
from execution.liquidation import (
    LiquidationAction,
    LiquidationEngine,
    LiquidationEngineConfig,
    LiquidationPlan,
    MarginAccountState,
    PositionExposure,
)

# ── PositionExposure ────────────────────────────────────────────────


class TestPositionExposure:
    def test_valid(self):
        pe = PositionExposure(
            symbol="BTC",
            quantity=1.0,
            mark_price=100.0,
            maintenance_margin_rate=0.05,
        )
        assert pe.abs_quantity == 1.0
        assert pe.notional == 100.0
        assert pe.maintenance_margin == 5.0
        assert pe.initial_margin == 5.0  # uses maint rate as fallback
        assert pe.liquidation_side == OrderSide.SELL

    def test_short_position(self):
        pe = PositionExposure(
            symbol="BTC",
            quantity=-2.0,
            mark_price=50.0,
            maintenance_margin_rate=0.1,
        )
        assert pe.abs_quantity == 2.0
        assert pe.notional == 100.0
        assert pe.liquidation_side == OrderSide.BUY

    def test_flat_position_raises(self):
        pe = PositionExposure(
            symbol="BTC",
            quantity=0.0,
            mark_price=50.0,
            maintenance_margin_rate=0.1,
        )
        with pytest.raises(ValueError, match="flat position"):
            _ = pe.liquidation_side

    def test_initial_margin_rate(self):
        pe = PositionExposure(
            symbol="BTC",
            quantity=1.0,
            mark_price=100.0,
            maintenance_margin_rate=0.05,
            initial_margin_rate=0.1,
        )
        assert pe.initial_margin == 10.0

    def test_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            PositionExposure(symbol="", quantity=1.0, mark_price=100, maintenance_margin_rate=0.05)

    def test_zero_price_raises(self):
        with pytest.raises(ValueError, match="mark_price"):
            PositionExposure(symbol="BTC", quantity=1, mark_price=0, maintenance_margin_rate=0.05)

    def test_zero_maint_rate_raises(self):
        with pytest.raises(ValueError, match="maintenance_margin_rate"):
            PositionExposure(symbol="BTC", quantity=1, mark_price=100, maintenance_margin_rate=0)

    def test_invalid_initial_margin_rate(self):
        with pytest.raises(ValueError, match="initial_margin_rate"):
            PositionExposure(
                symbol="BTC",
                quantity=1,
                mark_price=100,
                maintenance_margin_rate=0.05,
                initial_margin_rate=-1,
            )


# ── MarginAccountState ──────────────────────────────────────────────


class TestMarginAccountState:
    def test_maintenance_from_positions(self):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=1.0, mark_price=100, maintenance_margin_rate=0.05
            ),
        ]
        acc = MarginAccountState(equity=100.0, positions=pos)
        assert acc.maintenance_requirement == 5.0
        assert acc.maintenance_deficit == 0.0
        assert acc.margin_ratio == 100.0 / 5.0

    def test_maintenance_from_explicit(self):
        acc = MarginAccountState(equity=50.0, maintenance_margin=100.0)
        assert acc.maintenance_requirement == 100.0
        assert acc.maintenance_deficit == 50.0

    def test_initial_from_positions(self):
        pos = [
            PositionExposure(
                symbol="BTC",
                quantity=1.0,
                mark_price=100,
                maintenance_margin_rate=0.05,
                initial_margin_rate=0.1,
            ),
        ]
        acc = MarginAccountState(equity=100.0, positions=pos)
        assert acc.initial_requirement == 10.0

    def test_initial_from_explicit(self):
        acc = MarginAccountState(equity=100.0, initial_margin=20.0)
        assert acc.initial_requirement == 20.0

    def test_margin_ratio_inf_when_no_requirement(self):
        acc = MarginAccountState(equity=100.0)
        assert acc.margin_ratio == float("inf")

    def test_invalid_equity_type(self):
        with pytest.raises(TypeError, match="equity"):
            MarginAccountState(equity="oops")  # type: ignore[arg-type]


# ── LiquidationEngineConfig ─────────────────────────────────────────


class TestLiquidationEngineConfig:
    def test_defaults(self):
        cfg = LiquidationEngineConfig()
        assert cfg.target_margin_ratio == 1.05

    def test_invalid_target_ratio(self):
        with pytest.raises(ValueError, match="target_margin_ratio"):
            LiquidationEngineConfig(target_margin_ratio=0)

    def test_invalid_max_fraction(self):
        with pytest.raises(ValueError, match="max_position_fraction"):
            LiquidationEngineConfig(max_position_fraction=0)

    def test_invalid_min_order(self):
        with pytest.raises(ValueError, match="min_order_quantity"):
            LiquidationEngineConfig(min_order_quantity=-1)

    def test_invalid_precision(self):
        with pytest.raises(ValueError, match="precision"):
            LiquidationEngineConfig(precision=0)


# ── LiquidationAction ──────────────────────────────────────────────


class TestLiquidationAction:
    def test_valid(self):
        a = LiquidationAction(
            symbol="BTC",
            side=OrderSide.SELL,
            quantity=1.0,
            maintenance_reduction=5.0,
            notional_reduction=100.0,
        )
        assert a.quantity == 1.0

    def test_zero_quantity_raises(self):
        with pytest.raises(ValueError, match="quantity"):
            LiquidationAction(
                symbol="BTC",
                side=OrderSide.SELL,
                quantity=0,
                maintenance_reduction=5.0,
                notional_reduction=100.0,
            )

    def test_negative_maintenance_reduction_raises(self):
        with pytest.raises(ValueError, match="maintenance_reduction"):
            LiquidationAction(
                symbol="BTC",
                side=OrderSide.SELL,
                quantity=1.0,
                maintenance_reduction=-1,
                notional_reduction=100.0,
            )

    def test_negative_notional_reduction_raises(self):
        with pytest.raises(ValueError, match="notional_reduction"):
            LiquidationAction(
                symbol="BTC",
                side=OrderSide.SELL,
                quantity=1.0,
                maintenance_reduction=5.0,
                notional_reduction=-1,
            )


# ── LiquidationPlan ─────────────────────────────────────────────────


class TestLiquidationPlan:
    def test_should_liquidate_true(self):
        action = LiquidationAction(
            symbol="BTC",
            side=OrderSide.SELL,
            quantity=1.0,
            maintenance_reduction=5.0,
            notional_reduction=100.0,
        )
        plan = LiquidationPlan(
            actions=(action,),
            pre_margin_ratio=0.8,
            post_margin_ratio=1.1,
            maintenance_deficit=10.0,
            required_reduction=5.0,
        )
        assert plan.should_liquidate is True

    def test_should_liquidate_false(self):
        plan = LiquidationPlan(
            actions=(),
            pre_margin_ratio=1.5,
            post_margin_ratio=1.5,
            maintenance_deficit=0.0,
            required_reduction=0.0,
        )
        assert plan.should_liquidate is False


# ── LiquidationEngine ──────────────────────────────────────────────


class TestLiquidationEngine:
    @pytest.fixture()
    def submit_mock(self):
        return MagicMock()

    def test_plan_no_liquidation_needed(self, submit_mock):
        engine = LiquidationEngine(submit_mock)
        pos = [
            PositionExposure(
                symbol="BTC", quantity=1.0, mark_price=100, maintenance_margin_rate=0.05
            ),
        ]
        acc = MarginAccountState(equity=100.0, positions=pos)
        plan = engine.plan(acc)
        assert plan.should_liquidate is False
        assert plan.pre_margin_ratio == 100.0 / 5.0

    def test_plan_with_liquidation(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=10.0, mark_price=100, maintenance_margin_rate=0.1
            ),
        ]
        # equity=50, requirement=100, ratio=0.5 < 1.05
        acc = MarginAccountState(equity=50.0, positions=pos)
        engine = LiquidationEngine(submit_mock)
        plan = engine.plan(acc)
        assert plan.should_liquidate is True
        assert len(plan.actions) > 0
        assert plan.actions[0].side == OrderSide.SELL

    def test_plan_no_positions(self, submit_mock):
        acc = MarginAccountState(equity=100.0)
        engine = LiquidationEngine(submit_mock)
        plan = engine.plan(acc)
        assert plan.should_liquidate is False
        assert plan.post_margin_ratio == float("inf")

    def test_liquidate_executes_orders(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=10.0, mark_price=100, maintenance_margin_rate=0.1
            ),
        ]
        acc = MarginAccountState(equity=50.0, positions=pos)
        engine = LiquidationEngine(submit_mock)
        plan = engine.liquidate(acc)
        assert plan.should_liquidate is True
        assert submit_mock.called

    def test_liquidate_no_action_needed(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=1.0, mark_price=100, maintenance_margin_rate=0.05
            ),
        ]
        acc = MarginAccountState(equity=1000.0, positions=pos)
        engine = LiquidationEngine(submit_mock)
        plan = engine.liquidate(acc)
        assert not plan.should_liquidate
        assert not submit_mock.called

    def test_simulate_multiple_accounts(self, submit_mock):
        pos1 = [
            PositionExposure(
                symbol="BTC", quantity=1.0, mark_price=100, maintenance_margin_rate=0.05
            ),
        ]
        pos2 = [
            PositionExposure(
                symbol="ETH", quantity=10.0, mark_price=50, maintenance_margin_rate=0.1
            ),
        ]
        acc1 = MarginAccountState(equity=1000.0, positions=pos1)
        acc2 = MarginAccountState(equity=10.0, positions=pos2)
        engine = LiquidationEngine(submit_mock)
        plans = engine.simulate([acc1, acc2])
        assert len(plans) == 2
        assert plans[0].should_liquidate is False
        assert plans[1].should_liquidate is True

    def test_config_accessor(self, submit_mock):
        cfg = LiquidationEngineConfig(target_margin_ratio=1.5)
        engine = LiquidationEngine(submit_mock, config=cfg)
        assert engine.config.target_margin_ratio == 1.5

    def test_plan_multiple_positions(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=5.0, mark_price=200, maintenance_margin_rate=0.1
            ),
            PositionExposure(
                symbol="ETH", quantity=10.0, mark_price=50, maintenance_margin_rate=0.1
            ),
        ]
        # Maint: BTC=100, ETH=50 → total=150, equity=80 → ratio ~0.53
        acc = MarginAccountState(equity=80.0, positions=pos)
        engine = LiquidationEngine(submit_mock)
        plan = engine.plan(acc)
        assert plan.should_liquidate is True
        assert len(plan.actions) >= 1

    def test_plan_with_min_order_quantity(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=0.001, mark_price=100, maintenance_margin_rate=0.1
            ),
        ]
        acc = MarginAccountState(equity=0.005, positions=pos)
        cfg = LiquidationEngineConfig(min_order_quantity=1.0)
        engine = LiquidationEngine(submit_mock, config=cfg)
        plan = engine.plan(acc)
        # Position too small to meet min_order_quantity
        assert len(plan.actions) == 0

    def test_plan_max_position_fraction(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=10.0, mark_price=100, maintenance_margin_rate=0.1
            ),
        ]
        acc = MarginAccountState(equity=50.0, positions=pos)
        cfg = LiquidationEngineConfig(max_position_fraction=0.5)
        engine = LiquidationEngine(submit_mock, config=cfg)
        plan = engine.plan(acc)
        if plan.actions:
            assert plan.actions[0].quantity <= 5.0 + 1e-9

    def test_plan_short_position(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=-10.0, mark_price=100, maintenance_margin_rate=0.1
            ),
        ]
        acc = MarginAccountState(equity=50.0, positions=pos)
        engine = LiquidationEngine(submit_mock)
        plan = engine.plan(acc)
        assert plan.should_liquidate is True
        assert plan.actions[0].side == OrderSide.BUY

    def test_plan_already_at_target(self, submit_mock):
        pos = [
            PositionExposure(
                symbol="BTC", quantity=1.0, mark_price=100, maintenance_margin_rate=0.1
            ),
        ]
        # Maint=10, equity=10.5 → ratio=1.05 exactly
        acc = MarginAccountState(equity=10.5, positions=pos)
        engine = LiquidationEngine(submit_mock)
        plan = engine.plan(acc)
        assert plan.should_liquidate is False
