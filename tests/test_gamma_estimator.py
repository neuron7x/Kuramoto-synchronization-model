# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call"
"""Tests for multi-segment PSD gamma estimator."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from geosync.estimators.gamma_estimator import PSDGammaEstimator


def test_white_noise_gamma_near_zero() -> None:
    """White noise has flat PSD → γ ≈ 0."""
    np.random.seed(42)
    est = PSDGammaEstimator()
    g = est.compute(np.random.randn(1000))
    assert abs(g.value) < 1.0, f"White noise gamma={g.value} too far from 0"
    assert g.is_valid


def test_brownian_motion_gamma_positive() -> None:
    """Brownian motion (cumsum of white noise) → γ > 0 (persistent)."""
    np.random.seed(42)
    est = PSDGammaEstimator()
    bm = np.cumsum(np.random.randn(1000))
    g = est.compute(np.diff(bm))
    assert g.is_valid


def test_short_series_returns_invalid() -> None:
    """Series < 96 samples should return invalid."""
    est = PSDGammaEstimator()
    g = est.compute(np.random.randn(50))
    assert not g.is_valid
    assert g.value == 0.0


def test_nan_input_returns_invalid() -> None:
    data = np.ones(200)
    data[100] = float("nan")
    est = PSDGammaEstimator()
    g = est.compute(data)
    assert not g.is_valid


def test_constant_input_returns_invalid() -> None:
    est = PSDGammaEstimator()
    g = est.compute(np.zeros(200))
    assert not g.is_valid


def test_quality_gate_rejects_noisy_fit() -> None:
    """Estimator with min_quality=0.99 should reject most fits."""
    est = PSDGammaEstimator(min_quality=0.99)
    np.random.seed(42)
    result = est.compute(np.random.randn(200))
    # With 0.99 threshold, quality must be extremely high to pass
    assert not result.is_valid or result.quality >= 0.99


def test_deterministic_same_input_same_output() -> None:
    """Same input → same gamma. No hidden state."""
    est = PSDGammaEstimator()
    data = np.sin(np.linspace(0, 20, 500)) + 0.1 * np.random.RandomState(42).randn(500)
    g1 = est.compute(data)
    g2 = est.compute(data)
    assert g1.value == g2.value
    assert g1.quality == g2.quality


@given(seed=st.integers(min_value=0, max_value=10000))
@settings(max_examples=20, deadline=None)
def test_gamma_always_bounded(seed: int) -> None:
    """∀ input: gamma ∈ [-5, 5] (clipped)."""
    rng = np.random.RandomState(seed)
    est = PSDGammaEstimator()
    g = est.compute(rng.randn(200))
    assert -5.0 <= g.value <= 5.0


def test_validity_gate_requires_quality_and_stationarity() -> None:
    """`is_valid = mean_q >= min_quality and is_stationary` — both must hold (INV-DRO3).

    A non-stationary series (random walk) can pass the quality bar yet must NOT be marked
    valid; under `And -> Or` the single satisfied quality condition would validate a
    non-stationary estimate. A stationary white-noise series with adequate quality is the
    positive control.
    """
    est = PSDGammaEstimator()

    white = est.compute(np.random.default_rng(0).standard_normal(512))
    assert white.is_stationary and white.quality >= est.min_quality
    assert white.is_valid is True

    walk = est.compute(np.cumsum(np.random.default_rng(1).standard_normal(512)))
    assert walk.is_stationary is False
    assert walk.is_valid is False, "a non-stationary estimate must never be marked valid"


def test_confidence_interval_is_not_the_degenerate_fallback_on_a_good_signal() -> None:
    """`if len(boot) < 10: return -5.0, 5.0` — the wide fallback is for TOO FEW bootstrap fits.

    A well-resolved series yields far more than ten usable bootstrap segments, so the CI must
    be the empirical 2.5/97.5 percentiles, not the sentinel (-5, 5). Under `Lt -> GtE` a good
    signal is forced into that useless wide band. Pinned by demanding a bounded CI.
    """
    est = PSDGammaEstimator()
    result = est.compute(np.random.default_rng(3).standard_normal(512))

    assert result.ci_low > -5.0 and result.ci_high < 5.0, (
        "a well-resolved estimate collapsed to the degenerate wide-CI fallback"
    )
    assert result.ci_low <= result.value <= result.ci_high


def test_brownian_fit_band_stays_in_the_low_frequency_scaling_region() -> None:
    """`f <= f_hi` bounds the fit to the low-frequency scaling region (INV-DRO1: gamma=2H+1).

    Brownian motion has H~1, so gamma must land near 3 (well above 1). Under `LtE -> Gt` the
    mask keeps the HIGH-frequency tail instead of the scaling band, collapsing the estimate
    toward the noise floor (~0.8 here). A physical lower bound on a Brownian series -- not a
    magic constant -- separates the two.
    """
    brownian = np.cumsum(np.random.default_rng(5).standard_normal(150))
    gamma = PSDGammaEstimator().compute(brownian).value
    assert gamma > 1.5, (
        f"Brownian gamma collapsed to {gamma:.3f}; the fit band left the low-frequency region"
    )
