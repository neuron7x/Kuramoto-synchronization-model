# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import math
from decimal import Decimal, localcontext

import pytest

try:  # pragma: no cover - optional dependency boundary
    from hypothesis import assume, event, given, seed, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from execution.order import (
    ConstrainedPositionSizer,
    PortfolioState,
    PositionSizingConstraints,
    PositionSizingRequest,
    RiskAwarePositionSizer,
)

from .utils import property_seed, property_settings, regression_note


def _finite_floats(*, min_value: float, max_value: float) -> st.SearchStrategy[float]:
    return st.floats(
        min_value=min_value,
        max_value=max_value,
        allow_nan=False,
        allow_infinity=False,
    )


def _risk_aware_reference(
    balance: float, risk: float, price: float, max_leverage: float
) -> float:
    if price <= 0.0:
        raise ValueError("price must be positive")
    clipped_risk = max(0.0, min(risk, 1.0))
    notional = balance * clipped_risk
    if notional <= 0.0:
        return 0.0

    with localcontext() as ctx:
        ctx.prec = 50
        notional_d = Decimal(str(balance)) * Decimal(str(clipped_risk))
        price_d = Decimal(str(price))
        risk_qty = notional_d / price_d
        leverage_cap = (Decimal(str(balance)) * Decimal(str(max_leverage))) / price_d
        qty = min(risk_qty, leverage_cap)
        qty_float = float(qty)

    if qty_float <= 0.0:
        return 0.0

    if qty_float * price > notional + 1e-15:
        candidate = qty_float
        while candidate > 0.0 and candidate * price > notional + 1e-15:
            candidate = math.nextafter(candidate, 0.0)
        qty_float = max(0.0, candidate)

    return qty_float


@seed(property_seed("test_risk_aware_matches_reference"))
@settings(**property_settings("test_risk_aware_matches_reference", max_examples=150))
@given(
    _finite_floats(min_value=0.0, max_value=1e9),
    _finite_floats(min_value=-2.0, max_value=2.0),
    _finite_floats(min_value=1e-9, max_value=1e6),
    _finite_floats(min_value=1.0, max_value=50.0),
)
def test_risk_aware_matches_reference(
    balance: float, risk: float, price: float, leverage: float
) -> None:
    sizer = RiskAwarePositionSizer()
    expected = _risk_aware_reference(balance, risk, price, leverage)
    actual = sizer.size(balance, risk, price, max_leverage=leverage)

    regression_note(
        "risk_aware_case",
        {
            "balance": balance,
            "risk": risk,
            "price": price,
            "leverage": leverage,
            "expected": expected,
            "actual": actual,
        },
    )

    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    assert actual >= 0.0
    assert actual * price <= balance * max(0.0, min(risk, 1.0)) + 1e-9
    assert actual <= (balance * leverage) / price + 1e-9


def _constraint_strategy() -> st.SearchStrategy[PositionSizingConstraints]:
    return st.builds(
        PositionSizingConstraints,
        max_drawdown=_finite_floats(min_value=0.0, max_value=0.9),
        max_portfolio_volatility=_finite_floats(min_value=0.05, max_value=5.0),
        kelly_fraction_limit=_finite_floats(min_value=0.05, max_value=1.0),
        cppi_multiplier=_finite_floats(min_value=1.0, max_value=20.0),
        cppi_floor=_finite_floats(min_value=0.0, max_value=0.95),
        volatility_buffer=_finite_floats(min_value=0.0, max_value=0.2),
        min_order_size=_finite_floats(min_value=0.0, max_value=5.0),
        max_order_size=st.one_of(
            st.none(), _finite_floats(min_value=0.1, max_value=10.0)
        ),
        max_leverage=_finite_floats(min_value=1.0, max_value=20.0),
    )


def _symbol_strategy() -> st.SearchStrategy[str]:
    alphabet = st.characters(min_codepoint=65, max_codepoint=90)
    return st.text(alphabet=alphabet, min_size=2, max_size=6)


@st.composite
def _portfolio_state_request(
    draw: st.DrawFn,
) -> tuple[PositionSizingRequest, PortfolioState, PositionSizingConstraints]:
    constraints = draw(_constraint_strategy())
    symbol = draw(_symbol_strategy())

    balance = draw(_finite_floats(min_value=0.0, max_value=1e9))
    equity = draw(_finite_floats(min_value=0.0, max_value=1e9))
    peak_equity_raw = draw(_finite_floats(min_value=0.0, max_value=1.5e9))
    peak_equity = max(peak_equity_raw, equity, balance, 1e-6)
    volatility = draw(_finite_floats(min_value=0.0, max_value=2.0))

    positions = draw(
        st.dictionaries(
            keys=_symbol_strategy(),
            values=_finite_floats(min_value=-5e4, max_value=5e4),
            max_size=5,
        )
    )
    positions = dict(positions)
    positions.setdefault(symbol, 0.0)

    budget_source = draw(st.one_of(st.none(), st.just("fixed"), st.just("absent")))
    if budget_source == "fixed":
        risk_budgets = {
            key: draw(_finite_floats(min_value=0.0, max_value=1.0)) for key in positions
        }
    elif budget_source is None:
        risk_budgets = None
    else:
        risk_budgets = {}
    if isinstance(risk_budgets, dict) and draw(st.booleans()):
        risk_budgets[symbol] = draw(_finite_floats(min_value=0.0, max_value=1.0))

    exposure_source = draw(st.one_of(st.none(), st.just("portfolio")))
    if exposure_source is None:
        risk_exposures = None
    else:
        risk_exposures = {
            key: draw(_finite_floats(min_value=-1.0, max_value=2.0))
            for key in positions
        }

    state = PortfolioState(
        balance=balance,
        equity=equity,
        peak_equity=peak_equity,
        volatility=volatility,
        positions=positions,
        risk_budgets=risk_budgets,
        risk_exposures=risk_exposures,
    )

    leverage_limit = draw(
        st.one_of(
            st.none(), _finite_floats(min_value=0.5, max_value=constraints.max_leverage)
        )
    )
    risk_fraction = draw(_finite_floats(min_value=-0.5, max_value=1.5))
    confidence = draw(_finite_floats(min_value=0.0, max_value=1.0))
    edge = draw(st.one_of(st.none(), _finite_floats(min_value=-0.5, max_value=0.5)))
    variance = draw(st.one_of(st.none(), _finite_floats(min_value=0.0, max_value=2.0)))
    instrument_vol = draw(
        st.one_of(st.none(), _finite_floats(min_value=0.0, max_value=3.0))
    )
    min_trade_qty = draw(_finite_floats(min_value=0.0, max_value=10.0))
    max_trade_qty = draw(
        st.one_of(st.none(), _finite_floats(min_value=0.1, max_value=20.0))
    )

    request = PositionSizingRequest(
        symbol=symbol,
        direction=draw(st.integers(min_value=-1, max_value=1)),
        price=draw(_finite_floats(min_value=1e-9, max_value=1e6)),
        risk_fraction=risk_fraction,
        confidence=confidence,
        forecast_edge=edge,
        forecast_variance=variance,
        instrument_volatility=instrument_vol,
        min_trade_qty=min_trade_qty,
        max_trade_qty=max_trade_qty,
        leverage_limit=leverage_limit,
    )

    return request, state, constraints


@seed(property_seed("test_constrained_matches_risk_aware_when_unbounded"))
@settings(
    **property_settings(
        "test_constrained_matches_risk_aware_when_unbounded", max_examples=120
    )
)
@given(
    _finite_floats(min_value=0.0, max_value=1e9),
    _finite_floats(min_value=-0.5, max_value=1.5),
    _finite_floats(min_value=1e-9, max_value=1e6),
    _finite_floats(min_value=1.0, max_value=15.0),
)
def test_constrained_matches_risk_aware_when_unbounded(
    balance: float, risk: float, price: float, leverage: float
) -> None:
    base = RiskAwarePositionSizer()
    constraints = PositionSizingConstraints(
        max_drawdown=1.0,
        max_portfolio_volatility=10.0,
        kelly_fraction_limit=1.0,
        cppi_multiplier=max(2.0, leverage * 1.5),
        cppi_floor=0.0,
        volatility_buffer=0.0,
        min_order_size=0.0,
        max_order_size=None,
        max_leverage=max(leverage, 1.0),
    )
    constrained = ConstrainedPositionSizer(constraints=constraints)

    expected = base.size(balance, risk, price, max_leverage=leverage)
    actual = constrained.size(balance, risk, price, max_leverage=leverage)

    regression_note(
        "constrained_unbounded",
        {
            "balance": balance,
            "risk": risk,
            "price": price,
            "leverage": leverage,
            "expected": expected,
            "actual": actual,
        },
    )

    assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)


@seed(property_seed("test_constrained_sizer_respects_invariants"))
@settings(
    **property_settings("test_constrained_sizer_respects_invariants", max_examples=140)
)
@given(_portfolio_state_request())
def test_constrained_sizer_respects_invariants(
    payload: tuple[PositionSizingRequest, PortfolioState, PositionSizingConstraints],
) -> None:
    request, state, constraints = payload
    assume(request.price > 0.0)
    # Avoid extreme edge cases where tiny equity leads to numerical instability
    assume(state.equity == 0.0 or state.equity >= 1e-100)
    # Ensure positions don't exceed equity by unreasonable ratios
    for pos_val in state.positions.values():
        if state.equity > 0:
            assume(abs(pos_val * request.price / state.equity) < 1e20)
    sizer = ConstrainedPositionSizer(constraints=constraints)
    result = sizer.size_order(request, state)

    event(f"direction={request.direction}")
    event(f"capital-positive={state.equity > 0}")
    regression_note(
        "sizer_case",
        {
            "direction": request.direction,
            "equity": state.equity,
            "balance": state.balance,
            "risk_fraction": request.risk_fraction,
            "applied_fraction": result.applied_fraction,
        },
    )

    assert math.isfinite(result.order_quantity)
    assert math.isfinite(result.target_position)
    assert math.isfinite(result.applied_fraction)

    if state.equity <= 0.0 or request.direction == 0:
        assert math.isclose(result.order_quantity, 0.0, abs_tol=1e-12)

    min_size = max(constraints.min_order_size, request.min_trade_qty)
    if abs(result.order_quantity) < min_size - 1e-12:
        cap = None
        if constraints.max_order_size is not None:
            cap = constraints.max_order_size
        if request.max_trade_qty is not None:
            cap = (
                request.max_trade_qty
                if cap is None
                else min(cap, request.max_trade_qty)
            )
        if cap is None or cap >= min_size - 1e-12:
            assert math.isclose(result.order_quantity, 0.0, abs_tol=1e-12)

    if constraints.max_order_size is not None:
        assert abs(result.order_quantity) <= constraints.max_order_size + 1e-9
    if request.max_trade_qty is not None:
        assert abs(result.order_quantity) <= request.max_trade_qty + 1e-9

    if state.equity > 0.0:
        assert abs(result.applied_fraction) <= constraints.max_leverage + 1e-9
        assert (
            abs(result.target_position * request.price)
            <= state.equity * constraints.max_leverage + 1e-6
        )

    if request.direction > 0:
        assert result.applied_fraction >= -1e-12
    elif request.direction < 0:
        assert result.applied_fraction <= 1e-12
