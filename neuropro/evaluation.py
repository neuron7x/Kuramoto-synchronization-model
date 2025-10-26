"""Evaluation utilities."""

from __future__ import annotations

import numpy as np


def sharpe(r):
    r = np.asarray(r)
    if len(r) < 2:
        return 0.0
    return (r.mean() / (r.std(ddof=1) + 1e-12)) * np.sqrt(252)


def deflated_sharpe(sr: float, n: int, trials: int = 50) -> float:
    if n <= 2:
        return 0.0
    emax = np.sqrt(2 * np.log(trials)) - (
        np.log(np.log(trials)) + np.log(4 * np.pi)
    ) / (2 * np.sqrt(2 * np.log(trials)))
    return (abs(sr) - emax) * np.sqrt((n - 1) / (n - 2))


def cvar(returns, alpha: float = 0.95) -> float:
    r = np.asarray(returns)
    if len(r) == 0:
        return 0.0
    q = np.quantile(r, 1 - alpha)
    tail = r[r <= q]
    return float(tail.mean()) if len(tail) > 0 else 0.0


def max_drawdown(equity) -> float:
    ec = np.asarray(equity) if not isinstance(equity, np.ndarray) else equity
    if len(ec) == 0:
        return 0.0
    peaks = np.maximum.accumulate(ec)
    dd = (peaks - ec) / (peaks + 1e-12)
    return float(np.max(dd))
