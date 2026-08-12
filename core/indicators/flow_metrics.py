# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Flow-based microstructure metrics: QILM and FMN.

Both indicators were distilled from the author's crypto-research archive
(``/home/neuro7/Downloads/криптовалюта/04_ЕМЕРДЖЕНТНІ_КОГНІТИВНІ_СИСТЕМИ/
Повна технічна реалізація когнітивно-трейдингової системи Neuron7X.odt``)
and re-implemented here as pure-numpy vector operations so they can feed
the ``core/indicators`` pipeline alongside Kuramoto/Ricci/Hurst.

Both are *precursor* features and require genuine microstructure data
(open interest, delta volume, order-book bid/ask volume, CVD). They
emit ``np.nan`` at positions where inputs are degenerate — the caller
must drop NaNs before routing the signal into a decision gate.

QILM — Quantum Integrated Liquidity Metric
-------------------------------------------

    S_t = +1  if ΔOI_t > 0 and sign(ΔV_t) == sign(ΔOI_t)
        = -1  otherwise

    QILM_t = S_t · ( |ΔOI_t| / ATR_t ) · ( |ΔV_t| + HV_t ) / ( V_t + HV_t )

where

    ΔOI_t  = OI_t - OI_{t-1}         change in open interest
    ΔV_t   = buy_volume_t - sell_volume_t  (signed delta volume)
    HV_t   = hidden volume (iceberg / dark)
    V_t    = total visible volume
    ATR_t  = 14-period Average True Range (or supplied scale)

**Interpretation.** QILM > 0 means new open interest is entering the
book in the same direction as the signed volume — fresh money pushing a
trend. QILM < 0 means OI is shrinking OR the signed flow contradicts the
OI delta — positions are closing (profit-taking, stop-outs) or the print
is adversarial (spoof + hunt).

FMN — Flow Momentum Network
----------------------------

    OB_imbalance_t = (bid_vol_t - ask_vol_t) / (bid_vol_t + ask_vol_t)
    CVD_t           = Σ_{i≤t} ΔV_i
    FMN_t           = tanh( w1·OB_imbalance_t + w2·(CVD_t / scale) )

Default weights ``w1 = w2 = 1.0`` (uniform contribution). ``scale`` is a
rolling CVD normaliser — by default the rolling max-abs over the lookback
window, which keeps the tanh argument well-conditioned across regimes.

FMN saturates at ±1. Sustained |FMN| > 0.6 is a strong one-sided flow.

Design notes
------------
* Both functions are **stateless** — no side effects, deterministic,
  mypy --strict clean.
* Degenerate denominators (``V_t + HV_t == 0``, ``bid+ask == 0``,
  ``ATR_t == 0``) return ``np.nan`` at that index rather than raising.
  The caller owns the NaN policy (see ``agent/invariants.py`` INV_004).
* Shapes are strict: all inputs must be 1-D ``float64`` arrays of equal
  length. ``_validate_1d`` enforces this once at the boundary.
"""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "QILM_DEFAULT_EPS",
    "FMN_DEFAULT_WEIGHTS",
    "compute_qilm",
    "compute_fmn",
]

#: Numerical floor for denominators. Chosen to be well below any
#: plausible volume/ATR but large enough to avoid float underflow.
QILM_DEFAULT_EPS: Final[float] = 1e-12

#: Default ``(w1, w2)`` for FMN — uniform weighting of OB imbalance and
#: normalised CVD.
FMN_DEFAULT_WEIGHTS: Final[tuple[float, float]] = (1.0, 1.0)


def _validate_1d(name: str, arr: NDArray[np.float64], expected_len: int) -> NDArray[np.float64]:
    """Boundary-level shape/dtype check. Called once per input."""
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    if arr.shape[0] != expected_len:
        raise ValueError(
            f"{name} length {arr.shape[0]} != expected {expected_len}",
        )
    if not np.issubdtype(arr.dtype, np.floating):
        raise TypeError(f"{name} must be float, got dtype {arr.dtype}")
    return arr.astype(np.float64, copy=False)


def compute_qilm(
    open_interest: NDArray[np.float64],
    volume: NDArray[np.float64],
    delta_volume: NDArray[np.float64],
    hidden_volume: NDArray[np.float64],
    atr: NDArray[np.float64],
    *,
    eps: float = QILM_DEFAULT_EPS,
) -> NDArray[np.float64]:
    """Quantum Integrated Liquidity Metric — see module docstring.

    Parameters
    ----------
    open_interest
        Open-interest series (absolute, not delta). ``len >= 2``.
    volume
        Total traded volume per bar (non-negative).
    delta_volume
        Signed delta volume = buy_volume − sell_volume.
    hidden_volume
        Estimated hidden / iceberg volume (non-negative).
    atr
        Positive volatility scale (e.g. 14-period ATR). Zeros → NaN.
    eps
        Denominator floor. Do not lower — ``1e-12`` is already below
        float round-off on practical volumes.

    Returns
    -------
    qilm
        Array of the same length as ``open_interest``. Index 0 is always
        ``np.nan`` (no ΔOI defined). Degenerate bars return ``np.nan``.
    """
    n = open_interest.shape[0]
    if n < 2:
        raise ValueError(f"compute_qilm requires len>=2, got {n}")

    oi = _validate_1d("open_interest", open_interest, n)
    vol = _validate_1d("volume", volume, n)
    dv = _validate_1d("delta_volume", delta_volume, n)
    hv = _validate_1d("hidden_volume", hidden_volume, n)
    at = _validate_1d("atr", atr, n)

    d_oi = np.empty(n, dtype=np.float64)
    d_oi[0] = np.nan
    d_oi[1:] = np.diff(oi)

    # Direction: +1 if new OI enters in the direction of signed flow,
    # −1 otherwise. When ΔOI == 0 we have no direction → NaN.
    sign_dv = np.sign(dv)
    sign_oi = np.sign(d_oi)
    same_direction = (d_oi > 0.0) & (sign_dv == sign_oi) & (sign_dv != 0.0)
    s = np.where(same_direction, 1.0, -1.0)

    # Guard denominators.
    eff_vol = vol + hv
    safe_atr = np.where(at > eps, at, np.nan)
    safe_eff = np.where(eff_vol > eps, eff_vol, np.nan)

    magnitude = (np.abs(d_oi) / safe_atr) * ((np.abs(dv) + hv) / safe_eff)
    qilm = s * magnitude

    # Index 0 has no ΔOI → always NaN.
    qilm[0] = np.nan
    # Propagate NaNs from degenerate denominators / undefined direction.
    qilm = np.where(np.isfinite(magnitude), qilm, np.nan)
    return qilm.astype(np.float64, copy=False)


def compute_fmn(
    bid_volume: NDArray[np.float64],
    ask_volume: NDArray[np.float64],
    delta_volume: NDArray[np.float64],
    *,
    weights: tuple[float, float] = FMN_DEFAULT_WEIGHTS,
    cvd_window: int = 100,
    eps: float = QILM_DEFAULT_EPS,
) -> NDArray[np.float64]:
    """Flow Momentum Network — see module docstring.

    Parameters
    ----------
    bid_volume, ask_volume
        Visible resting volume on each side of the book per bar.
    delta_volume
        Signed per-bar delta volume (buy − sell). CVD is its cumsum.
    weights
        ``(w1, w2)`` mixing weights. Default ``(1.0, 1.0)``.
    cvd_window
        Lookback used to normalise the cumulative CVD so the tanh
        argument stays on the same scale across regimes. Computed as
        the rolling max-abs CVD over the last ``cvd_window`` bars.
        Must be ``>= 2``.
    eps
        Denominator floor.

    Returns
    -------
    fmn
        Array of the same length as inputs, values in ``(-1, 1)``.
        Indices with degenerate order-book (bid+ask ≈ 0) are NaN.
    """
    n = bid_volume.shape[0]
    if n < 2:
        raise ValueError(f"compute_fmn requires len>=2, got {n}")
    if cvd_window < 2:
        raise ValueError(f"cvd_window must be >=2, got {cvd_window}")

    bid = _validate_1d("bid_volume", bid_volume, n)
    ask = _validate_1d("ask_volume", ask_volume, n)
    dv = _validate_1d("delta_volume", delta_volume, n)

    total = bid + ask
    ob_imbalance = np.where(total > eps, (bid - ask) / np.where(total > eps, total, 1.0), np.nan)

    cvd = np.cumsum(dv)

    # Rolling max-abs scaler: at index t, scale = max(|CVD_{t-w+1..t}|).
    # Implementation uses ``sliding_window_view`` so the inner loop is
    # gone — the whole thing vectorises to a single ``max`` reduction
    # over a shape (n - w + 1, w) strided view. For t < w - 1 we fall
    # back to an expanding-window ``np.maximum.accumulate`` so the
    # early tail is still bounded without allocating a padded array.
    w1, w2 = weights
    abs_cvd = np.abs(cvd)
    # Expanding max for the warm-up region [0 .. cvd_window - 2].
    expanding_max = np.maximum.accumulate(abs_cvd)
    scale = expanding_max.copy()
    if n >= cvd_window:
        # Tail [cvd_window - 1 .. n - 1] uses the true rolling window.
        windows = np.lib.stride_tricks.sliding_window_view(abs_cvd, cvd_window)
        rolling_max = windows.max(axis=1)
        scale[cvd_window - 1 :] = rolling_max
    # Guard against zero scale → fall back to 1.0 so tanh arg stays finite.
    scale = np.where(scale > eps, scale, 1.0)

    cvd_scaled = cvd / scale
    arg = w1 * ob_imbalance + w2 * cvd_scaled
    fmn = np.tanh(arg)
    # Preserve NaN positions from degenerate order book.
    fmn = np.where(np.isfinite(ob_imbalance), fmn, np.nan)
    return fmn.astype(np.float64, copy=False)
