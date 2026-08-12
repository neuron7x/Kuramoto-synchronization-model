# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for the Rosenstein maximal-Lyapunov estimator.

Pins two defects in ``geosync/estimators/lyapunov_estimator.py``:

1. Divergence values were sliced with ``avg_div[:fit_len]`` (a contiguous
   prefix) while ``fit_len`` counted VALID steps only. Zero-filled invalid
   steps (from ``np.zeros_like``) are finite, pass ``np.isfinite`` and drag the
   polyfit slope toward a spurious 0.0 anchor. Fixed by selecting values (and
   the matching time axis) via ``valid_mask``.
2. No scaling-region acceptance gate existed, so a non-scaling (noise) series
   returned a silent, unreliable slope with ``is_valid=True``. INV-LE3 requires
   the log-divergence linear fit to reach R² ≥ 0.80 or be demoted to
   ``is_valid=False`` and fail closed to λ = 0.0.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geosync.estimators.lyapunov_estimator import RosensteinLyapunov


def _logistic_map(n: int, r: float = 4.0, x0: float = 0.4) -> np.ndarray:
    """Deterministic chaotic series; theoretical MLE = ln 2 ≈ 0.693 at r=4."""
    x = np.empty(n, dtype=np.float64)
    x[0] = x0
    for i in range(1, n):
        x[i] = r * x[i - 1] * (1.0 - x[i - 1])
    return x


def test_chaotic_logistic_map_recovers_positive_lambda() -> None:
    """INV-LE2/LE3: a clean chaotic signal has a linear scaling region, so the
    fit passes the R² gate, is_valid stays True and λ ≈ ln 2 > 0.

    Guards against the R² gate over-demoting legitimate chaos.
    """
    series = _logistic_map(2000)
    est = RosensteinLyapunov().compute(series)

    assert est.is_valid is True
    assert est.is_chaotic is True
    assert est.lambda_max > 0.0
    # Rosenstein on the logistic map recovers λ near the analytic ln 2.
    assert est.lambda_max == pytest.approx(math.log(2.0), abs=0.15)


def test_white_noise_is_demoted_by_scaling_gate() -> None:
    """INV-LE3 regression: white noise has no linear scaling region.

    Under the old behavior the polyfit returned a spurious non-zero slope with
    is_valid=True (measured λ≈0.151). The R² acceptance gate must now demote it
    to a non-scaling verdict: is_valid=False, λ fails closed to 0.0.
    """
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(600)
    est = RosensteinLyapunov().compute(noise)

    assert est.is_valid is False
    assert est.is_chaotic is False
    assert est.lambda_max == 0.0
    assert est.doubling_time == math.inf


def test_scaling_gate_never_fabricates_slope_when_demoted() -> None:
    """When demoted, every derived metric is the fail-closed sentinel, never a
    partial artifact of the rejected fit (INV-LE3: demote, never fabricate)."""
    rng = np.random.default_rng(11)
    noise = rng.standard_normal(500)
    est = RosensteinLyapunov().compute(noise)

    if not est.is_valid:
        assert est.lambda_max == 0.0
        assert est.divergence_rate == 0.0
        assert est.doubling_time == math.inf
