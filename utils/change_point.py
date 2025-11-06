"""Change point detection utilities used by the FHMC controller."""
from __future__ import annotations

import numpy as np


def cusum_score(series, *, drift: float = 0.0, threshold: float = 5.0) -> float:
    values = np.asarray(series, dtype=float)
    if values.size == 0:
        return 0.0
    s_pos = 0.0
    s_neg = 0.0
    alarms = 0
    mean = float(values.mean())
    std = float(values.std() + 1e-8)
    for value in values:
        z = (value - mean) / std
        s_pos = max(0.0, s_pos + z - drift)
        s_neg = min(0.0, s_neg + z + drift)
        if s_pos > threshold or s_neg < -threshold:
            alarms += 1
            s_pos = 0.0
            s_neg = 0.0
    return float(alarms)


def vol_shock(returns, *, window: int = 60) -> float:
    returns = np.asarray(returns, dtype=float)
    if returns.size < window:
        return 0.0
    recent = np.std(returns[-window:])
    baseline = np.std(returns[:window])
    return float((recent - baseline) / (baseline + 1e-8))
