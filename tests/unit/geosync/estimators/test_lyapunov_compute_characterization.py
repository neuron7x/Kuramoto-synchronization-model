# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Characterization + numerical-equivalence pins for ``RosensteinLyapunov.compute``.

ARC-001 remediation: ``compute`` was refactored (helper extraction) to drop
below the code-hygiene complexity/LOC thresholds. This suite freezes the EXACT
pre-refactor output of ``compute`` across chaotic / stable / noise / degenerate
inputs so that any behavioural drift — including a single-ULP numeric change —
fails closed. Golden values captured from the pre-refactor implementation.

Physics: INV-LE1 (finite MLE for bounded finite input), INV-LE2 (sign of MLE),
INV-LE3 (R² ≥ 0.80 scaling gate; below it demote to is_valid=False, fail closed
to λ = 0.0, never fabricate a slope).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geosync.estimators.lyapunov_estimator import LyapunovEstimate, RosensteinLyapunov


def _logistic_map(n: int, r: float = 4.0, x0: float = 0.4) -> np.ndarray:
    x = np.empty(n, dtype=np.float64)
    x[0] = x0
    for i in range(1, n):
        x[i] = r * x[i - 1] * (1.0 - x[i - 1])
    return x


def _ar1(n: int, phi: float = 0.5, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    e = rng.standard_normal(n)
    y = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        y[i] = phi * y[i - 1] + e[i]
    return y


def _cases() -> dict[str, np.ndarray]:
    return {
        "logistic2000": _logistic_map(2000),
        "logistic500": _logistic_map(500),
        "noise600": np.random.default_rng(7).standard_normal(600),
        "noise500": np.random.default_rng(11).standard_normal(500),
        "sine": np.sin(np.linspace(0.0, 80.0 * np.pi, 1500)),
        "short50": np.arange(50.0),
        "const": np.full(400, 3.14),
        "nan": np.concatenate([np.arange(300.0), [np.nan]]),
        "2d": np.ones((10, 10)),
        "ar1": _ar1(800),
    }


# Golden outputs frozen from the pre-refactor implementation. (lambda_max,
# is_chaotic, doubling_time, divergence_rate, is_valid)
_GOLDEN: dict[str, tuple[float, bool, float, float, bool]] = {
    "logistic2000": (0.688531, True, 1.01, 0.6885, True),
    "logistic500": (0.63012, True, 1.1, 0.6301, True),
    "noise600": (0.0, False, math.inf, 0.0, False),
    "noise500": (0.0, False, math.inf, 0.0, False),
    "sine": (0.0, False, math.inf, 0.0, False),
    "short50": (0.0, False, math.inf, 0.0, False),
    "const": (0.0, False, math.inf, 0.0, False),
    "nan": (0.0, False, math.inf, 0.0, False),
    "2d": (0.0, False, math.inf, 0.0, False),
    "ar1": (0.0, False, math.inf, 0.0, False),
}


@pytest.mark.parametrize("name", sorted(_GOLDEN))
def test_compute_matches_frozen_golden_exactly(name: str) -> None:
    """Numerical-equivalence pin: every field bit-for-bit equal to the golden."""
    series = _cases()[name]
    est = RosensteinLyapunov().compute(np.asarray(series, dtype=np.float64))
    exp = _GOLDEN[name]

    assert isinstance(est, LyapunovEstimate)
    assert est.lambda_max == exp[0], name
    assert est.is_chaotic == exp[1], name
    assert est.doubling_time == exp[2], name
    assert est.divergence_rate == exp[3], name
    assert est.is_valid == exp[4], name


def test_invalid_sentinel_is_uniform_across_all_reject_paths() -> None:
    """INV-LE3: every fail-closed path returns the identical sentinel tuple."""
    sentinel = (0.0, False, math.inf, 0.0, False)
    for name in ("noise600", "sine", "short50", "const", "nan", "2d", "ar1"):
        est = RosensteinLyapunov().compute(np.asarray(_cases()[name], dtype=np.float64))
        assert (
            est.lambda_max,
            est.is_chaotic,
            est.doubling_time,
            est.divergence_rate,
            est.is_valid,
        ) == sentinel, name


def test_compute_is_deterministic_and_idempotent() -> None:
    """Same input -> identical estimate across repeated calls (INV-LE1 finiteness)."""
    series = _logistic_map(2000)
    est_a = RosensteinLyapunov().compute(series)
    est_b = RosensteinLyapunov().compute(series)
    assert est_a == est_b
    assert math.isfinite(est_a.lambda_max)
