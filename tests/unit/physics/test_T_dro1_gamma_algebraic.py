# SPDX-License-Identifier: MIT
"""T-DRO1 (algebraic) — `γ = 2·H + 1` to documented precision.

INV-DRO1 (universal, P0) reads::

    γ = 2·H + 1 to float precision; tolerance |γ − (2H+1)| < 1e-5.

The implementation in :func:`core.dro_ara.engine.derive_gamma`
returns ``(round(2H+1, 6), round(H, 6), round(r2, 6))``. By
construction the rounding to 6 decimal places keeps the residual
``|γ − (2H+1)|`` strictly below ``5e-7`` — well inside the
``1e-5`` ceiling of the invariant — but only if the *internal*
computation is correct. The point of this test is to pin the
relationship across a sweep of inputs (synthetic and stochastic),
so any future refactor that decouples ``γ`` from ``H`` (e.g., via
a separate estimator) is caught immediately.

Why a separate file from ``test_dfa_gamma_estimator.py``
--------------------------------------------------------

The existing test focuses on Hurst-exponent recovery accuracy on
synthetic fractional Brownian motion. INV-DRO1 is a different
claim: it pins the *algebraic identity* between the two returned
fields. The two tests are complementary; this one falsifies a
specific class of bug (γ and H drift apart) that an H-recovery
test cannot.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.dro_ara.engine import derive_gamma

# Documented tolerance from the INV-DRO1 spec.
_GAMMA_H_TOL: float = 1e-5


def _assert_gamma_equals_2h_plus_1(label: str, gamma: float, H: float, **params: object) -> None:
    residual = abs(gamma - (2.0 * H + 1.0))
    assert residual < _GAMMA_H_TOL, (
        f"INV-DRO1 VIOLATED on {label}: "
        f"|γ − (2H+1)| = {residual:.3e} > {_GAMMA_H_TOL:.0e}. "
        f"γ={gamma!r}, H={H!r}, params={params}. "
        "Physical reasoning: γ and H come from the same DFA estimator; "
        "the algebraic relation is the contract — drift implies the "
        "two fields were computed from divergent intermediate states."
    )


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 101, 314, 2024, 9999])
def test_inv_dro1_random_walk_input(seed: int) -> None:
    """INV-DRO1 on random-walk inputs: γ = 2H + 1 over a length sweep.

    Property-style: the algebraic identity is asserted for every length in
    a per-seed sweep, so the contract is pinned across input sizes, not at
    a single n.
    """
    rng = np.random.default_rng(seed=seed)
    for n in (512, 1024, 2048):
        series = np.cumsum(rng.normal(0.0, 1.0, size=n))
        gamma, H, _r2 = derive_gamma(series)
        assert math.isfinite(gamma) and math.isfinite(H), (
            f"INV-DRO1 VIOLATED: derive_gamma returned non-finite observed "
            f"(γ={gamma}, H={H}) at seed={seed} with n={n}; DFA on a random "
            "walk must yield finite γ and H."
        )
        _assert_gamma_equals_2h_plus_1("random_walk", gamma, H, seed=seed, n=n)


@pytest.mark.parametrize("slope", [0.001, 0.01, 0.05, 0.1])
def test_inv_dro1_linear_trend_input(slope: float) -> None:
    """INV-DRO1 on a deterministic linear trend over a length sweep.

    Linear trend yields trivial DFA fluctuation; whatever (H, γ) the
    estimator returns, the algebraic identity γ = 2H + 1 must hold for
    every sampled length where both fields are finite.
    """
    for n in (512, 1024, 2048):
        series = slope * np.arange(n, dtype=np.float64)
        gamma, H, _r2 = derive_gamma(series)
        if not (math.isfinite(gamma) and math.isfinite(H)):
            # A degenerate input may produce a sentinel; that is acceptable.
            # The invariant is conditional on finiteness of both fields.
            continue
        _assert_gamma_equals_2h_plus_1("linear_trend", gamma, H, slope=slope, n=n)


@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    n=st.integers(min_value=256, max_value=2048),
    sigma=st.floats(min_value=1e-3, max_value=1e3, allow_nan=False, allow_infinity=False),
)
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_inv_dro1_hypothesis_random_walk_invariance(seed: int, n: int, sigma: float) -> None:
    """INV-DRO1 fuzz: identity holds across (seed, n, sigma) configurations."""
    rng = np.random.default_rng(seed=seed)
    series = np.cumsum(rng.normal(0.0, sigma, size=n))
    gamma, H, _r2 = derive_gamma(series)
    if not (math.isfinite(gamma) and math.isfinite(H)):
        return
    _assert_gamma_equals_2h_plus_1("hypothesis_walk", gamma, H, seed=seed, n=n, sigma=sigma)


def test_inv_dro1_known_exact_relation_for_pure_brownian() -> None:
    """INV-DRO1: pure Brownian motion has H ≈ 0.5 ⟹ γ = 2H + 1 ≈ 2.

    The DFA estimator on a long enough Brownian path should
    recover H ≈ 0.5 ± ~0.1 for n=4096; whatever H it returns,
    γ must equal 2H+1 within the spec tolerance.
    """
    # Property-style: sweep several independent Brownian realizations; the
    # algebraic identity must hold on every one (a single path could pass
    # by luck of the estimator's rounding).
    for seed in (12345, 222, 7, 90909):
        rng = np.random.default_rng(seed=seed)
        n = 4096
        series = np.cumsum(rng.normal(0.0, 1.0, size=n))
        gamma, H, r2 = derive_gamma(series)
        _assert_gamma_equals_2h_plus_1("pure_brownian_n4096", gamma, H, seed=seed, n=n)
        # Sanity: r2 should indicate a clean linear DFA fit on Brownian.
        assert math.isfinite(r2), (
            f"INV-DRO1 / INV-HPC2 VIOLATED: at seed={seed} with n={n} observed "
            f"r2={r2!r} non-finite; the DFA log-log fit quality must be a finite "
            "number for a well-formed Brownian path."
        )
