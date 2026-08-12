# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Romano-Wolf stepwise multiple testing (FWER control + power)."""

from __future__ import annotations

import numpy as np
import pytest

from research.robustness.romano_wolf import RomanoWolfResult, romano_wolf_stepm


def test_strong_edges_are_rejected_noise_is_not() -> None:
    """Power + selectivity: clear edges flagged, noise columns left alone."""
    rng = np.random.default_rng(1)
    edges = rng.normal(0.45, 1.0, (500, 3))  # ~10σ mean over T=500
    noise = rng.normal(0.0, 1.0, (500, 17))
    perf = np.hstack([edges, noise])

    result = romano_wolf_stepm(perf, alpha=0.05, n_bootstrap=1500, seed=0)

    assert result.rejected[:3].all(), "all three genuine edges must be rejected (power)"
    # FWER control is family-wise, not per-comparison: at alpha=0.05 a single
    # false discovery across the 17 nulls is within contract (P(≥1) ≈ alpha),
    # so the honest selectivity bound is "almost none", not "exactly none".
    assert result.rejected[3:].sum() <= 1, "noise false-discoveries must be ≤ 1 at alpha=0.05"


def test_fwer_controlled_far_below_naive() -> None:
    """On pure noise the family-wise false-discovery rate stays near alpha,
    where a naive per-strategy test at the same level would be ~1 − (1−α)^K."""
    alpha = 0.10
    k = 20
    trials = 120
    any_rejection = 0
    for i in range(trials):
        noise = np.random.default_rng(1000 + i).normal(0.0, 1.0, (300, k))
        result = romano_wolf_stepm(noise, alpha=alpha, n_bootstrap=400, seed=i)
        if result.rejected.any():
            any_rejection += 1
    empirical_fwer = any_rejection / trials
    naive_fwer = 1.0 - (1.0 - alpha) ** k  # ~0.88

    assert empirical_fwer <= 0.20, (
        f"stepM FWER={empirical_fwer:.3f} should stay near alpha={alpha}; "
        f"naive per-strategy bound would be {naive_fwer:.3f}"
    )
    assert empirical_fwer < naive_fwer / 2.0, "stepM must dominate the naive multiplicity bound"


def test_determinism_same_seed() -> None:
    rng = np.random.default_rng(3)
    perf = rng.normal(0.05, 1.0, (300, 10))
    a = romano_wolf_stepm(perf, n_bootstrap=300, seed=7)
    b = romano_wolf_stepm(perf, n_bootstrap=300, seed=7)
    assert np.array_equal(a.rejected, b.rejected)
    assert a.critical_values == b.critical_values


def test_result_shape_and_metadata() -> None:
    rng = np.random.default_rng(0)
    perf = rng.normal(0.0, 1.0, (200, 6))
    result = romano_wolf_stepm(perf, alpha=0.05, n_bootstrap=200, seed=0)
    assert isinstance(result, RomanoWolfResult)
    assert result.rejected.shape == (6,)
    assert result.statistics.shape == (6,)
    assert result.n_strategies == 6
    assert result.n_periods == 200
    assert 0 <= result.n_rejected <= 6


def test_zero_variance_strategy_never_rejected() -> None:
    """A constant (zero-SD) column carries no signal and must not be flagged."""
    rng = np.random.default_rng(0)
    perf = np.hstack([np.full((300, 1), 5.0), rng.normal(0.0, 1.0, (300, 4))])
    result = romano_wolf_stepm(perf, alpha=0.10, n_bootstrap=300, seed=0)
    assert not bool(result.rejected[0]), "zero-variance column must never be rejected"
    assert np.isneginf(result.statistics[0]) or result.statistics[0] == 0.0


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"alpha": 0.0}, "alpha"),
        ({"alpha": 1.0}, "alpha"),
        ({"n_bootstrap": 0}, "n_bootstrap"),
        ({"block_size": 0}, "block_size"),
        ({"block_size": 99999}, "block_size"),
    ],
)
def test_invalid_parameters_fail_closed(kwargs: dict[str, float], match: str) -> None:
    perf = np.random.default_rng(0).normal(0.0, 1.0, (100, 4))
    with pytest.raises(ValueError, match=match):
        romano_wolf_stepm(perf, **kwargs)


@pytest.mark.parametrize(
    "bad,match",
    [
        (np.zeros(10), "2-D"),
        (np.zeros((1, 4)), "2 periods"),
        (np.full((10, 3), np.inf), "non-finite"),
    ],
)
def test_malformed_performance_fails_closed(bad: np.ndarray, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        romano_wolf_stepm(bad)
