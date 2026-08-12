# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import math
from pathlib import Path

import numpy as np
import pytest

from backtest.engine import PortfolioConstraints, WalkForwardEngine, walk_forward
from backtest.transaction_costs import (
    BorrowFinancing,
    BpsSpread,
    CompositeTransactionCostModel,
    FixedBpsCommission,
    FixedSlippage,
    FixedSpread,
    PercentVolumeCommission,
    PerUnitCommission,
    SquareRootSlippage,
    TransactionCostModel,
    VolumeProportionalSlippage,
    load_market_costs,
)


class DummyModel(TransactionCostModel):
    def __init__(self) -> None:
        self.commission_calls: list[tuple[float, float]] = []
        self.spread_calls: list[tuple[float, str | None]] = []
        self.slippage_calls: list[tuple[float, float, str | None]] = []
        self.financing_calls: list[tuple[float, float]] = []

    def get_commission(self, volume: float, price: float) -> float:
        self.commission_calls.append((volume, price))
        return volume * 0.5

    def get_spread(self, price: float, side: str | None = None) -> float:
        self.spread_calls.append((price, side))
        return price * 0.01

    def get_slippage(self, volume: float, price: float, side: str | None = None) -> float:
        self.slippage_calls.append((volume, price, side))
        return volume * 0.1

    def get_financing(self, position: float, price: float) -> float:
        self.financing_calls.append((position, price))
        return position * price * 0.001


def test_component_models_behaviour() -> None:
    assert FixedBpsCommission(10).get_commission(5, 100) == pytest.approx(5 * 100 * 10 * 1e-4)
    assert PercentVolumeCommission(0.5).get_commission(2, 50) == pytest.approx(2 * 50 * 0.5 * 0.01)
    assert PerUnitCommission(1.2).get_commission(3, 10) == pytest.approx(3.6)

    assert FixedSpread(0.25).get_spread(100, "buy") == pytest.approx(0.25)
    assert BpsSpread(5).get_spread(200, "sell") == pytest.approx(200 * 5 * 1e-4)

    assert FixedSlippage(0.05).get_slippage(10, 100) == pytest.approx(0.05)
    assert VolumeProportionalSlippage(0.01).get_slippage(4, 100) == pytest.approx(0.04)
    assert SquareRootSlippage(a=0.1, b=0.5).get_slippage(9, 100) == pytest.approx(
        100 * (0.1 + 0.5 * math.sqrt(9))
    )

    linear_financing = BorrowFinancing(
        long_rate_bps=36500, short_rate_bps=36500, periods_per_year=365
    )
    assert linear_financing.get_financing(1.0, 100.0) == pytest.approx(1.0)
    assert linear_financing.get_financing(-2.0, 100.0) == pytest.approx(2.0)

    linear_reference = BorrowFinancing(long_rate_bps=10000, short_rate_bps=10000)
    nonlinear_financing = BorrowFinancing(long_rate_bps=10000, short_rate_bps=10000, exponent=1.5)
    assert nonlinear_financing.get_financing(4.0, 50.0) > linear_reference.get_financing(4.0, 50.0)


def test_composite_model_delegates() -> None:
    dummy = DummyModel()
    composite = CompositeTransactionCostModel(
        commission_model=dummy,
        spread_model=dummy,
        slippage_model=dummy,
        financing_model=dummy,
    )

    assert composite.get_commission(2, 100) == pytest.approx(1.0)
    assert composite.get_spread(50, "buy") == pytest.approx(0.5)
    assert composite.get_slippage(3, 75, "sell") == pytest.approx(0.3)
    assert composite.get_financing(2.0, 100.0) == pytest.approx(0.2)
    assert dummy.commission_calls == [(2, 100)]
    assert dummy.spread_calls == [(50, "buy")]
    assert dummy.slippage_calls == [(3, 75, "sell")]
    assert dummy.financing_calls == [(2.0, 100.0)]


def test_load_market_costs_from_mapping(tmp_path: Path) -> None:
    config = {
        "X-test": {
            "commission_model": "fixed_bps",
            "commission_params": {"bps": 12},
            "spread_model": "bps",
            "spread_params": {"bps": 4},
            "slippage_model": "volume",
            "slippage_params": {"coefficient": 0.02},
            "borrow_bps": 50,
        }
    }
    model = load_market_costs(config, "X-test")
    assert isinstance(model, CompositeTransactionCostModel)
    assert model.get_commission(1, 100) == pytest.approx(100 * 12 * 1e-4)
    assert model.get_spread(100) == pytest.approx(100 * 4 * 1e-4)
    assert model.get_slippage(5, 100) == pytest.approx(5 * 0.02)
    expected_daily_cost = (100.0 * 0.005) / 252
    assert model.get_financing(1.0, 100.0) == pytest.approx(expected_daily_cost)

    file_config = tmp_path / "markets.yaml"
    file_config.write_text(
        "X-test:\n  commission_bps: 10\n  funding_long_bps: 100\n  funding_short_bps: 200\n",
        encoding="utf8",
    )
    file_model = load_market_costs(file_config, "X-test")
    assert file_model.get_commission(2, 50) == pytest.approx(2 * 50 * 10 * 1e-4)
    expected_short_cost = (50.0 * 0.02) / 252
    assert file_model.get_financing(-1.0, 50.0) == pytest.approx(expected_short_cost)


def test_walk_forward_respects_default_fee() -> None:
    prices = np.array([100.0, 101.0, 102.0], dtype=float)

    def signals(_: np.ndarray) -> np.ndarray:
        return np.array([0.0, 1.0, 1.0])

    result = walk_forward(prices, signals, fee=0.01)
    assert result.trades == 1
    assert result.commission_cost == pytest.approx(0.01)
    assert result.spread_cost == pytest.approx(0.0)
    assert result.slippage_cost == pytest.approx(0.0)


def test_walk_forward_market_configuration(tmp_path: Path) -> None:
    config = tmp_path / "markets.yaml"
    config.write_text(
        "Test:\n"
        "  commission_per_unit: 1.25\n"
        "  spread: 0.5\n"
        "  slippage_model: fixed\n"
        "  slippage_params:\n"
        "    value: 0.25\n",
        encoding="utf8",
    )

    prices = np.array([100.0, 100.0, 100.0], dtype=float)

    def signals(_: np.ndarray) -> np.ndarray:
        return np.array([0.0, 1.0, 1.0])

    engine = WalkForwardEngine()
    result = engine.run(
        prices,
        signals,
        fee=0.0,
        cost_config=config,
        market="Test",
    )

    assert result.trades == 1
    assert result.commission_cost == pytest.approx(1.25)
    assert result.spread_cost == pytest.approx(0.5)
    assert result.slippage_cost == pytest.approx(0.25)
    assert result.pnl == pytest.approx(-(1.25 + 0.5 + 0.25))


def test_walk_forward_financing_and_constraints() -> None:
    prices = np.array([100.0, 101.0, 102.0, 103.0], dtype=float)

    def signals(_: np.ndarray) -> np.ndarray:
        return np.array([0.0, 1.0, 1.0, 1.0], dtype=float)

    financing_model = BorrowFinancing(
        long_rate_bps=36500, short_rate_bps=36500, periods_per_year=365
    )
    composite = CompositeTransactionCostModel(financing_model=financing_model)
    constraints = PortfolioConstraints(max_gross_exposure=0.5)

    engine = WalkForwardEngine()
    result = engine.run(
        prices,
        signals,
        fee=0.0,
        cost_model=composite,
        constraints=constraints,
    )

    assert result.trades == 1
    assert result.commission_cost == pytest.approx(0.0)
    assert result.slippage_cost == pytest.approx(0.0)
    assert result.spread_cost == pytest.approx(0.0)
    expected_cost = sum(0.5 * price * 3.65 / 365 for price in [prices[1], prices[2]])
    assert result.financing_cost == pytest.approx(expected_cost)
