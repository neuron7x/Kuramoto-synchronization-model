from __future__ import annotations

import math

import pytest

from execution.order import (
    ConstrainedPositionSizer,
    PortfolioState,
    PositionSizingConstraints,
    PositionSizingRequest,
    RiskAwarePositionSizer,
    position_sizing,
)
from execution.position_sizer import calculate_position_size


@pytest.mark.parametrize(
    "balance,risk,price,max_leverage",
    [
        (10_000.0, 0.02, 25_000.0, 5.0),
        (5_000.0, 0.5, 1_250.0, 3.0),
    ],
)
def test_calculate_position_size_matches_risk_aware(
    balance: float, risk: float, price: float, max_leverage: float
) -> None:
    sizer = RiskAwarePositionSizer()

    helper_qty = calculate_position_size(
        balance,
        risk,
        price,
        max_leverage=max_leverage,
    )
    class_qty = sizer.size(
        balance=balance,
        risk=risk,
        price=price,
        max_leverage=max_leverage,
    )

    assert helper_qty == pytest.approx(class_qty)


def test_calculate_position_size_guards_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        calculate_position_size(balance=1_000.0, risk=0.1, price=0.0)

    assert calculate_position_size(balance=0.0, risk=0.1, price=100.0) == 0.0
    assert calculate_position_size(balance=1_000.0, risk=-1.0, price=100.0) == 0.0
    assert calculate_position_size(
        balance=1_000.0, risk=10.0, price=100.0
    ) == pytest.approx(10.0)


def test_size_rejects_non_positive_price() -> None:
    sizer = RiskAwarePositionSizer()
    with pytest.raises(ValueError):
        sizer.size(balance=1_000.0, risk=0.1, price=0.0)
    with pytest.raises(ValueError):
        sizer.size(balance=1_000.0, risk=0.1, price=-1.0)


def test_size_clamps_risk_and_handles_zero_notional() -> None:
    sizer = RiskAwarePositionSizer()

    zero_qty = sizer.size(balance=5_000.0, risk=-0.5, price=100.0)
    assert zero_qty == 0.0

    capped_qty = sizer.size(balance=5_000.0, risk=5.0, price=125.0)
    assert capped_qty == pytest.approx((5_000.0 * 1.0) / 125.0)

    assert position_sizing(2_500.0, 0.0, 200.0) == 0.0


@pytest.mark.parametrize(
    "balance,risk,price",
    [
        (0.01, 0.25, 0.29),
    ],
)
def test_size_biases_down_when_rounding_overshoots(
    monkeypatch: pytest.MonkeyPatch, balance: float, risk: float, price: float
) -> None:
    sizer = RiskAwarePositionSizer()
    original_nextafter = math.nextafter
    calls: list[tuple[float, float]] = []

    def tracked_nextafter(x: float, y: float) -> float:
        calls.append((x, y))
        return original_nextafter(x, y)

    monkeypatch.setattr("execution.order.math.nextafter", tracked_nextafter)

    qty = sizer.size(balance=balance, risk=risk, price=price)

    assert (
        calls
    ), "nextafter should be consulted when the initial quantity exceeds the budget"
    assert qty >= 0.0
    assert qty * price <= balance * min(max(risk, 0.0), 1.0) + 1e-12


def test_constrained_sizer_zero_when_drawdown_breached() -> None:
    constraints = PositionSizingConstraints(max_drawdown=0.1, cppi_floor=0.9)
    sizer = ConstrainedPositionSizer(constraints)
    state = PortfolioState(
        balance=100_000.0,
        equity=85_000.0,
        peak_equity=100_000.0,
        volatility=0.18,
    )
    request = PositionSizingRequest(
        symbol="BTC",
        direction=1,
        price=25_000.0,
        risk_fraction=0.2,
        forecast_edge=0.05,
        forecast_variance=0.3,
        instrument_volatility=0.5,
    )

    result = sizer.size_order(request, state)

    assert result.order_quantity == 0.0
    assert result.target_position == 0.0
    assert result.notes.get("drawdown") == pytest.approx(0.15)


def test_constrained_sizer_scales_to_volatility_limit() -> None:
    constraints = PositionSizingConstraints(
        max_portfolio_volatility=0.3,
        volatility_buffer=0.0,
        kelly_fraction_limit=0.6,
        cppi_floor=0.5,
        cppi_multiplier=4.0,
    )
    sizer = ConstrainedPositionSizer(constraints)
    state = PortfolioState(
        balance=100_000.0,
        equity=100_000.0,
        peak_equity=100_000.0,
        volatility=0.25,
    )
    request = PositionSizingRequest(
        symbol="ETH",
        direction=1,
        price=100.0,
        risk_fraction=0.5,
        instrument_volatility=1.2,
    )

    result = sizer.size_order(request, state)

    assert result.target_position == pytest.approx(230.769, rel=1e-3)
    assert result.order_quantity == pytest.approx(result.target_position)
    assert result.notes.get("volatility_scale") == pytest.approx(0.4615, rel=1e-3)


def test_constrained_sizer_respects_risk_budgets_and_positions() -> None:
    constraints = PositionSizingConstraints(
        kelly_fraction_limit=0.5,
        max_drawdown=0.3,
        cppi_floor=0.6,
    )
    sizer = ConstrainedPositionSizer(constraints)
    state = PortfolioState(
        balance=200_000.0,
        equity=200_000.0,
        peak_equity=220_000.0,
        volatility=0.12,
        positions={"BTC": 0.5333333333},
        risk_budgets={"BTC": 0.1},
        risk_exposures={"BTC": 0.08, "ETH": 0.2},
    )
    request = PositionSizingRequest(
        symbol="BTC",
        direction=1,
        price=30_000.0,
        risk_fraction=0.3,
    )

    result = sizer.size_order(request, state)

    expected_fraction = 0.1 * (1 - state.drawdown / constraints.max_drawdown)
    expected_target = expected_fraction * state.equity / request.price

    assert result.target_position == pytest.approx(expected_target, rel=1e-6)
    assert result.order_quantity == pytest.approx(
        expected_target - state.position_for("BTC"), rel=1e-6
    )
    assert result.notes.get("risk_budget") == pytest.approx(0.1)


def test_constrained_sizer_size_method_matches_risk_aware_for_small_risk() -> None:
    sizer = ConstrainedPositionSizer()

    qty = sizer.size(balance=10_000.0, risk=0.02, price=25_000.0)

    assert qty == pytest.approx(0.008)


def test_constrained_sizer_size_clamps_negative_risk_to_zero() -> None:
    sizer = ConstrainedPositionSizer()

    qty = sizer.size(balance=5_000.0, risk=-0.3, price=200.0)

    assert qty == 0.0


def test_constrained_sizer_honours_zero_leverage_limit() -> None:
    constraints = PositionSizingConstraints(max_leverage=3.0)
    sizer = ConstrainedPositionSizer(constraints)
    state = PortfolioState(
        balance=50_000.0,
        equity=50_000.0,
        peak_equity=50_000.0,
        volatility=0.1,
    )
    request = PositionSizingRequest(
        symbol="BTC",
        direction=1,
        price=25_000.0,
        risk_fraction=0.5,
        leverage_limit=0.0,
    )

    result = sizer.size_order(request, state)

    assert result.order_quantity == 0.0
    assert result.target_position == 0.0


def test_constrained_sizer_neutral_clipping_emits_order() -> None:
    constraints = PositionSizingConstraints(max_leverage=1.0)
    sizer = ConstrainedPositionSizer(constraints)
    state = PortfolioState(
        balance=10_000.0,
        equity=10_000.0,
        peak_equity=10_000.0,
        volatility=0.05,
        positions={"BTC": 1.0},
    )
    request = PositionSizingRequest(
        symbol="BTC",
        direction=0,
        price=25_000.0,
        risk_fraction=0.0,
    )

    result = sizer.size_order(request, state)

    max_position = (state.equity * constraints.max_leverage) / request.price
    assert result.target_position == pytest.approx(max_position)
    assert result.order_quantity == 0.0
    assert result.notes.get("deferred_rebalance") == pytest.approx(
        max_position - state.position_for("BTC")
    )
    assert result.notes.get("leverage_clip") == pytest.approx(max_position)
