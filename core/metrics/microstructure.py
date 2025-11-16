# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Microstructure metrics used by research and reporting pipelines."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
import pandas as pd


def queue_imbalance(bid_sizes: Sequence[float], ask_sizes: Sequence[float]) -> float:
    """Compute the queue imbalance metric.

    Parameters
    ----------
    bid_sizes, ask_sizes:
        Sequences of resting volume at the bid and ask.  The function accepts
        either level aggregates or individual order sizes. Must be non-empty
        sequences of finite numeric values.

    Returns
    -------
    float
        Queue imbalance in range [-1, 1]. Positive values indicate more bid
        volume, negative indicates more ask volume. Returns 0.0 if total
        volume is zero or inputs are invalid.

    Raises
    ------
    ValueError
        If bid_sizes or ask_sizes is empty or contains non-finite values.
    """
    if len(bid_sizes) == 0:
        raise ValueError("bid_sizes must not be empty")
    if len(ask_sizes) == 0:
        raise ValueError("ask_sizes must not be empty")

    bid_arr = np.asarray(bid_sizes, dtype=float)
    ask_arr = np.asarray(ask_sizes, dtype=float)

    if not np.all(np.isfinite(bid_arr)):
        raise ValueError("bid_sizes must contain only finite values")
    if not np.all(np.isfinite(ask_arr)):
        raise ValueError("ask_sizes must contain only finite values")

    bid_total = float(np.sum(np.clip(bid_arr, a_min=0.0, a_max=None)))
    ask_total = float(np.sum(np.clip(ask_arr, a_min=0.0, a_max=None)))
    denom = bid_total + ask_total
    if denom <= 0.0:
        return 0.0
    return (bid_total - ask_total) / denom


def kyles_lambda(returns: Sequence[float], signed_volume: Sequence[float]) -> float:
    """Estimate Kyle's lambda using a least squares regression.

    Kyle's lambda measures price impact per unit of signed volume, representing
    the market's price response to informed trading.

    Parameters
    ----------
    returns : Sequence[float]
        Time series of price returns. Must have the same length as signed_volume.
    signed_volume : Sequence[float]
        Time series of signed (directional) trading volume.
        Positive for buyer-initiated, negative for seller-initiated.

    Returns
    -------
    float
        Estimated Kyle's lambda coefficient. Returns 0.0 if the regression
        cannot be computed due to insufficient data or zero volume variance.

    Raises
    ------
    ValueError
        If input sequences have different lengths or are empty.

    Notes
    -----
    The metric regresses returns on signed volume to estimate price impact.
    Higher values indicate greater price impact per unit of volume, suggesting
    lower market liquidity or presence of informed traders.

    References
    ----------
    Kyle, A. S. (1985). "Continuous Auctions and Insider Trading."
    Econometrica, 53(6), 1315-1335.
    """
    if len(returns) == 0:
        raise ValueError("returns must not be empty")
    if len(signed_volume) == 0:
        raise ValueError("signed_volume must not be empty")
    if len(returns) != len(signed_volume):
        raise ValueError("returns and signed_volume must have the same length")

    r = np.asarray(list(returns), dtype=float)
    q = np.asarray(list(signed_volume), dtype=float)
    mask = np.isfinite(r) & np.isfinite(q)
    r = r[mask]
    q = q[mask]
    if r.size == 0 or q.size == 0:
        return 0.0
    if np.allclose(q, 0.0):
        return 0.0
    q = q - np.mean(q)
    r = r - np.mean(r)
    denom = np.dot(q, q)
    if denom <= 0.0:
        return 0.0
    return float(np.dot(q, r) / denom)


def hasbrouck_information_impulse(
    returns: Sequence[float], signed_volume: Sequence[float]
) -> float:
    """Estimate Hasbrouck's information content using signed square-root volume.

    The statistic is effectively the correlation between centered returns and the
    signed square-root of volume.  Normalizing by the Euclidean norms of both
    series makes the measure invariant to affine transformations (shifts and
    rescaling) of the input data, which is desirable for downstream property
    tests that compare relative information content rather than absolute
    magnitudes.

    Parameters
    ----------
    returns : Sequence[float]
        Time series of price returns. Must have the same length as signed_volume.
    signed_volume : Sequence[float]
        Time series of signed (directional) trading volume.

    Returns
    -------
    float
        Information impulse response coefficient in range [-1, 1].
        Returns 0.0 if computation cannot be performed due to zero variance
        or insufficient data.

    Raises
    ------
    ValueError
        If input sequences have different lengths or are empty.

    Notes
    -----
    This metric quantifies how much price changes contain information about
    order flow. Higher absolute values suggest greater price informativeness.

    References
    ----------
    Hasbrouck, J. (1991). "Measuring the Information Content of Stock Trades."
    Journal of Finance, 46(1), 179-207.
    """
    if len(returns) == 0:
        raise ValueError("returns must not be empty")
    if len(signed_volume) == 0:
        raise ValueError("signed_volume must not be empty")
    if len(returns) != len(signed_volume):
        raise ValueError("returns and signed_volume must have the same length")

    r = np.asarray(list(returns), dtype=float)
    q = np.asarray(list(signed_volume), dtype=float)
    mask = np.isfinite(r) & np.isfinite(q)
    r = r[mask]
    q = q[mask]
    if r.size == 0 or q.size == 0:
        return 0.0
    q = q - np.mean(q)
    transformed = np.sign(q) * np.sqrt(np.abs(q))
    transformed = transformed - np.mean(transformed)
    r = r - np.mean(r)
    norm_transformed = float(np.linalg.norm(transformed))
    norm_returns = float(np.linalg.norm(r))
    if norm_transformed == 0.0 or norm_returns == 0.0:
        return 0.0
    return float(np.dot(transformed, r) / (norm_transformed * norm_returns))


@dataclass(slots=True)
class MicrostructureReport:
    """Container for per-symbol microstructure metrics."""

    symbol: str
    samples: int
    avg_queue_imbalance: float
    kyles_lambda: float
    hasbrouck_impulse: float


def build_symbol_microstructure_report(
    frame: pd.DataFrame,
    *,
    symbol_col: str = "symbol",
    bid_col: str = "bid_volume",
    ask_col: str = "ask_volume",
    returns_col: str = "returns",
    signed_volume_col: str = "signed_volume",
) -> pd.DataFrame:
    """Generate a per-symbol report of the microstructure metrics."""

    required = {symbol_col, bid_col, ask_col, returns_col, signed_volume_col}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"Missing columns for microstructure report: {sorted(missing)}")

    grouped = frame.groupby(symbol_col, sort=True)
    rows = []
    for symbol, group in grouped:
        qi = queue_imbalance(group[bid_col].to_numpy(), group[ask_col].to_numpy())
        k_lambda = kyles_lambda(
            group[returns_col].to_numpy(), group[signed_volume_col].to_numpy()
        )
        impulse = hasbrouck_information_impulse(
            group[returns_col].to_numpy(), group[signed_volume_col].to_numpy()
        )
        rows.append(
            MicrostructureReport(
                symbol=str(symbol),
                samples=int(len(group)),
                avg_queue_imbalance=float(qi),
                kyles_lambda=float(k_lambda),
                hasbrouck_impulse=float(impulse),
            )
        )

    return pd.DataFrame([asdict(row) for row in rows])


__all__ = [
    "MicrostructureReport",
    "build_symbol_microstructure_report",
    "hasbrouck_information_impulse",
    "kyles_lambda",
    "queue_imbalance",
]
