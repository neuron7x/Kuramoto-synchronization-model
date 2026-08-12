"""Tests for robustness module: bootstrap CI, DSR, ADF, MI."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.robustness import (
    ADFReport,
    BootstrapICReport,
    DeflatedSharpeReport,
    MutualInfoReport,
    adf_stationarity,
    block_bootstrap_ic,
    deflated_sharpe,
    mutual_information,
)

_SEED = 42


# ---------------------------------------------------------------------------
# R1 · block bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_strong_correlation_ci_excludes_zero() -> None:
    rng = np.random.default_rng(_SEED)
    n = 3000
    x = rng.normal(0.0, 1.0, size=n)
    y = x + 0.1 * rng.normal(0.0, 1.0, size=n)
    r = block_bootstrap_ic(x, y, block_size=50, n_bootstraps=300, seed=_SEED)
    assert isinstance(r, BootstrapICReport)
    assert r.ic_point > 0.9
    assert r.ci_lo_95 > 0.5
    assert r.significant_at_95 is True


def test_bootstrap_null_ci_includes_zero() -> None:
    rng = np.random.default_rng(_SEED)
    n = 3000
    x = rng.normal(0.0, 1.0, size=n)
    y = rng.normal(0.0, 1.0, size=n)
    r = block_bootstrap_ic(x, y, block_size=50, n_bootstraps=300, seed=_SEED)
    assert r.ci_lo_95 < 0.0 < r.ci_hi_95
    assert r.significant_at_95 is False


def test_bootstrap_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        block_bootstrap_ic(
            np.arange(100, dtype=np.float64),
            np.arange(101, dtype=np.float64),
        )


def test_bootstrap_rejects_bad_block_size() -> None:
    x = np.zeros(100, dtype=np.float64)
    with pytest.raises(ValueError):
        block_bootstrap_ic(x, x, block_size=0)


def test_bootstrap_rejects_bad_n_bootstraps() -> None:
    x = np.zeros(100, dtype=np.float64)
    with pytest.raises(ValueError):
        block_bootstrap_ic(x, x, n_bootstraps=1)


def test_bootstrap_deterministic_under_fixed_seed() -> None:
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=1000)
    y = rng.normal(0.0, 1.0, size=1000)
    a = block_bootstrap_ic(x, y, block_size=30, n_bootstraps=100, seed=_SEED)
    b = block_bootstrap_ic(x, y, block_size=30, n_bootstraps=100, seed=_SEED)
    assert a.ci_lo_95 == b.ci_lo_95
    assert a.ci_hi_95 == b.ci_hi_95


# ---------------------------------------------------------------------------
# R2 · deflated Sharpe
# ---------------------------------------------------------------------------


def test_deflated_sharpe_minimum_trials_light_deflation() -> None:
    """With n_trials=2, Φ⁻¹(0.5)=0 is the primary term; deflation is mild."""
    r = deflated_sharpe(sharpe_observed=2.0, n_trials=2, n_observations=100)
    assert isinstance(r, DeflatedSharpeReport)
    assert np.isfinite(r.sharpe_expected_max)
    assert np.isfinite(r.deflated_sharpe)
    assert r.deflated_sharpe > 0.0
    assert r.probability_sharpe_is_real > 0.5


def test_deflated_sharpe_many_trials_deflates_prob() -> None:
    """Many trials → expected_max grows → probability_real falls."""
    # Use marginal Sharpe so that n_trials actually discriminates
    # (a huge t-statistic would saturate Pr(real) at 1.0 for any trials).
    r_few = deflated_sharpe(sharpe_observed=0.05, n_trials=2, n_observations=400)
    r_many = deflated_sharpe(sharpe_observed=0.05, n_trials=10_000, n_observations=400)
    assert r_many.sharpe_expected_max > r_few.sharpe_expected_max
    assert r_many.probability_sharpe_is_real < r_few.probability_sharpe_is_real


def test_deflated_sharpe_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        deflated_sharpe(sharpe_observed=1.0, n_trials=0, n_observations=100)
    with pytest.raises(ValueError):
        deflated_sharpe(sharpe_observed=1.0, n_trials=5, n_observations=1)


def test_deflated_sharpe_high_observed_yields_high_prob() -> None:
    """If observed Sharpe is high and n_trials small → Pr(real) → 1."""
    r = deflated_sharpe(sharpe_observed=3.0, n_trials=2, n_observations=1000)
    assert r.probability_sharpe_is_real > 0.99


# ---------------------------------------------------------------------------
# R3 · ADF
# ---------------------------------------------------------------------------


def test_adf_stationary_white_noise() -> None:
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=500)
    r = adf_stationarity(x)
    assert isinstance(r, ADFReport)
    assert r.verdict in {"STATIONARY", "INCONCLUSIVE"}
    assert r.pvalue < 0.10


def test_adf_nonstationary_random_walk() -> None:
    rng = np.random.default_rng(_SEED)
    noise = rng.normal(0.0, 1.0, size=500)
    walk = np.cumsum(noise)
    r = adf_stationarity(walk)
    assert r.verdict in {"UNIT_ROOT", "INCONCLUSIVE"}
    assert r.pvalue > 0.01


def test_adf_too_short_returns_inconclusive() -> None:
    r = adf_stationarity(np.array([1.0, 2.0, 3.0], dtype=np.float64))
    assert r.verdict == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# R4 · Mutual information
# ---------------------------------------------------------------------------


def test_mutual_information_strong_dependence_positive() -> None:
    rng = np.random.default_rng(_SEED)
    n = 5000
    x = rng.normal(0.0, 1.0, size=n)
    y = x + 0.1 * rng.normal(0.0, 1.0, size=n)
    r = mutual_information(x, y, n_bins=32)
    assert isinstance(r, MutualInfoReport)
    assert r.mutual_information_nats > 0.5
    assert r.mutual_information_bits > 0.7


def test_mutual_information_independence_near_zero() -> None:
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=5000)
    y = rng.normal(0.0, 1.0, size=5000)
    r = mutual_information(x, y, n_bins=32)
    # Histogram estimator has positive bias ~ k²/n; for n=5000, k=32 it's ~0.2 nats
    assert r.mutual_information_nats < 0.3


def test_mutual_information_too_few_samples_returns_nan() -> None:
    r = mutual_information(np.arange(10.0), np.arange(10.0))
    assert not np.isfinite(r.mutual_information_nats)
    assert not np.isfinite(r.mutual_information_bits)


def test_mutual_information_nonlinear_captured_when_spearman_is_zero() -> None:
    """y = x² — Spearman sees 0 but MI should be positive."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=5000)
    y = x * x
    r = mutual_information(x, y, n_bins=32)
    assert r.mutual_information_nats > 0.5
    # Spearman on a symmetric non-monotone relationship is low
    assert abs(r.correlation_spearman) < 0.1
