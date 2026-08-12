# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for White's Reality Check data-snooping correction."""

from __future__ import annotations

import numpy as np
import pytest

from research.robustness.white_reality_check import (
    WhiteRealityCheckResult,
    white_reality_check,
)


def _strong_edge_among_noise(seed: int = 42, t: int = 500, k_noise: int = 20) -> np.ndarray:
    rng = np.random.default_rng(seed)
    edge = rng.normal(0.20, 1.0, (t, 1))  # ~4.5σ mean over T=500
    noise = rng.normal(0.0, 1.0, (t, k_noise))
    return np.hstack([edge, noise])


def test_strong_edge_is_detected() -> None:
    """A genuine edge among noise rejects H0 (small p)."""
    result = white_reality_check(_strong_edge_among_noise(), n_bootstrap=2000, seed=0)
    assert result.p_value < 0.05, f"strong edge should reject H0, got p={result.p_value}"
    assert result.best_strategy == 0


def test_pure_noise_is_not_significant() -> None:
    """Many pure-noise strategies must NOT pass — the snooping guard holds."""
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 1.0, (500, 50))
    result = white_reality_check(noise, n_bootstrap=2000, seed=0)
    assert result.p_value > 0.10, f"noise must not be significant, got p={result.p_value}"


def test_reality_check_beats_naive_max_on_snooped_noise() -> None:
    """The correction's reason for existing: the naive best-of-K t-test
    manufactures significance on pure noise; White's RC does not."""
    rng = np.random.default_rng(11)
    noise = rng.normal(0.0, 1.0, (500, 100))
    rc = white_reality_check(noise, n_bootstrap=2000, seed=0)

    # Naive one-sided t-test on the single best-looking strategy.
    best = int(noise.mean(axis=0).argmax())
    series = noise[:, best]
    t_stat = np.sqrt(series.size) * series.mean() / series.std(ddof=1)
    from math import erfc, sqrt

    naive_p = 0.5 * erfc(t_stat / sqrt(2.0))

    assert naive_p < 0.05, "sanity: naive max-test should look (falsely) significant"
    assert rc.p_value > naive_p, "Reality Check must be more conservative than naive max-test"


def test_determinism_same_seed() -> None:
    perf = _strong_edge_among_noise()
    a = white_reality_check(perf, n_bootstrap=500, seed=11)
    b = white_reality_check(perf, n_bootstrap=500, seed=11)
    assert a.p_value == b.p_value
    assert a.statistic == b.statistic


def test_pvalue_bounds_and_metadata() -> None:
    result = white_reality_check(_strong_edge_among_noise(), n_bootstrap=300, seed=3)
    assert 0.0 < result.p_value <= 1.0
    assert isinstance(result, WhiteRealityCheckResult)
    assert result.n_periods == 500
    assert result.n_strategies == 21
    assert result.n_bootstrap == 300


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"n_bootstrap": 0}, "n_bootstrap"),
        ({"block_size": 0}, "block_size"),
        ({"block_size": 10_000}, "block_size"),
    ],
)
def test_invalid_parameters_fail_closed(kwargs: dict[str, int], match: str) -> None:
    perf = np.random.default_rng(0).normal(0.0, 1.0, (100, 5))
    with pytest.raises(ValueError, match=match):
        white_reality_check(perf, **kwargs)


@pytest.mark.parametrize(
    "bad,match",
    [
        (np.zeros(10), "2-D"),
        (np.zeros((1, 5)), "2 time periods"),
        (np.full((10, 3), np.nan), "non-finite"),
    ],
)
def test_malformed_performance_fails_closed(bad: np.ndarray, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        white_reality_check(bad)
