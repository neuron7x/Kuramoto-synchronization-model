"""Objective functions for the optimize CLI command."""

from __future__ import annotations

import numpy as np


def sharpe_ratio(returns: np.ndarray, risk_free: float = 0.0) -> float:
    """Compute a basic Sharpe ratio for a vector of returns."""

    excess = returns - risk_free
    mean = float(excess.mean())
    std = float(excess.std(ddof=1)) if excess.size > 1 else 0.0
    if std == 0.0:
        return 0.0
    return mean / std
