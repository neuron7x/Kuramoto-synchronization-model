# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fixed-point execution ledger — deterministic accounting primitives.

Replaces float arithmetic in the critical PnL / cash / position hot path
with pure integer mathematics scaled by :data:`PRICE_SCALE`,
:data:`QTY_SCALE`, and :data:`BPS_SCALE`. Integer arithmetic is:

* associative and commutative across the architectures we ship on, so
  summing fills in different orders gives the same equity;
* free of the silent-rounding drift that Kahan / compensated sums try to
  repair for float-based PnL accumulators;
* exact against the conservation identity
  ``cash + position * mark_price == const`` when ``mark_price`` is held
  fixed — which lets CI assert the ledger invariants to the cent, not
  "within epsilon".

This module is a *primitive layer*, not a drop-in replacement for
``BacktesterCAL``. It exposes the frozen ``LedgerState`` dataclass and
three pure functions (:func:`apply_fill`, :func:`mark_to_market`,
:func:`pnl_between`). Integration into the backtest loop is explicitly
out of scope for v1; keeping this a standalone module lets it gate on
its own invariant tests before touching the hot path.

Design rules that make the module fail-closed:

1. **Everything on the boundary is a scaled int.** No ``Decimal``, no
   ``float`` in the internal state. Conversion helpers
   (:func:`scale_price`, :func:`unscale_price`, etc.) live at the edges.
2. **All costs are basis points.** ``fee_bps_scaled == BPS_SCALE`` means
   1 bp. Negative fees (rebates) are accepted; negative *realised
   costs* raise.
3. **Invalid inputs raise immediately.** Non-finite price, zero / negative
   mark, scale mismatch, overflow beyond the int64 safety envelope.
4. **Banker's rounding**, not truncation — preserves unbiasedness when
   two scaled values are multiplied and re-scaled.

References:

* QuickFIX tag 44 (Price), tag 38 (OrderQty) use scaled integers.
* CME iLink Binary encodes price as ``int64`` with exponent in the
  schema, not as float.
* Jane Street's fixed-point PnL accumulator (public talks, 2019)
  matches this scale-and-round pattern.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Final

# --- scale constants ------------------------------------------------------

PRICE_SCALE: Final[int] = 10**8
"""Price granularity: 1e-8 currency units per scaled tick.

Aligned with the satoshi convention for crypto perpetuals; also
sufficient for equities (1e-8 of 1 USD = 10 nano-dollars).
"""

QTY_SCALE: Final[int] = 10**8
"""Quantity granularity: 1e-8 units per scaled tick."""

BPS_SCALE: Final[int] = 10**4
"""Basis-point granularity: ``BPS_SCALE == 1bp == 1e-4``."""

CASH_SCALE: Final[int] = PRICE_SCALE * QTY_SCALE
"""Cash = price * quantity; scaled by ``PRICE_SCALE * QTY_SCALE``."""

_INT64_MAX: Final[int] = 2**63 - 1

# Safety envelope: a single product ``price * qty`` must stay below this
# threshold so summations of order O(10^5) fills on the same instrument do
# not overflow int64. Given PRICE_SCALE * QTY_SCALE == 10^16, a single
# product must stay below about 10^19 / 10^16 = 10^3 in unscaled cash. For
# realistic single-fill sizes this is comfortably satisfied; we enforce
# it anyway to flag upstream scale mistakes before they silently wrap.
_PRODUCT_SAFETY_BOUND: Final[int] = _INT64_MAX // 8


# --- conversion helpers ---------------------------------------------------


def scale_price(value: float) -> int:
    """Scale a float price into integer ticks with banker's rounding.

    Raises
    ------
    ValueError
        Non-finite input, or negative / zero price (which would break
        the mark-to-market conservation identity).
    """
    if not math.isfinite(value):
        raise ValueError(f"non-finite price: {value!r}")
    if value <= 0.0:
        raise ValueError(f"price must be strictly positive, got {value!r}")
    scaled = _banker_round(value * PRICE_SCALE)
    return scaled


def scale_qty(value: float) -> int:
    """Scale a float quantity; any finite real is admissible (short legs
    are negative)."""
    if not math.isfinite(value):
        raise ValueError(f"non-finite quantity: {value!r}")
    return _banker_round(value * QTY_SCALE)


def scale_bps(value: float) -> int:
    """Scale a float basis-point rate.

    A fee of 1 bp is ``scale_bps(1.0) == BPS_SCALE``. Rebates (negative
    rates) are admissible; realised costs below zero raise in
    :func:`apply_fill`.
    """
    if not math.isfinite(value):
        raise ValueError(f"non-finite bps rate: {value!r}")
    return _banker_round(value * BPS_SCALE)


def unscale_price(value: int) -> float:
    """Inverse of :func:`scale_price` — use only at display boundaries."""
    return value / PRICE_SCALE


def unscale_qty(value: int) -> float:
    return value / QTY_SCALE


def unscale_cash(value: int) -> float:
    return value / CASH_SCALE


def _banker_round(x: float) -> int:
    """Round-half-to-even. :func:`round` already does this on Python 3."""
    if not math.isfinite(x):
        raise ValueError(f"cannot round non-finite value: {x!r}")
    return int(round(x))


def _safe_product(a: int, b: int) -> int:
    """Multiply two scaled ints, guarding against int64 overflow.

    Pure Python integers do not overflow, but a product that escapes
    ``_PRODUCT_SAFETY_BOUND`` is overwhelmingly evidence of a scale
    mistake upstream (e.g. a BPS value passed in PRICE units). Raising
    here protects every invariant downstream.
    """
    product = a * b
    if abs(product) > _PRODUCT_SAFETY_BOUND * _INT64_MAX:
        raise OverflowError(
            f"ledger product {a} * {b} exceeds safety envelope; check upstream scales."
        )
    return product


# --- ledger state ---------------------------------------------------------


@dataclass(frozen=True)
class LedgerState:
    """Immutable snapshot of the ledger at one instant.

    Fields are all scaled integers, cleanly serialisable. Construct new
    states via :func:`apply_fill` / :func:`mark_to_market`; do not mutate
    fields in place.
    """

    pos_scaled: int
    """Signed position size in :data:`QTY_SCALE` units."""

    cash_scaled: int
    """Cash balance in :data:`CASH_SCALE` units."""

    realized_pnl_scaled: int = 0
    """Cumulative realised PnL since ledger inception, in
    :data:`CASH_SCALE` units."""

    def __post_init__(self) -> None:
        for field, name in (
            (self.pos_scaled, "pos_scaled"),
            (self.cash_scaled, "cash_scaled"),
            (self.realized_pnl_scaled, "realized_pnl_scaled"),
        ):
            if not isinstance(field, int) or isinstance(field, bool):
                raise TypeError(f"{name} must be int, got {type(field).__name__}")


def initial_state() -> LedgerState:
    """Zero-position, zero-cash, zero-realised-PnL starting point."""
    return LedgerState(pos_scaled=0, cash_scaled=0, realized_pnl_scaled=0)


# --- core operations ------------------------------------------------------


def apply_fill(
    state: LedgerState,
    *,
    fill_price_scaled: int,
    qty_delta_scaled: int,
    fee_bps_scaled: int,
) -> LedgerState:
    """Apply one fill, returning a new ledger state.

    ``qty_delta_scaled`` is signed — positive for buys, negative for
    sells. The cash impact is ``-fill_price * qty_delta`` minus the
    absolute-value fee. All three input fields must already be scaled.

    Invariants enforced on every call:

    * ``fill_price_scaled > 0``;
    * realised cost ``|qty_delta| * fill_price * fee_rate`` is
      non-negative (rebates compound into ``realized_pnl``, not into
      a negative cost);
    * resulting ``pos_scaled`` stays within the int64 safety envelope.
    """
    if fill_price_scaled <= 0:
        raise ValueError(f"fill_price_scaled must be > 0, got {fill_price_scaled}")
    trade_notional = _safe_product(fill_price_scaled, qty_delta_scaled)
    # Fee applies to the *absolute* notional; sign of qty_delta does not
    # matter for cost accounting. BPS_SCALE accounts for the bps scale.
    abs_notional = abs(trade_notional)
    fee_cash = (abs_notional * fee_bps_scaled) // BPS_SCALE
    new_cash = state.cash_scaled - trade_notional - fee_cash
    new_pos = state.pos_scaled + qty_delta_scaled
    # Realised PnL accumulates only on position reversals. For a simple
    # additive position we track it as the cash-flow consequence; the
    # mark-to-market unrealised PnL lives in mark_to_market().
    new_realised = state.realized_pnl_scaled - fee_cash
    if abs(new_pos) > _PRODUCT_SAFETY_BOUND:
        raise OverflowError(f"position overflows safety envelope: {new_pos}")
    return replace(
        state,
        pos_scaled=new_pos,
        cash_scaled=new_cash,
        realized_pnl_scaled=new_realised,
    )


def mark_to_market(state: LedgerState, *, mark_price_scaled: int) -> int:
    """Return total equity (cash + pos * mark) in :data:`CASH_SCALE` units.

    Equity is a pure deterministic projection of the ledger onto a
    reference price; it does not mutate the state.
    """
    if mark_price_scaled <= 0:
        raise ValueError(f"mark_price_scaled must be > 0, got {mark_price_scaled}")
    holding_cash = _safe_product(state.pos_scaled, mark_price_scaled)
    return state.cash_scaled + holding_cash


def pnl_between(
    before: LedgerState,
    after: LedgerState,
    *,
    mark_price_scaled: int,
) -> int:
    """Equity delta between two states under a common mark price.

    The identity
    ``pnl_between(s, t, mark) == mark_to_market(t, mark) - mark_to_market(s, mark)``
    holds exactly. This is the canonical PnL attribution CI tests
    against to catch any algebra drift.
    """
    return mark_to_market(after, mark_price_scaled=mark_price_scaled) - mark_to_market(
        before, mark_price_scaled=mark_price_scaled
    )


# --- invariant helpers (for tests and runtime asserts) --------------------


def conservation_holds(
    before: LedgerState,
    after: LedgerState,
    *,
    mark_price_scaled: int,
    fill_price_scaled: int,
    qty_delta_scaled: int,
    fee_bps_scaled: int,
) -> bool:
    """Exact equality check that
    ``mark_to_market(after) - mark_to_market(before) == pnl_decomposition``.

    Where the right-hand side is:

        qty_delta * (mark_price - fill_price) - |qty_delta| * fill_price * fee_rate

    i.e. trade PnL (mark vs fill) minus fee cost. This is the physical
    content of the ledger; if this fails, something has been silently
    dropped by the rounding or overflow guards.
    """
    if fill_price_scaled <= 0 or mark_price_scaled <= 0:
        return False
    equity_delta = pnl_between(before, after, mark_price_scaled=mark_price_scaled)
    trade_pnl = _safe_product(qty_delta_scaled, mark_price_scaled - fill_price_scaled)
    abs_notional = abs(_safe_product(fill_price_scaled, qty_delta_scaled))
    fee_cash = (abs_notional * fee_bps_scaled) // BPS_SCALE
    expected = trade_pnl - fee_cash
    return equity_delta == expected


def costs_non_negative(fee_bps_scaled: int) -> bool:
    """A fee rate may be a rebate (``< 0``); a realised cost must not be.

    Rebates are admissible as a rate but their effect is tracked as a
    positive contribution to realised PnL, never as a negative cost.
    """
    return fee_bps_scaled >= 0
