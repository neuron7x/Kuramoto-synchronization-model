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
        either level aggregates or individual order sizes.
    """

    bid_total = float(np.sum(np.clip(bid_sizes, a_min=0.0, a_max=None)))
    ask_total = float(np.sum(np.clip(ask_sizes, a_min=0.0, a_max=None)))
    denom = bid_total + ask_total
    if denom <= 0.0:
        return 0.0
    return (bid_total - ask_total) / denom


def kyles_lambda(returns: Sequence[float], signed_volume: Sequence[float]) -> float:
    """Estimate Kyle's lambda using a least squares regression."""

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
    """

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
        k_lambda = kyles_lambda(group[returns_col].to_numpy(), group[signed_volume_col].to_numpy())
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
