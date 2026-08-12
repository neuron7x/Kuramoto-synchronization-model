# SPDX-License-Identifier: MIT
"""T22 (robustness companion) — INV-LE1 adversarial finiteness battery.

The companion file (`test_T22_lyapunov_spectral.py`) sweeps five
hand-picked input families (white noise, constant, sine, random
walk, step) and asserts MLE finiteness on each. INV-LE1 reads
"MLE is finite for **any** bounded finite input series" — the
universal claim is stronger than any hand-picked sweep.

This file closes that gap with two fixtures:

1. **Adversarial corpus** — explicitly constructed pathological
   inputs that strain the Rosenstein nearest-neighbor algorithm:
   single huge spikes, ramps, near-overflow magnitudes, bimodal
   clusters. Inputs that retain measurable divergence must yield a
   finite MLE; two-value-collapsed inputs (whose Theiler-excluded
   neighbors all sit at distance 0) have no divergence to measure
   and MUST fail closed (Rosenstein 1993 §2.2).
2. **Hypothesis fuzz** — randomly generated bounded series with
   widely-varying length, embedding dimension, and tau. The MLE
   must be a finite real, or — for a degenerate draw — fail closed
   with an INV-LE1 ValueError. A non-finite return is never allowed.

Why this matters
----------------

INV-LE1 is P0. A non-finite MLE — or a *spurious* λ=0 silently
returned for a constant/zero-variance input — propagates through
Kelly sizing and risk gating, in the constant case falsely labelling
a frozen series as a "stable regime". The corrected contract fails
closed on degenerate input; catching it at the estimator boundary is
cheaper than catching it at the order-book.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.physics.lyapunov_exponent import maximal_lyapunov_exponent


def _assert_finite_mle(label: str, mle: float, **params: object) -> None:
    assert math.isfinite(mle), (
        f"INV-LE1 VIOLATED on {label}: MLE = {mle} is not finite. "
        f"Expected finite real for any bounded finite input. "
        f"Observed at params={params}. "
        "Physical reasoning: Rosenstein nearest-neighbor divergence "
        "on a bounded series cannot diverge to ±∞ in finite steps; "
        "non-finite output means a degenerate divisor (zero-distance "
        "neighbors) was not guarded."
    )


# ---------------------------------------------------------------------------
# Adversarial corpus
# ---------------------------------------------------------------------------


def test_inv_le1_single_huge_spike() -> None:
    """One enormous outlier in an otherwise calm series."""
    n = 600
    series = np.zeros(n, dtype=np.float64)
    series[n // 2] = 1e6
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    _assert_finite_mle("single_huge_spike", mle, n=n, dim=3, tau=1)


def test_inv_le1_two_value_alternating() -> None:
    """Degenerate alternation: only two unique values.

    Contract correction: under the Theiler temporal-exclusion window every
    nearest neighbor of a [0,1,0,1,...] series lands on a same-phase point at
    distance 0, so the divergence rate is everywhere undefined (Rosenstein
    1993 §2.2). This is the same zero-divergence class as a constant series —
    the corrected INV-LE1 fails closed rather than masking it as λ=0.
    """
    n = 600
    series = np.tile([0.0, 1.0], n // 2).astype(np.float64)
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(series, dim=3, tau=1)


def test_inv_le1_linear_ramp() -> None:
    """Pure linear ramp — perfectly predictable, zero divergence."""
    n = 600
    series = np.linspace(-1.0, 1.0, n, dtype=np.float64)
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    _assert_finite_mle("linear_ramp", mle, n=n, dim=3, tau=1)


def test_inv_le1_extreme_alternation() -> None:
    """Alternating ±1e6 — extreme magnitude, two-value-collapsed structure.

    Contract correction: like ``two_value_alternating`` this is a two-unique-
    value series whose Theiler-excluded nearest neighbors collapse to distance
    0, leaving no measurable divergence. The corrected INV-LE1 fails closed.
    """
    n = 600
    series = np.tile([-1e6, 1e6], n // 2).astype(np.float64)
    with pytest.raises(ValueError, match="INV-LE1"):
        maximal_lyapunov_exponent(series, dim=3, tau=1)


def test_inv_le1_near_overflow_magnitudes() -> None:
    """Series in the upper IEEE-754 double range — risks float overflow
    in pairwise distance computations."""
    n = 600
    rng = np.random.default_rng(seed=11)
    series = rng.normal(0.0, 1e150, size=n)
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    _assert_finite_mle("near_overflow_magnitudes", mle, n=n, dim=3, tau=1)


def test_inv_le1_short_minimal_series() -> None:
    """Short series at the lower bound of where embedding makes sense.

    With dim=3, tau=1 the embedding consumes the first 2 samples,
    so a 50-sample series is the minimum non-vacuous fixture.
    """
    n = 50
    rng = np.random.default_rng(seed=7)
    series = rng.normal(0.0, 1.0, size=n)
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    _assert_finite_mle("short_minimal_series", mle, n=n, dim=3, tau=1)


def test_inv_le1_bimodal_clusters() -> None:
    """Two tight clusters far apart — many zero-distance neighbors."""
    n = 600
    rng = np.random.default_rng(seed=23)
    cluster_a = rng.normal(0.0, 1e-6, size=n // 2)
    cluster_b = rng.normal(1e3, 1e-6, size=n // 2)
    series = np.concatenate([cluster_a, cluster_b])
    rng.shuffle(series)
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    _assert_finite_mle("bimodal_clusters", mle, n=n, dim=3, tau=1)


def test_inv_le1_negative_zero_mixture() -> None:
    """Series with both +0.0 and −0.0 — IEEE-754 sign edge case."""
    n = 600
    series = np.zeros(n, dtype=np.float64)
    series[::2] = -0.0
    series[1::2] = 0.0
    series[100] = 1.0  # one non-zero point so embedding has structure
    mle = maximal_lyapunov_exponent(series, dim=3, tau=1)
    _assert_finite_mle("negative_zero_mixture", mle, n=n, dim=3, tau=1)


# ---------------------------------------------------------------------------
# Hypothesis fuzz
# ---------------------------------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    n=st.integers(min_value=80, max_value=400),
    dim=st.integers(min_value=2, max_value=5),
    tau=st.integers(min_value=1, max_value=4),
    scale=st.floats(min_value=1e-12, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_inv_le1_hypothesis_fuzz_keeps_mle_finite(
    seed: int, n: int, dim: int, tau: int, scale: float
) -> None:
    """INV-LE1 universal: fuzz the input space.

    Either the MLE is a finite real, or (for a degenerate draw whose embedded
    points all collapse to one location) the estimator fails closed with a
    ValueError naming INV-LE1. What is NEVER permitted is a non-finite return
    value — that is the masking bug INV-LE1 exists to prevent.
    """
    rng = np.random.default_rng(seed=seed)
    series = rng.normal(0.0, scale, size=n)
    try:
        mle = maximal_lyapunov_exponent(series, dim=dim, tau=tau)
    except ValueError as exc:
        assert "INV-LE1" in str(exc), (
            f"hypothesis_fuzz raised a non-INV-LE1 ValueError at "
            f"seed={seed}, n={n}, dim={dim}, tau={tau}, scale={scale}: {exc}"
        )
        return
    _assert_finite_mle(
        "hypothesis_fuzz",
        mle,
        seed=seed,
        n=n,
        dim=dim,
        tau=tau,
        scale=scale,
    )
