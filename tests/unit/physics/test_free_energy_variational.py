# SPDX-License-Identifier: MIT
"""Tests for :mod:`core.physics.free_energy_variational`.

Pins three classes of contract:

1. **Algebraic exact** — closed-form KL identities and zero-self-distance
   to machine precision (1e-12).
2. **Universal property** — KL ≥ 0 always (Gibbs inequality); surprise
   ≥ 0; finite input ⟹ finite output.
3. **Decomposition consistency** — variational_free_energy =
   kl_divergence − expected_log_likelihood, exactly.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.physics.free_energy_variational import (
    DiagonalGaussianBelief,
    GaussianBelief,
    expected_log_likelihood,
    kl_divergence,
    kl_divergence_diagonal,
    surprise,
    variational_free_energy,
)

_ALGEBRAIC_TOL: float = 1e-12


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------


def test_gaussian_belief_rejects_non_finite_mean() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="mean must be finite"):
            GaussianBelief(mean=bad, log_variance=0.0)


def test_gaussian_belief_rejects_non_finite_log_variance() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="log_variance must be finite"):
            GaussianBelief(mean=0.0, log_variance=bad)


def test_diagonal_gaussian_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="same shape"):
        DiagonalGaussianBelief(
            mean=np.zeros(3, dtype=np.float64),
            log_variance=np.zeros(4, dtype=np.float64),
        )


def test_diagonal_gaussian_rejects_2d() -> None:
    with pytest.raises(ValueError, match="1-D"):
        DiagonalGaussianBelief(
            mean=np.zeros((2, 3), dtype=np.float64),
            log_variance=np.zeros((2, 3), dtype=np.float64),
        )


# ---------------------------------------------------------------------------
# KL — algebraic identities
# ---------------------------------------------------------------------------


def test_kl_self_distance_is_zero() -> None:
    """Gibbs identity: KL[q || q] = 0 to machine precision."""
    for mean, log_var in [(0.0, 0.0), (3.14, 1.5), (-7.2, -0.5)]:
        q = GaussianBelief(mean=mean, log_variance=log_var)
        kl = kl_divergence(q, q)
        assert abs(kl) < _ALGEBRAIC_TOL, (
            f"KL self-distance non-zero: KL[N({mean}, exp({log_var})) || itself] "
            f"= {kl:.3e}, expected < {_ALGEBRAIC_TOL:.0e}. "
            "Gibbs inequality is the algebraic floor; any non-zero residual "
            "means the closed-form decomposition has drifted."
        )


@pytest.mark.parametrize("mu_q", [0.5, 1.0, 2.0, -1.5, 5.0])
def test_kl_mean_shift_under_unit_variance(mu_q: float) -> None:
    """KL[N(μ, 1) || N(0, 1)] = μ²/2 — exact closed form."""
    q = GaussianBelief(mean=mu_q, log_variance=0.0)
    p = GaussianBelief(mean=0.0, log_variance=0.0)
    expected = 0.5 * mu_q**2
    observed = kl_divergence(q, p)
    assert abs(observed - expected) < _ALGEBRAIC_TOL, (
        f"KL[N({mu_q}, 1) || N(0, 1)] = {observed!r}, expected {expected!r}; "
        f"error = {abs(observed - expected):.3e} > {_ALGEBRAIC_TOL:.0e}."
    )


@pytest.mark.parametrize("log_var_q", [-1.0, -0.5, 0.5, 1.0, 2.0])
def test_kl_variance_only_under_zero_mean(log_var_q: float) -> None:
    """KL[N(0, σ²) || N(0, 1)] = 0.5·(σ² − 1 − log σ²) — exact closed form."""
    q = GaussianBelief(mean=0.0, log_variance=log_var_q)
    p = GaussianBelief(mean=0.0, log_variance=0.0)
    sigma_sq = math.exp(log_var_q)
    expected = 0.5 * (sigma_sq - 1.0 - log_var_q)
    observed = kl_divergence(q, p)
    assert abs(observed - expected) < _ALGEBRAIC_TOL, (
        f"KL[N(0, exp({log_var_q})) || N(0, 1)] = {observed!r}, "
        f"expected {expected!r}; error = {abs(observed - expected):.3e}."
    )


@given(
    mu_q=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    log_var_q=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    mu_p=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    log_var_p=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_kl_property_non_negative_under_random_pair(
    mu_q: float, log_var_q: float, mu_p: float, log_var_p: float
) -> None:
    """Gibbs inequality: KL[q || p] ≥ 0 for any (q, p)."""
    q = GaussianBelief(mean=mu_q, log_variance=log_var_q)
    p = GaussianBelief(mean=mu_p, log_variance=log_var_p)
    kl = kl_divergence(q, p)
    # Allow ULP slack: KL can underflow to a tiny negative when q ≈ p.
    assert kl >= -1e-10, (
        f"Gibbs inequality VIOLATED: KL = {kl:.6e} < -1e-10 "
        f"at q=({mu_q}, {log_var_q}), p=({mu_p}, {log_var_p}). "
        "Closed-form KL between Gaussians must be non-negative."
    )


# ---------------------------------------------------------------------------
# Diagonal multivariate KL
# ---------------------------------------------------------------------------


def test_kl_diagonal_reduces_to_sum_of_univariate() -> None:
    """Independence under diagonal covariance: KL_diag = Σ KL_univariate."""
    rng = np.random.default_rng(42)
    n = 5
    mean_q = rng.normal(0.0, 1.0, size=n)
    log_var_q = rng.normal(0.0, 0.5, size=n)
    mean_p = rng.normal(0.0, 1.0, size=n)
    log_var_p = rng.normal(0.0, 0.5, size=n)

    diag_kl = kl_divergence_diagonal(
        DiagonalGaussianBelief(mean=mean_q, log_variance=log_var_q),
        DiagonalGaussianBelief(mean=mean_p, log_variance=log_var_p),
    )
    summed = sum(
        kl_divergence(
            GaussianBelief(mean=mean_q[i], log_variance=log_var_q[i]),
            GaussianBelief(mean=mean_p[i], log_variance=log_var_p[i]),
        )
        for i in range(n)
    )
    assert abs(diag_kl - summed) < _ALGEBRAIC_TOL, (
        f"Diagonal KL ({diag_kl}) != Σ univariate KL ({summed}); "
        f"difference {abs(diag_kl - summed):.3e} > {_ALGEBRAIC_TOL:.0e}. "
        "Independence under diagonal covariance is the algebraic floor."
    )


# ---------------------------------------------------------------------------
# Surprise
# ---------------------------------------------------------------------------


def test_surprise_minimum_at_mean() -> None:
    """Surprise minimum = 0.5·log(2π·σ²); attained at observation = μ."""
    log_var = 0.5
    sigma_sq = math.exp(log_var)
    expected_min = 0.5 * (math.log(2.0 * math.pi) + log_var)
    s = surprise(observation=2.7, predicted_mean=2.7, predicted_log_variance=log_var)
    assert abs(s - expected_min) < _ALGEBRAIC_TOL, (
        f"Surprise at mean = {s}, expected = {expected_min}; "
        f"σ² = {sigma_sq}; the residual term must vanish at observation == mean."
    )


def test_surprise_grows_quadratically_with_residual() -> None:
    """Surprise at residual r grows as r²/(2σ²) above the floor."""
    base_mean = 0.0
    log_var = 0.0  # σ² = 1
    sigma_sq = 1.0
    floor = surprise(
        observation=base_mean,
        predicted_mean=base_mean,
        predicted_log_variance=log_var,
    )
    for r in [0.5, 1.0, 2.0, 5.0]:
        s = surprise(
            observation=base_mean + r,
            predicted_mean=base_mean,
            predicted_log_variance=log_var,
        )
        expected_excess = 0.5 * (r**2) / sigma_sq
        observed_excess = s - floor
        assert abs(observed_excess - expected_excess) < _ALGEBRAIC_TOL, (
            f"Surprise excess at r={r}: observed {observed_excess}, expected "
            f"{expected_excess} (= r²/(2σ²) with σ²={sigma_sq}); error "
            f"{abs(observed_excess - expected_excess):.3e}."
        )


def test_surprise_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="finite"):
        surprise(observation=math.nan, predicted_mean=0.0, predicted_log_variance=0.0)
    with pytest.raises(ValueError, match="finite"):
        surprise(observation=0.0, predicted_mean=math.inf, predicted_log_variance=0.0)


# ---------------------------------------------------------------------------
# Free-energy decomposition consistency
# ---------------------------------------------------------------------------


def test_free_energy_equals_complexity_minus_accuracy() -> None:
    """F = D_KL[q || p] − E_q[log p(s | z)] — algebraic identity."""
    q = GaussianBelief(mean=1.0, log_variance=0.5)
    p = GaussianBelief(mean=0.0, log_variance=0.0)
    s = 1.5
    obs_log_var = 0.0
    F = variational_free_energy(q, p, observation=s, observation_log_variance=obs_log_var)
    complexity = kl_divergence(q, p)
    accuracy = expected_log_likelihood(q, observation=s, observation_log_variance=obs_log_var)
    assert abs(F - (complexity - accuracy)) < _ALGEBRAIC_TOL, (
        f"FE decomposition VIOLATED: F = {F}, "
        f"complexity − accuracy = {complexity - accuracy}; "
        f"residual {abs(F - (complexity - accuracy)):.3e}."
    )


@given(
    mu_q=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    log_var_q=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    mu_p=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    log_var_p=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    s=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    obs_log_var=st.floats(min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_free_energy_property_finite_under_finite_inputs(
    mu_q: float,
    log_var_q: float,
    mu_p: float,
    log_var_p: float,
    s: float,
    obs_log_var: float,
) -> None:
    """INV-HPC2: finite input ⟹ finite F."""
    q = GaussianBelief(mean=mu_q, log_variance=log_var_q)
    p = GaussianBelief(mean=mu_p, log_variance=log_var_p)
    F = variational_free_energy(q, p, observation=s, observation_log_variance=obs_log_var)
    assert math.isfinite(F), (
        f"INV-HPC2 VIOLATED: F = {F!r} not finite under finite inputs "
        f"q=({mu_q}, {log_var_q}), p=({mu_p}, {log_var_p}), s={s}, "
        f"obs_log_var={obs_log_var}."
    )


def test_diagonal_belief_rejects_any_nonfinite_component() -> None:
    """`not (isfinite(mean).all() and isfinite(log_var).all())` -- ALL components must be finite.

    Under `And -> Or` the guard fires only when BOTH arrays are entirely non-finite, so a
    belief with a single NaN mean (or log-variance) is silently admitted into the free-energy
    computation. One NaN in either field must fail closed.
    """
    from core.physics.free_energy_variational import DiagonalGaussianBelief

    with pytest.raises(ValueError, match="all-finite"):
        DiagonalGaussianBelief(mean=np.array([1.0, np.nan]), log_variance=np.array([0.0, 0.0]))
    with pytest.raises(ValueError, match="all-finite"):
        DiagonalGaussianBelief(mean=np.array([1.0, 2.0]), log_variance=np.array([0.0, np.inf]))
    # A fully finite belief is admitted.
    DiagonalGaussianBelief(mean=np.array([1.0, 2.0]), log_variance=np.array([0.0, -1.0]))


def test_expected_log_likelihood_rejects_nonfinite_observation() -> None:
    """`not (isfinite(observation) and isfinite(observation_log_variance))` fail-closes."""
    from core.physics.free_energy_variational import GaussianBelief, expected_log_likelihood

    q = GaussianBelief(mean=0.0, log_variance=0.0)
    with pytest.raises(ValueError):
        expected_log_likelihood(q, observation=float("nan"), observation_log_variance=0.0)
    with pytest.raises(ValueError):
        expected_log_likelihood(q, observation=0.0, observation_log_variance=float("inf"))
