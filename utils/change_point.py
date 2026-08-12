# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Change point detection utilities used by the FHMC controller.

These helpers normalise incoming series and compute lightweight signals for
runtime anomaly detection.  They intentionally avoid heavier dependencies so
they can run inside tight control loops.
"""

from __future__ import annotations

import numpy as np


def cusum_score(series, *, drift: float = 0.0, threshold: float = 5.0) -> float:
    """Return the number of CUSUM alarms triggered in ``series``.

    The input sequence is converted to a NumPy array and normalised using the
    global mean and standard deviation.  Positive and negative accumulators are
    updated for each value and reset whenever the configured ``threshold`` is
    exceeded, recording an alarm.  An empty series returns ``0.0`` to avoid
    noisy downstream metrics.
    """
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
    """Measure how much recent volatility deviates from a baseline window.

    The metric compares the standard deviation of the most recent ``window``
    samples to the initial ``window`` samples.  A positive value signals a
    spike in volatility, while a negative value indicates compression relative
    to the baseline period.  If the series is shorter than ``window``, the
    function returns ``0.0`` to keep callers tolerant of cold-start regimes.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.size < window:
        return 0.0
    recent = np.std(returns[-window:])
    baseline = np.std(returns[:window])
    return float((recent - baseline) / (baseline + 1e-8))
