"""Tests for Detrended Fluctuation Analysis Hurst estimator."""

from __future__ import annotations

import numpy as np

from research.microstructure.hurst import (
    HurstReport,
    dfa_hurst,
)

_SEED = 42


def test_hurst_white_noise_near_half() -> None:
    """White noise: H ≈ 0.5 ± tolerance (DFA-1 on stationary, memoryless input)."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=8192).astype(np.float64)
    r = dfa_hurst(x)
    assert isinstance(r, HurstReport)
    assert np.isfinite(r.hurst_exponent)
    assert abs(r.hurst_exponent - 0.5) < 0.08
    assert r.verdict == "WHITE_NOISE"
    assert r.r_squared > 0.95


def test_hurst_random_walk_near_three_halves() -> None:
    """Random walk = integrated white noise → H ≈ 1.5 (Brownian)."""
    rng = np.random.default_rng(_SEED)
    walk = np.cumsum(rng.normal(0.0, 1.0, size=8192)).astype(np.float64)
    r = dfa_hurst(walk)
    assert np.isfinite(r.hurst_exponent)
    assert abs(r.hurst_exponent - 1.5) < 0.12
    assert r.verdict == "STRONG_PERSISTENT"
    assert r.r_squared > 0.95


def test_hurst_mean_reverting_anti_persistent() -> None:
    """First-difference of white noise → anti-persistent, H ≈ 0."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=8192)
    y = np.diff(x).astype(np.float64)
    r = dfa_hurst(y)
    assert np.isfinite(r.hurst_exponent)
    assert r.hurst_exponent < 0.4
    assert r.verdict == "MEAN_REVERTING"


def test_hurst_too_short_returns_inconclusive() -> None:
    """Signal shorter than 4 · min_scale → INCONCLUSIVE with NaN H."""
    r = dfa_hurst(np.arange(32, dtype=np.float64))
    assert r.verdict == "INCONCLUSIVE"
    assert not np.isfinite(r.hurst_exponent)
    assert r.scales == ()
    assert r.fluctuations == ()


def test_hurst_schema_complete_on_happy_path() -> None:
    """On valid input all schema fields populated; scales strictly ascending."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=4096).astype(np.float64)
    r = dfa_hurst(x)
    assert isinstance(r.hurst_exponent, float)
    assert isinstance(r.r_squared, float)
    assert isinstance(r.verdict, str)
    assert len(r.scales) >= 4
    assert len(r.fluctuations) == len(r.scales)
    assert list(r.scales) == sorted(r.scales)
    assert r.n_samples_used == 4096


def test_hurst_deterministic_under_fixed_seed() -> None:
    """Same signal → identical H, R², scales, fluctuations."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=4096).astype(np.float64)
    a = dfa_hurst(x)
    b = dfa_hurst(x)
    assert a.hurst_exponent == b.hurst_exponent
    assert a.r_squared == b.r_squared
    assert a.scales == b.scales
    assert a.fluctuations == b.fluctuations


def test_hurst_verdict_taxonomy_covers_regimes() -> None:
    """Verdict label matches H band: mean-rev / white / persistent / strong."""
    rng = np.random.default_rng(_SEED)

    # Anti-persistent: first-difference of white noise (MA(1), θ=-1)
    y_anti = np.diff(rng.normal(0.0, 1.0, size=8192)).astype(np.float64)
    assert dfa_hurst(y_anti).verdict == "MEAN_REVERTING"

    # White noise
    y_white = rng.normal(0.0, 1.0, size=8192).astype(np.float64)
    assert dfa_hurst(y_white).verdict == "WHITE_NOISE"

    # Brownian motion → H ≈ 1.5 → STRONG_PERSISTENT
    y_brownian = np.cumsum(rng.normal(0.0, 1.0, size=8192)).astype(np.float64)
    assert dfa_hurst(y_brownian).verdict == "STRONG_PERSISTENT"


def test_hurst_nan_input_handled() -> None:
    """NaN entries are stripped; surviving sample length drives verdict."""
    x = np.full(2048, np.nan, dtype=np.float64)
    r = dfa_hurst(x)
    assert r.verdict == "INCONCLUSIVE"
    assert r.n_samples_used == 0
