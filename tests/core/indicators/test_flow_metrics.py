# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for QILM and FMN flow metrics.

These tests pin down the exact numerical behaviour of both indicators so
any future refactor has to deliberately re-approve the semantics. The
golden fixtures come from the original archive source document (see
``core/indicators/flow_metrics.py`` docstring).
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
import pytest
from numpy.typing import NDArray

from core.indicators import compute_fmn, compute_qilm
from core.indicators.flow_metrics import QILM_DEFAULT_EPS

Vec: TypeAlias = NDArray[np.float64]


def _zeros(n: int) -> Vec:
    out: Vec = np.zeros(n, dtype=np.float64)
    return out


def _full(n: int, value: float) -> Vec:
    out: Vec = np.full(n, value, dtype=np.float64)
    return out


def _arr(values: list[float]) -> Vec:
    out: Vec = np.array(values, dtype=np.float64)
    return out


# ---------- QILM ---------- #


def test_qilm_first_bar_is_nan() -> None:
    """Index 0 has no ΔOI defined → must be NaN."""
    n = 5
    qilm = compute_qilm(
        open_interest=_full(n, 100.0),
        volume=_full(n, 10.0),
        delta_volume=_full(n, 1.0),
        hidden_volume=_zeros(n),
        atr=_full(n, 1.0),
    )
    assert np.isnan(qilm[0])


def test_qilm_positive_when_oi_grows_with_flow() -> None:
    """New OI + same-sign flow → bullish signal > 0."""
    oi = _arr([100.0, 110.0, 125.0, 140.0])
    vol = _arr([10.0, 12.0, 14.0, 16.0])
    dv = _arr([1.0, 3.0, 5.0, 7.0])  # all positive
    hv = _zeros(4)
    atr = _full(4, 1.0)

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    # Bars 1..3 have ΔOI > 0 and sign(ΔV) > 0 → S = +1 → QILM > 0.
    assert np.all(qilm[1:] > 0.0)


def test_qilm_negative_when_oi_shrinks() -> None:
    """ΔOI < 0 → positions closing → S = −1 → QILM < 0."""
    oi = _arr([100.0, 90.0, 80.0])
    vol = _arr([10.0, 10.0, 10.0])
    dv = _arr([1.0, 1.0, 1.0])
    hv = _zeros(3)
    atr = _full(3, 1.0)

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    assert qilm[1] < 0.0
    assert qilm[2] < 0.0


def test_qilm_negative_on_contrarian_flow() -> None:
    """ΔOI > 0 but flow sign disagrees → contrarian → S = −1."""
    oi = _arr([100.0, 110.0])
    vol = _arr([10.0, 10.0])
    dv = _arr([0.0, -5.0])  # sells on OI expansion
    hv = _zeros(2)
    atr = _full(2, 1.0)

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    assert qilm[1] < 0.0


def test_qilm_exact_formula() -> None:
    """Pin the exact value to catch accidental refactors."""
    oi = _arr([100.0, 150.0])
    vol = _arr([100.0, 100.0])
    dv = _arr([0.0, 800.0])
    hv = _arr([0.0, 50.0])
    atr = _arr([1.5, 1.5])

    qilm = compute_qilm(oi, vol, dv, hv, atr)

    # S = +1 (ΔOI = 50 > 0 and sign(dv) > 0)
    # magnitude = (|50| / 1.5) * (|800| + 50) / (100 + 50)
    #           = 33.333... * 850 / 150
    expected = (50.0 / 1.5) * (850.0 / 150.0)
    assert qilm[1] == pytest.approx(expected, rel=1e-9)


def test_qilm_degenerate_atr_returns_nan() -> None:
    """ATR == 0 must produce NaN, not raise or silently explode."""
    oi = _arr([100.0, 110.0])
    vol = _arr([10.0, 10.0])
    dv = _arr([1.0, 1.0])
    hv = _zeros(2)
    atr = _arr([1.0, 0.0])

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    assert np.isnan(qilm[1])


def test_qilm_degenerate_volume_returns_nan() -> None:
    """V + HV == 0 → NaN."""
    oi = _arr([100.0, 110.0])
    vol = _arr([10.0, 0.0])
    dv = _arr([1.0, 0.0])
    hv = _zeros(2)
    atr = _full(2, 1.0)

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    assert np.isnan(qilm[1])


def test_qilm_rejects_short_arrays() -> None:
    with pytest.raises(ValueError, match="len>=2"):
        compute_qilm(
            open_interest=_arr([100.0]),
            volume=_arr([10.0]),
            delta_volume=_arr([1.0]),
            hidden_volume=_arr([0.0]),
            atr=_arr([1.0]),
        )


def test_qilm_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="length"):
        compute_qilm(
            open_interest=_arr([100.0, 110.0]),
            volume=_arr([10.0, 10.0, 10.0]),  # wrong
            delta_volume=_arr([1.0, 1.0]),
            hidden_volume=_arr([0.0, 0.0]),
            atr=_arr([1.0, 1.0]),
        )


def test_qilm_default_eps_is_safe() -> None:
    """Denominators just above eps must still compute finite values."""
    oi = _arr([100.0, 110.0])
    vol = _arr([10.0, 10.0 * QILM_DEFAULT_EPS * 2])
    dv = _arr([1.0, 1.0])
    hv = _zeros(2)
    atr = _arr([1.0, QILM_DEFAULT_EPS * 2])

    qilm = compute_qilm(oi, vol, dv, hv, atr)
    assert np.isfinite(qilm[1])


# ---------- FMN ---------- #


def test_fmn_output_in_unit_interval() -> None:
    """tanh is bounded in (−1, 1) by construction."""
    rng = np.random.default_rng(seed=42)
    n = 200
    bid: Vec = rng.uniform(10.0, 100.0, size=n).astype(np.float64)
    ask: Vec = rng.uniform(10.0, 100.0, size=n).astype(np.float64)
    dv: Vec = rng.uniform(-5.0, 5.0, size=n).astype(np.float64)

    fmn = compute_fmn(bid, ask, dv)
    finite = fmn[np.isfinite(fmn)]
    assert np.all(finite > -1.0)
    assert np.all(finite < 1.0)


def test_fmn_strong_buy_pressure_is_positive() -> None:
    """All-positive delta_vol + bid > ask → FMN > 0."""
    n = 20
    bid = _full(n, 100.0)
    ask = _full(n, 50.0)
    dv = _full(n, 10.0)

    fmn = compute_fmn(bid, ask, dv)
    # Rolling max-scaled CVD → argument big → near +1
    assert fmn[-1] > 0.5


def test_fmn_strong_sell_pressure_is_negative() -> None:
    n = 20
    bid = _full(n, 50.0)
    ask = _full(n, 100.0)
    dv = _full(n, -10.0)

    fmn = compute_fmn(bid, ask, dv)
    assert fmn[-1] < -0.5


def test_fmn_ob_imbalance_only() -> None:
    """Zero delta volume → FMN should reflect only OB imbalance via tanh."""
    n = 10
    bid = _full(n, 80.0)
    ask = _full(n, 20.0)
    dv = _zeros(n)

    fmn = compute_fmn(bid, ask, dv)
    # OB_imbalance = (80-20)/(80+20) = 0.6, CVD=0 → tanh(0.6+0)
    expected = float(np.tanh(0.6))
    assert fmn[-1] == pytest.approx(expected, rel=1e-9)


def test_fmn_degenerate_book_returns_nan() -> None:
    """bid + ask == 0 → NaN at that index."""
    bid = _arr([10.0, 0.0, 10.0])
    ask = _arr([10.0, 0.0, 10.0])
    dv = _arr([1.0, 1.0, 1.0])

    fmn = compute_fmn(bid, ask, dv)
    assert np.isnan(fmn[1])
    assert np.isfinite(fmn[0])
    assert np.isfinite(fmn[2])


def test_fmn_rejects_short_arrays() -> None:
    with pytest.raises(ValueError, match="len>=2"):
        compute_fmn(
            bid_volume=_arr([10.0]),
            ask_volume=_arr([10.0]),
            delta_volume=_arr([1.0]),
        )


def test_fmn_rejects_small_window() -> None:
    with pytest.raises(ValueError, match="cvd_window"):
        compute_fmn(
            bid_volume=_arr([10.0, 10.0]),
            ask_volume=_arr([10.0, 10.0]),
            delta_volume=_arr([1.0, 1.0]),
            cvd_window=1,
        )


def test_fmn_custom_weights() -> None:
    """Custom weights must be honoured in the tanh argument."""
    n = 5
    bid = _full(n, 80.0)
    ask = _full(n, 20.0)
    dv = _zeros(n)

    fmn_default = compute_fmn(bid, ask, dv, weights=(1.0, 1.0))
    fmn_half = compute_fmn(bid, ask, dv, weights=(0.5, 1.0))

    # Smaller w1 halves the OB contribution; tanh is monotonic increasing.
    assert fmn_half[-1] < fmn_default[-1]
    assert fmn_half[-1] > 0.0
