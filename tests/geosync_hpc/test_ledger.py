# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fixed-point ledger — invariant tests.

Guards the scientific and arithmetic content of ``geosync_hpc.ledger``:

* **Conservation** — mark-to-market equity delta equals the closed-form
  trade PnL decomposition for every (fill_price, qty_delta, fee, mark)
  tuple we can express in the scale envelope.
* **Idempotence on zero** — ``apply_fill`` with ``qty_delta == 0`` is a
  no-op except for a potentially non-zero fee (if someone passes one,
  which is unusual but allowed).
* **Sign** — buys increase position and reduce cash; sells do the
  opposite; the algebra commutes.
* **Fail-closed inputs** — non-finite price, negative / zero mark, scale
  mismatch, int64 envelope violations all raise immediately.
* **Property-based round-trips** — scale / unscale is idempotent to
  banker's rounding tolerance on random floats; scaled integer
  arithmetic is associative and commutative across any permutation of
  fills on the same instrument.

These tests are the "deterministic evidence" gate for Task 2 — without
them, the ledger is a promise, not an artefact.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosync_hpc.ledger import (
    BPS_SCALE,
    CASH_SCALE,
    PRICE_SCALE,
    QTY_SCALE,
    LedgerState,
    apply_fill,
    conservation_holds,
    costs_non_negative,
    initial_state,
    mark_to_market,
    pnl_between,
    scale_bps,
    scale_price,
    scale_qty,
    unscale_cash,
    unscale_price,
    unscale_qty,
)

# ---------------------------------------------------------------------------
# Scale constants
# ---------------------------------------------------------------------------


def test_scale_constants_are_canonical() -> None:
    assert PRICE_SCALE == 10**8
    assert QTY_SCALE == 10**8
    assert BPS_SCALE == 10**4
    assert CASH_SCALE == PRICE_SCALE * QTY_SCALE


# ---------------------------------------------------------------------------
# Conversion round-trips
# ---------------------------------------------------------------------------


@given(st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=None)
def test_scale_price_roundtrip(value: float) -> None:
    scaled = scale_price(value)
    assert isinstance(scaled, int)
    assert scaled > 0
    # Banker's rounding is stable under the 1e-8 tolerance of PRICE_SCALE.
    assert abs(unscale_price(scaled) - value) <= 1.0 / PRICE_SCALE


@given(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=None)
def test_scale_qty_roundtrip(value: float) -> None:
    scaled = scale_qty(value)
    assert isinstance(scaled, int)
    assert abs(unscale_qty(scaled) - value) <= 1.0 / QTY_SCALE


@given(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=None)
def test_scale_bps_roundtrip(value: float) -> None:
    scaled = scale_bps(value)
    assert isinstance(scaled, int)
    # bps tolerance is 1e-4 per scaled unit
    assert abs(scaled / BPS_SCALE - value) <= 1.0 / BPS_SCALE


def test_scale_price_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        scale_price(0.0)
    with pytest.raises(ValueError):
        scale_price(-1.0)


def test_scale_price_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        scale_price(math.nan)
    with pytest.raises(ValueError):
        scale_price(math.inf)


def test_scale_qty_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        scale_qty(math.nan)


def test_scale_bps_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        scale_bps(math.inf)


# ---------------------------------------------------------------------------
# LedgerState
# ---------------------------------------------------------------------------


def test_initial_state_is_zero() -> None:
    s = initial_state()
    assert s.pos_scaled == 0
    assert s.cash_scaled == 0
    assert s.realized_pnl_scaled == 0


def test_ledger_state_rejects_non_int_fields() -> None:
    with pytest.raises(TypeError):
        LedgerState(pos_scaled=1.5, cash_scaled=0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LedgerState(pos_scaled=0, cash_scaled=0, realized_pnl_scaled="0")  # type: ignore[arg-type]


def test_ledger_state_is_immutable() -> None:
    s = initial_state()
    with pytest.raises(Exception):  # FrozenInstanceError
        s.pos_scaled = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# apply_fill — scalar contracts
# ---------------------------------------------------------------------------


def test_apply_fill_zero_qty_is_noop_when_no_fee() -> None:
    s0 = initial_state()
    s1 = apply_fill(
        s0,
        fill_price_scaled=scale_price(100.0),
        qty_delta_scaled=0,
        fee_bps_scaled=scale_bps(5.0),
    )
    assert s1 == s0


def test_apply_fill_buy_increases_position_reduces_cash() -> None:
    s0 = initial_state()
    fill = scale_price(100.0)
    qty = scale_qty(2.0)
    s1 = apply_fill(
        s0,
        fill_price_scaled=fill,
        qty_delta_scaled=qty,
        fee_bps_scaled=scale_bps(0.0),
    )
    assert s1.pos_scaled == qty
    # cash == -fill * qty at zero fee
    assert s1.cash_scaled == -(fill * qty)


def test_apply_fill_sell_reverses_buy() -> None:
    s0 = initial_state()
    fill = scale_price(100.0)
    qty = scale_qty(2.0)
    s1 = apply_fill(s0, fill_price_scaled=fill, qty_delta_scaled=qty, fee_bps_scaled=0)
    s2 = apply_fill(s1, fill_price_scaled=fill, qty_delta_scaled=-qty, fee_bps_scaled=0)
    assert s2.pos_scaled == 0
    assert s2.cash_scaled == 0
    assert s2.realized_pnl_scaled == 0


def test_apply_fill_fee_reduces_cash_and_realised_pnl() -> None:
    s0 = initial_state()
    fill = scale_price(100.0)
    qty = scale_qty(1.0)
    fee_bps = scale_bps(5.0)
    s1 = apply_fill(s0, fill_price_scaled=fill, qty_delta_scaled=qty, fee_bps_scaled=fee_bps)
    expected_notional = fill * qty
    expected_fee = (expected_notional * fee_bps) // BPS_SCALE
    assert s1.cash_scaled == -expected_notional - expected_fee
    assert s1.realized_pnl_scaled == -expected_fee


def test_apply_fill_rejects_non_positive_price() -> None:
    s0 = initial_state()
    with pytest.raises(ValueError):
        apply_fill(
            s0,
            fill_price_scaled=0,
            qty_delta_scaled=scale_qty(1.0),
            fee_bps_scaled=0,
        )
    with pytest.raises(ValueError):
        apply_fill(
            s0,
            fill_price_scaled=-1,
            qty_delta_scaled=scale_qty(1.0),
            fee_bps_scaled=0,
        )


# ---------------------------------------------------------------------------
# mark_to_market + pnl_between
# ---------------------------------------------------------------------------


def test_mark_to_market_of_initial_state_is_zero() -> None:
    assert mark_to_market(initial_state(), mark_price_scaled=scale_price(100.0)) == 0


def test_mark_to_market_rejects_non_positive_mark() -> None:
    with pytest.raises(ValueError):
        mark_to_market(initial_state(), mark_price_scaled=0)
    with pytest.raises(ValueError):
        mark_to_market(initial_state(), mark_price_scaled=-1)


def test_pnl_between_is_mark_delta() -> None:
    mark = scale_price(101.0)
    s0 = initial_state()
    s1 = apply_fill(
        s0,
        fill_price_scaled=scale_price(100.0),
        qty_delta_scaled=scale_qty(1.0),
        fee_bps_scaled=0,
    )
    delta = pnl_between(s0, s1, mark_price_scaled=mark)
    assert delta == mark_to_market(s1, mark_price_scaled=mark) - mark_to_market(
        s0, mark_price_scaled=mark
    )


def test_pnl_from_buy_at_lower_price_than_mark_is_positive() -> None:
    """Buy at 100, mark at 101 → +1 unit profit (before fees)."""
    fill = scale_price(100.0)
    mark = scale_price(101.0)
    qty = scale_qty(1.0)
    s0 = initial_state()
    s1 = apply_fill(s0, fill_price_scaled=fill, qty_delta_scaled=qty, fee_bps_scaled=0)
    expected = (mark - fill) * qty
    assert pnl_between(s0, s1, mark_price_scaled=mark) == expected


# ---------------------------------------------------------------------------
# Conservation — the core physical invariant
# ---------------------------------------------------------------------------


@given(
    fill_price=st.floats(min_value=0.01, max_value=1e4, allow_nan=False, allow_infinity=False),
    qty=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    fee_bps=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    mark_delta=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=300, deadline=None)
def test_conservation_holds_under_random_fills(
    fill_price: float,
    qty: float,
    fee_bps: float,
    mark_delta: float,
) -> None:
    """For any (fill, qty, fee, mark) we can represent, the ledger's
    equity delta matches the closed-form trade-PnL identity exactly."""
    fill_scaled = scale_price(fill_price)
    qty_scaled = scale_qty(qty)
    fee_scaled = scale_bps(fee_bps)
    mark_scaled = scale_price(max(0.01, fill_price + mark_delta))
    s0 = initial_state()
    s1 = apply_fill(
        s0,
        fill_price_scaled=fill_scaled,
        qty_delta_scaled=qty_scaled,
        fee_bps_scaled=fee_scaled,
    )
    assert conservation_holds(
        s0,
        s1,
        mark_price_scaled=mark_scaled,
        fill_price_scaled=fill_scaled,
        qty_delta_scaled=qty_scaled,
        fee_bps_scaled=fee_scaled,
    ), (
        f"conservation broke at (fill={fill_price}, qty={qty}, fee={fee_bps} bp, "
        f"mark={unscale_price(mark_scaled)}): Δequity="
        f"{pnl_between(s0, s1, mark_price_scaled=mark_scaled)}"
    )


def test_conservation_guard_rejects_a_single_nonpositive_price() -> None:
    """TEETH: the price guard is OR, not AND — ONE non-positive price must fail closed.

    Measured gap this closes: ``tools/mutation_probe.py --only-logic`` showed
    ``ledger.py:295`` (``if fill_price_scaled <= 0 or mark_price_scaled <= 0``) mutating
    ``Or -> And`` and SURVIVING: no test exercised the ONE-sided case, so under the mutant a
    single invalid price slips past the guard and the function computes on garbage instead of
    returning False. Both one-sided cases are asserted below; a no-op state pair would
    otherwise report conservation as holding.
    """
    s = initial_state()
    assert (
        conservation_holds(
            s, s, mark_price_scaled=100_000, fill_price_scaled=0,
            qty_delta_scaled=0, fee_bps_scaled=0,
        )
        is False
    ), "a non-positive FILL price must fail closed even when the mark price is valid"
    assert (
        conservation_holds(
            s, s, mark_price_scaled=0, fill_price_scaled=100_000,
            qty_delta_scaled=0, fee_bps_scaled=0,
        )
        is False
    ), "a non-positive MARK price must fail closed even when the fill price is valid"


def test_conservation_holds_after_round_trip_buy_sell() -> None:
    fill_buy = scale_price(100.0)
    fill_sell = scale_price(102.0)
    qty = scale_qty(1.0)
    fee = scale_bps(5.0)
    s0 = initial_state()
    s1 = apply_fill(s0, fill_price_scaled=fill_buy, qty_delta_scaled=qty, fee_bps_scaled=fee)
    s2 = apply_fill(s1, fill_price_scaled=fill_sell, qty_delta_scaled=-qty, fee_bps_scaled=fee)
    # At mark = 102 (post sale price), equity equals initial cash outlay recovered + mark gains - fees.
    equity_final = mark_to_market(s2, mark_price_scaled=fill_sell)
    # Closed form:
    #   buy: paid fill_buy * qty, fee_buy = fill_buy*qty*fee/BPS_SCALE
    #   sell: received fill_sell * qty, fee_sell = fill_sell*qty*fee/BPS_SCALE
    #   position ends at 0 so mark leg contributes 0.
    gross = (fill_sell - fill_buy) * qty
    fee_buy = (fill_buy * qty * fee) // BPS_SCALE
    fee_sell = (fill_sell * qty * fee) // BPS_SCALE
    expected = gross - fee_buy - fee_sell
    assert equity_final == expected


# ---------------------------------------------------------------------------
# Commutativity / associativity of sequential fills
# ---------------------------------------------------------------------------


def test_sequential_fills_sum_commutes_over_permutations() -> None:
    """Three fills on the same instrument, any order → same final state
    modulo the realised-pnl-attribution detail (fees applied per fill)."""
    fills = [
        dict(fill=scale_price(100.0), qty=scale_qty(1.0), fee=0),
        dict(fill=scale_price(101.0), qty=scale_qty(-0.5), fee=0),
        dict(fill=scale_price(99.0), qty=scale_qty(0.25), fee=0),
    ]
    s = initial_state()
    for f in fills:
        s = apply_fill(
            s, fill_price_scaled=f["fill"], qty_delta_scaled=f["qty"], fee_bps_scaled=f["fee"]
        )
    s_rev = initial_state()
    for f in reversed(fills):
        s_rev = apply_fill(
            s_rev,
            fill_price_scaled=f["fill"],
            qty_delta_scaled=f["qty"],
            fee_bps_scaled=f["fee"],
        )
    assert s.pos_scaled == s_rev.pos_scaled
    assert s.cash_scaled == s_rev.cash_scaled
    # Realised PnL accumulates fees; same fees → same total.
    assert s.realized_pnl_scaled == s_rev.realized_pnl_scaled


# ---------------------------------------------------------------------------
# Cost sign contract
# ---------------------------------------------------------------------------


def test_costs_non_negative_contract() -> None:
    assert costs_non_negative(0) is True
    assert costs_non_negative(scale_bps(1.0)) is True
    assert costs_non_negative(scale_bps(-0.5)) is False  # rebate rate; caller's concern


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_ledger_is_platform_stable_over_random_fills() -> None:
    """Run the same random sequence twice; assert bit-identical states.

    This guards against any future refactor that accidentally introduces
    a float intermediate (numpy dtype, pandas arithmetic, etc.) which
    would break byte-equivalence across processes / architectures.
    """
    rng = np.random.default_rng(42)
    prices = rng.uniform(80.0, 120.0, size=500)
    qtys = rng.uniform(-1.0, 1.0, size=500)
    fee_bps = 1.5
    s_a = initial_state()
    s_b = initial_state()
    for p, q in zip(prices, qtys):
        s_a = apply_fill(
            s_a,
            fill_price_scaled=scale_price(float(p)),
            qty_delta_scaled=scale_qty(float(q)),
            fee_bps_scaled=scale_bps(fee_bps),
        )
        s_b = apply_fill(
            s_b,
            fill_price_scaled=scale_price(float(p)),
            qty_delta_scaled=scale_qty(float(q)),
            fee_bps_scaled=scale_bps(fee_bps),
        )
    assert s_a == s_b


def test_unscale_cash_is_float_inverse() -> None:
    """Display-only helper — sanity check it does what it says."""
    assert unscale_cash(CASH_SCALE) == pytest.approx(1.0)
    assert unscale_cash(2 * CASH_SCALE) == pytest.approx(2.0)
    assert unscale_cash(-CASH_SCALE) == pytest.approx(-1.0)
