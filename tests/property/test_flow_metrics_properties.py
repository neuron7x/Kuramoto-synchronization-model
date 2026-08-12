# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based tests for QILM and FMN flow metrics.

These tests pin down universal invariants that must hold for **every**
generated input, not just the hand-crafted fixtures in
``test_flow_metrics.py``. If Hypothesis finds a counter-example it is
an invariant violation, not an edge-case nit.

Invariants
----------

**QILM**
  1. Index 0 is always NaN (no ΔOI defined).
  2. Every non-NaN output is finite (no ±inf leakage).
  3. Degenerate denominators (ATR = 0) propagate to NaN, they never
     silently produce ±inf.
  4. Scale-equivariance in ATR: dividing ATR by k > 0 multiplies |QILM|
     by exactly k (pure algebraic check of the formula).

**FMN**
  1. |FMN_t| < 1 strictly for every finite output (tanh saturation).
  2. Degenerate bars (bid + ask = 0) propagate to NaN.
  3. Sign-flip symmetry: swapping bid↔ask and negating CVD flips FMN
     sign at every finite index.
"""

from __future__ import annotations

from typing import Any, TypeAlias, cast

import numpy as np
import pytest
from numpy.typing import NDArray

try:  # pragma: no cover - optional dependency boundary
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.indicators import compute_fmn, compute_qilm

Vec: TypeAlias = NDArray[np.float64]


def _to_vec(values: list[float]) -> Vec:
    out: Vec = np.asarray(values, dtype=np.float64)
    return out


_FLOAT_POS = st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False)
_FLOAT_ANY = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_FLOAT_NON_NEG = st.floats(min_value=0.0, max_value=1e4, allow_nan=False, allow_infinity=False)

_VEC_POS_SMALL = st.lists(_FLOAT_POS, min_size=3, max_size=20).map(_to_vec)
_VEC_POS = st.lists(_FLOAT_POS, min_size=2, max_size=30).map(_to_vec)
_VEC_ANY = st.lists(_FLOAT_ANY, min_size=2, max_size=30).map(_to_vec)
_VEC_NON_NEG = st.lists(_FLOAT_NON_NEG, min_size=2, max_size=30).map(_to_vec)
_VEC_BID = st.lists(
    st.floats(min_value=1.0, max_value=1e5, allow_nan=False, allow_infinity=False),
    min_size=3,
    max_size=40,
).map(_to_vec)
_VEC_FLOW = st.lists(
    st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
    min_size=3,
    max_size=40,
).map(_to_vec)


# ---- QILM invariants ---- #


@given(
    oi=_VEC_POS,
    scale_factor=st.floats(min_value=0.1, max_value=10.0),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_qilm_atr_scale_equivariance(oi: Vec, scale_factor: float) -> None:
    """|QILM| scales inversely with ATR (algebraic identity)."""
    n = oi.shape[0]
    vol: Vec = np.full(n, 100.0, dtype=np.float64)
    dv: Vec = np.full(n, 50.0, dtype=np.float64)
    hv: Vec = np.zeros(n, dtype=np.float64)
    atr: Vec = np.full(n, 2.0, dtype=np.float64)

    base = compute_qilm(oi, vol, dv, hv, atr)
    scaled = compute_qilm(oi, vol, dv, hv, atr / scale_factor)

    mask = np.isfinite(base) & np.isfinite(scaled)
    if bool(mask.any()):
        np.testing.assert_allclose(
            scaled[mask],
            base[mask] * scale_factor,
            rtol=1e-9,
            atol=1e-12,
        )


@given(
    oi=_VEC_POS,
    vol=_VEC_POS,
    dv=_VEC_ANY,
    hv=_VEC_NON_NEG,
    atr=_VEC_POS,
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_qilm_finite_values_are_never_infinite(
    oi: Vec,
    vol: Vec,
    dv: Vec,
    hv: Vec,
    atr: Vec,
) -> None:
    """Every non-NaN QILM value is finite — no ±inf leaks."""
    n = int(min(oi.size, vol.size, dv.size, hv.size, atr.size))
    if n < 2:
        return
    qilm = compute_qilm(oi[:n], vol[:n], dv[:n], hv[:n], atr[:n])

    finite_part = qilm[~np.isnan(qilm)]
    assert bool(np.all(np.isfinite(finite_part))), "QILM produced ±inf"
    assert bool(np.isnan(qilm[0])), "Index 0 must be NaN"


@given(oi=_VEC_POS_SMALL)
@settings(max_examples=30, deadline=None)
def test_qilm_zero_atr_propagates_nan(oi: Vec) -> None:
    """A bar with ATR=0 must emit NaN at that index, not ±inf."""
    n = int(oi.size)
    if n < 3:
        return
    vol: Vec = np.full(n, 100.0, dtype=np.float64)
    dv: Vec = np.full(n, 10.0, dtype=np.float64)
    hv: Vec = np.zeros(n, dtype=np.float64)
    atr: Vec = np.full(n, 1.0, dtype=np.float64)
    atr[n // 2] = 0.0

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    assert bool(np.isnan(qilm[n // 2]))


# ---- FMN invariants ---- #


@given(
    bid=_VEC_BID,
    ask=_VEC_BID,
    dv=_VEC_FLOW,
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_fmn_always_bounded_in_unit_interval(bid: Vec, ask: Vec, dv: Vec) -> None:
    """|FMN| < 1 strictly at every finite index (tanh saturation)."""
    n = int(min(bid.size, ask.size, dv.size))
    if n < 2:
        return
    fmn = compute_fmn(bid[:n], ask[:n], dv[:n])
    finite = fmn[np.isfinite(fmn)]
    if finite.size == 0:
        return
    assert bool(np.all(finite > -1.0))
    assert bool(np.all(finite < 1.0))


@given(
    bid=_VEC_BID,
    ask=_VEC_BID,
    dv=_VEC_FLOW,
)
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_fmn_sign_flip_symmetry(bid: Vec, ask: Vec, dv: Vec) -> None:
    """Swap bid↔ask AND negate dv → FMN flips sign at every finite index.

    ``FMN(bid, ask, dv) = tanh(w1·OB_imbalance + w2·CVD/scale)``.
    Swapping the book flips ``OB_imbalance``. Negating ``dv`` negates
    the CVD. Both contributions flip sign → the tanh argument flips →
    FMN flips. This is a pure algebraic identity.
    """
    n = int(min(bid.size, ask.size, dv.size))
    if n < 2:
        return
    b = bid[:n]
    a = ask[:n]
    d = dv[:n]

    original = compute_fmn(b, a, d)
    flipped = compute_fmn(a, b, -d)

    mask = np.isfinite(original) & np.isfinite(flipped)
    if not bool(mask.any()):
        return
    np.testing.assert_allclose(
        flipped[mask],
        -original[mask],
        atol=1e-9,
        rtol=1e-9,
    )


@given(
    n=st.integers(min_value=3, max_value=30),
    window=st.integers(min_value=2, max_value=5),
)
@settings(max_examples=30, deadline=None)
def test_fmn_degenerate_book_row_returns_nan(n: int, window: int) -> None:
    """A bar with bid+ask == 0 must emit NaN at that index."""
    bid: Vec = np.full(n, 10.0, dtype=np.float64)
    ask: Vec = np.full(n, 10.0, dtype=np.float64)
    dv: Vec = np.zeros(n, dtype=np.float64)
    bad_idx = n - 1
    bid[bad_idx] = 0.0
    ask[bad_idx] = 0.0

    fmn = compute_fmn(bid, ask, dv, cvd_window=window)
    # Use .item() to obtain a Python bool for the assertion under strict mypy.
    val = cast(Any, fmn[bad_idx])
    assert bool(np.isnan(val))
