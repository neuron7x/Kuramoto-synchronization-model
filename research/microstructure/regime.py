"""Regime detection for the L2 kill-test substrate.

Motivation: recursive / cyclic analysis on the collected 5h14m window
shows IC is intermittent — some time blocks produce IC > 0.15, others
invert to IC < -0.05. Full-window verdict averages these. The next
inevitable question is: *when* is the Ricci cross-sectional signal
predictive?

The regime_analysis step flagged cross-asset mean correlation
(`corr_mean` of mid-return) as the feature with the strongest
(directional) relationship to block IC. This module exposes that
feature as a per-row rolling score, and applies a threshold to build
a boolean regime mask consumable by `run_killtest(regime_mask=...)`.

Only one public function and one helper. No new dataclasses.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from research.microstructure.killtest import FeatureFrame

_MIN_WINDOW_ROWS: int = 60


def rolling_corr_regime(
    features: FeatureFrame,
    *,
    window_rows: int = 300,
) -> NDArray[np.float64]:
    """Rolling mean off-diagonal correlation of 1-sec mid-return across symbols.

    For each row t >= window_rows, compute the correlation matrix of the
    `window_rows` most-recent 1-sec log-return vectors (rows are time,
    columns are symbols). Return the mean of off-diagonal entries as the
    regime score. Earlier rows are NaN.

    High score ⇒ cross-asset correlation is high ⇒ cross-sectional Ricci
    signal has meaningful structure to measure. Low score ⇒ assets decouple,
    Ricci κ_min becomes noise-driven.
    """
    if window_rows < _MIN_WINDOW_ROWS:
        raise ValueError(f"window_rows must be >= {_MIN_WINDOW_ROWS}, got {window_rows}")
    if features.n_symbols < 2:
        raise ValueError(f"need >= 2 symbols for cross-asset correlation, got {features.n_symbols}")

    log_mid = np.log(features.mid)
    ret = np.vstack([np.zeros((1, features.n_symbols)), np.diff(log_mid, axis=0)])
    n = ret.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    eye_mask = ~np.eye(features.n_symbols, dtype=bool)

    for t in range(window_rows, n):
        block = ret[t - window_rows : t]
        if not np.all(np.isfinite(block)):
            continue
        std = block.std(axis=0)
        if np.any(std < 1e-14):
            continue
        corr_raw = np.corrcoef(block.T)
        corr = np.nan_to_num(np.asarray(corr_raw, dtype=np.float64), nan=0.0)
        out[t] = float(corr[eye_mask].mean())
    return out


def rolling_rv_regime(
    features: FeatureFrame,
    *,
    window_rows: int = 300,
) -> NDArray[np.float64]:
    """Rolling realized volatility (per-symbol mean) of 1-sec mid-return.

    Walk-forward analysis on the collected 5h14m substrate identified
    realized vol as the single strongest regime discriminator for
    Ricci IC (Spearman ρ=+0.352, p=0.008 across 56 rolling windows;
    low-vol quartile IC median = +0.027 vs high-vol quartile IC
    median = +0.137).

    High score ⇒ there is flow / activity ⇒ OFI drives observable
    price changes ⇒ cross-sectional Ricci has structural content
    to score. Low score ⇒ the book is inert ⇒ OFI → 0 → Ricci → noise.

    Implementation: per-row rolling std of 1-sec log-returns averaged
    across symbols. No baseline subtraction (we want absolute activity,
    not anomaly vs expected).
    """
    if window_rows < _MIN_WINDOW_ROWS:
        raise ValueError(f"window_rows must be >= {_MIN_WINDOW_ROWS}, got {window_rows}")
    if features.n_symbols < 1:
        raise ValueError(f"need >= 1 symbol, got {features.n_symbols}")

    log_mid = np.log(features.mid)
    ret = np.vstack([np.zeros((1, features.n_symbols)), np.diff(log_mid, axis=0)])
    n = ret.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    for t in range(window_rows, n):
        block = ret[t - window_rows : t]
        if not np.all(np.isfinite(block)):
            continue
        out[t] = float(block.std(axis=0).mean())
    return out


def regime_mask_from_score(
    score: NDArray[np.float64],
    *,
    threshold: float,
) -> NDArray[np.bool_]:
    """Boolean mask: True where score >= threshold and finite, False otherwise."""
    mask = np.isfinite(score) & (score >= threshold)
    return mask.astype(bool)


def regime_mask_from_quantile(
    score: NDArray[np.float64],
    *,
    quantile: float,
) -> NDArray[np.bool_]:
    """Boolean mask: True where score >= empirical quantile of the finite scores.

    quantile must lie in (0, 1); e.g. 0.5 keeps the top half, 0.25 keeps
    the top 75%. Finite-threshold-free alternative when absolute score
    scale depends on substrate.
    """
    if not 0.0 < quantile < 1.0:
        raise ValueError(f"quantile must lie in (0, 1), got {quantile}")
    finite = score[np.isfinite(score)]
    if finite.size == 0:
        return np.zeros_like(score, dtype=bool)
    threshold = float(np.quantile(finite, quantile))
    return regime_mask_from_score(score, threshold=threshold)
