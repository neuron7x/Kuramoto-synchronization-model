# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Defect-sensitive contracts for the risk / sizing core.

Targets: adaptive_risk_manager, dynamic_position_sizer, gaba_inhibition_gate,
order_validator, portfolio_optimizer. Every assertion pins a safety invariant a
regression could quietly break: monotone risk caps, non-negative sizes, fail-closed
rejection of degenerate orders/inputs, the GABA magnitude-fidelity guarantee, the
portfolio weight-sum contract, and explicit handling of singular/NaN covariance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch

from modules.adaptive_risk_manager import AdaptiveRiskManager
from modules.dynamic_position_sizer import DynamicPositionSizer, SizingMethod
from modules.gaba_inhibition_gate import GABAInhibitionGate, GateParams
from modules.order_validator import Order, OrderSide, OrderType, OrderValidator
from modules.portfolio_optimizer import OptimizationMethod, PortfolioOptimizer


# --------------------------------------------------------------------------- #
# adaptive_risk_manager
# --------------------------------------------------------------------------- #
def test_leverage_cap_is_monotonic_in_volatility() -> None:
    arm = AdaptiveRiskManager(base_capital=100_000.0)
    low_vol = arm.update_position_limits("A", volatility=0.005)
    high_vol = arm.update_position_limits("B", volatility=0.05)
    # Higher volatility must never permit MORE leverage.
    assert high_vol.max_leverage < low_vol.max_leverage


def test_position_size_is_non_negative_and_price_must_be_positive() -> None:
    arm = AdaptiveRiskManager(base_capital=100_000.0)
    size = arm.calculate_position_size("A", price=100.0, volatility=0.01, confidence=1.0)
    assert size >= 0.0
    # Zero / negative equity-price is a degenerate order and must be rejected.
    with pytest.raises(ValueError, match="positive"):
        arm.calculate_position_size("A", price=0.0)
    with pytest.raises(ValueError, match="positive"):
        arm.calculate_position_size("A", price=-5.0)


# --------------------------------------------------------------------------- #
# dynamic_position_sizer
# --------------------------------------------------------------------------- #
def test_recommended_size_is_bounded_and_non_negative() -> None:
    ds = DynamicPositionSizer(base_capital=100_000.0)
    result = ds.calculate_size("A", price=100.0, volatility=0.2, confidence=1.0)
    assert result.recommended_size >= 0.0
    assert result.min_size <= result.recommended_size <= result.max_size


def test_kelly_fraction_fails_closed_on_degenerate_stats() -> None:
    ds = DynamicPositionSizer(base_capital=100_000.0)
    # Non-positive average loss, or certain win, cannot produce a positive bet.
    assert ds.calculate_kelly_size(0.6, 0.02, 0.0) == 0.0
    assert ds.calculate_kelly_size(1.0, 0.02, 0.01) == 0.0
    assert ds.calculate_kelly_size(0.0, 0.02, 0.01) == 0.0


def test_kelly_is_capped_and_fractional_shrinks_it() -> None:
    ds = DynamicPositionSizer(base_capital=100_000.0, kelly_fraction=0.25)
    full = ds.calculate_kelly_size(0.7, 0.05, 0.02, fractional=False)
    frac = ds.calculate_kelly_size(0.7, 0.05, 0.02, fractional=True)
    assert 0.0 <= full <= 0.5  # hard 50% cap
    assert frac == pytest.approx(full * 0.25)


def test_kelly_method_size_never_exceeds_max_position() -> None:
    ds = DynamicPositionSizer(base_capital=100_000.0)
    res = ds.calculate_size(
        "A", price=100.0, volatility=0.2, confidence=1.0, method=SizingMethod.KELLY,
        win_rate=0.9, avg_win=0.1, avg_loss=0.01,
    )
    assert res.recommended_size <= res.max_size


# --------------------------------------------------------------------------- #
# gaba_inhibition_gate
# --------------------------------------------------------------------------- #
def test_gaba_gate_enforces_magnitude_fidelity_when_elevated() -> None:
    gate = GABAInhibitionGate(GateParams(), device="cpu")
    market_state = {
        "vix": 80.0, "volatility": 0.5, "return": 0.01,
        "position": 1.0, "rpe": 0.0, "delta_t_ms": 10.0,
    }
    action = torch.tensor([2.0, -3.0, 1.5])
    gated = action.clone()
    metrics = None
    for _ in range(5):  # let GABA build past the 0.1 MFD activation boundary
        gated, metrics = gate.forward(market_state, action.clone())
    assert metrics is not None
    assert metrics.gaba_level > 0.1  # elevated -> MFD guarantee is active
    # Magnitude-fidelity: gated action never exceeds the proposed action.
    assert bool((gated.abs() <= action.abs() + 1e-6).all())


def test_gaba_gate_clamps_inhibition_to_max_and_rejects_nan() -> None:
    params = GateParams()
    gate = GABAInhibitionGate(params, device="cpu")
    market_state = {
        "vix": 1000.0, "volatility": 5.0, "return": 0.0,
        "position": 0.0, "rpe": 0.0, "delta_t_ms": 50.0,
    }
    _, metrics = gate.forward(market_state, torch.tensor([9.0, 9.0]))
    # Inhibition can approach but never exceed the pinned cap (equality boundary).
    assert 0.0 <= metrics.inhibition <= params.max_inhibition
    assert params.risk_min <= metrics.risk_weight <= params.risk_max
    with pytest.raises(ValueError, match="NaN or Inf"):
        gate.forward(market_state, torch.tensor([float("nan"), 1.0]))


# --------------------------------------------------------------------------- #
# order_validator
# --------------------------------------------------------------------------- #
def test_order_validator_rejects_bad_quantity_and_symbol() -> None:
    ov = OrderValidator()
    bad_qty = Order("id1", "AAPL", OrderSide.BUY, OrderType.MARKET, quantity=-5.0)
    result = ov.validate(bad_qty, current_price=100.0)
    assert result.is_valid is False
    assert "INVALID_QUANTITY" in {e.code for e in result.errors}

    missing = Order("", "", OrderSide.BUY, OrderType.MARKET, quantity=100.0)
    codes = {e.code for e in ov.validate(missing, current_price=100.0).errors}
    assert {"MISSING_SYMBOL", "MISSING_ORDER_ID"} <= codes


def test_order_validator_still_catches_basics_without_a_price() -> None:
    # A missing current_price must not bypass the basic quantity gate.
    ov = OrderValidator()
    order = Order("id1", "AAPL", OrderSide.BUY, OrderType.MARKET, quantity=0.0)
    result = ov.validate(order, current_price=None)
    assert result.is_valid is False
    assert "INVALID_QUANTITY" in {e.code for e in result.errors}


def test_limit_order_requires_positive_limit_price() -> None:
    ov = OrderValidator()
    order = Order("id1", "AAPL", OrderSide.BUY, OrderType.LIMIT, quantity=100.0, price=None)
    codes = {e.code for e in ov.validate(order, current_price=100.0).errors}
    assert "MISSING_LIMIT_PRICE" in codes


# --------------------------------------------------------------------------- #
# portfolio_optimizer
# --------------------------------------------------------------------------- #
def _returns(seed: int = 0, cols: int = 5, n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(0.0, 0.01, size=(n, cols)),
        columns=[chr(ord("A") + i) for i in range(cols)],
    )


def test_optimizer_weights_are_non_negative_and_sum_to_one() -> None:
    opt = PortfolioOptimizer()
    for method in (
        OptimizationMethod.MAX_SHARPE,
        OptimizationMethod.MIN_VARIANCE,
        OptimizationMethod.RISK_PARITY,
        OptimizationMethod.EQUAL_WEIGHT,
    ):
        result = opt.optimize(_returns(), method=method)
        weights = [a.weight for a in result.allocations]
        assert all(np.isfinite(w) for w in weights)
        assert all(w >= 0.0 for w in weights)  # no-short default constraint
        assert sum(weights) == pytest.approx(1.0, abs=1e-9)


def test_optimizer_handles_singular_covariance_explicitly() -> None:
    # Perfectly collinear assets -> singular covariance. pinv keeps it finite.
    rng = np.random.default_rng(1)
    base = rng.normal(0.0, 0.01, size=(300, 1))
    df = pd.DataFrame(np.tile(base, (1, 4)), columns=list("ABCD"))
    result = PortfolioOptimizer().optimize(df, method=OptimizationMethod.MIN_VARIANCE)
    weights = [a.weight for a in result.allocations]
    assert all(np.isfinite(w) for w in weights)
    assert sum(weights) == pytest.approx(1.0, abs=1e-9)


def test_optimizer_rejects_nan_or_inf_returns() -> None:
    opt = PortfolioOptimizer()
    nan_df = _returns()
    nan_df["A"] = np.nan  # all-NaN column -> undefined covariance
    with pytest.raises(ValueError, match="NaN or Inf"):
        opt.optimize(nan_df, method=OptimizationMethod.MAX_SHARPE)
    inf_df = _returns()
    inf_df.iloc[0, 0] = np.inf
    with pytest.raises(ValueError, match="NaN or Inf"):
        opt.optimize(inf_df, method=OptimizationMethod.MAX_SHARPE)
