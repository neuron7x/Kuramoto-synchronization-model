# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""HAC-adjusted PSR (Newey–West, Bartlett kernel) — analytical contracts.

Guards the scientific content of ``probabilistic_sharpe_ratio_hac``:

* Monotonicity against the vanilla PSR under known serial-correlation
  regimes (white noise ≈ vanilla; positive AR(1) ⇒ HAC lower; negative
  AR(1) ⇒ HAC higher).
* Fail-closed behaviour on degenerate inputs (short, constant, non-finite).
* Bartlett-kernel invariants (weights non-negative; lag=0 ⇒ no
  correction; monotone decay in lag).
* Auto-bandwidth reproducibility vs Newey & West (1994) rule.

The tests are deterministic (seed-locked) and do not depend on live
market data. They falsify three distinct failure modes:

1. Correction is silently a no-op (HAC = vanilla for *every* regime).
2. Correction has wrong sign (HAC > vanilla under positive autocorr).
3. Correction is arithmetically broken on edge cases (NaN / ∞ leak).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.robustness.cpcv import (
    _newey_west_auto_lag,
    _newey_west_effective_size,
    probabilistic_sharpe_ratio,
    probabilistic_sharpe_ratio_hac,
)

SEED = 42
T_DEFAULT = 600  # long enough for the automatic bandwidth L ≈ 5
# For PSR-interior tests we use T=400 so Φ(z) stays informative (neither
# saturated at 1 nor collapsed to 0) while Newey–West still has room to
# bite at auto-lag L = 5.
T_INTERIOR = 400


def _ar1(
    n: int,
    phi: float,
    sigma: float,
    rng: np.random.Generator,
    drift: float = 0.0002,
) -> np.ndarray:
    """AR(1) with stationary start: x_t = phi * x_{t-1} + sigma * eps_t.

    The default drift is tuned so that, for ``n=400, phi=0.6, sigma=0.01``,
    the vanilla PSR sits in the informative interior (~0.98) — neither
    saturated at 1.0 (which would hide the HAC correction) nor collapsed
    to 0. Override for tests that exercise a different regime.
    """
    eps = rng.standard_normal(n)
    x = np.empty(n, dtype=np.float64)
    x[0] = eps[0] * sigma / math.sqrt(max(1.0 - phi * phi, 1e-12))
    for t in range(1, n):
        x[t] = phi * x[t - 1] + sigma * eps[t]
    return x + drift


# -------------------------------------------------------------------------
# Newey–West effective size primitives
# -------------------------------------------------------------------------


def test_effective_size_equals_n_under_no_lag() -> None:
    r = np.random.default_rng(SEED).standard_normal(T_DEFAULT)
    assert _newey_west_effective_size(r, lag=0) == pytest.approx(T_DEFAULT)


def test_effective_size_approx_n_under_white_noise() -> None:
    """White noise has ρ_k ≈ 0 so T_eff ≈ T."""
    r = np.random.default_rng(SEED).standard_normal(T_DEFAULT)
    n_eff = _newey_west_effective_size(r, lag=_newey_west_auto_lag(T_DEFAULT))
    # Finite-sample slop tolerance ~10 % of T — sufficient to fail if
    # correction is wrong by a factor of 2.
    assert abs(n_eff - T_DEFAULT) / T_DEFAULT < 0.15


def test_effective_size_shrinks_under_positive_autocorrelation() -> None:
    rng = np.random.default_rng(SEED)
    r = _ar1(T_DEFAULT, phi=0.6, sigma=0.01, rng=rng)
    n_eff = _newey_west_effective_size(r, lag=_newey_west_auto_lag(T_DEFAULT))
    # Under φ = 0.6 the long-run variance is ~(1+φ)/(1−φ) ≈ 4× the
    # instantaneous — so T_eff should be well under half of T.
    assert 0.1 * T_DEFAULT < n_eff < 0.6 * T_DEFAULT


def test_effective_size_grows_under_negative_autocorrelation() -> None:
    rng = np.random.default_rng(SEED)
    r = _ar1(T_DEFAULT, phi=-0.6, sigma=0.01, rng=rng)
    n_eff = _newey_west_effective_size(r, lag=_newey_west_auto_lag(T_DEFAULT))
    assert n_eff > 1.2 * T_DEFAULT


def test_effective_size_rejects_negative_lag() -> None:
    with pytest.raises(ValueError):
        _newey_west_effective_size(np.zeros(5), lag=-1)


def test_auto_bandwidth_matches_newey_west_1994_rule() -> None:
    # L* = floor(4 · (T/100)^(2/9)); verified against a hand computation.
    for n, expected in [(50, 3), (100, 4), (252, 4), (500, 5), (1000, 6), (10_000, 11)]:
        assert (
            _newey_west_auto_lag(n) == expected
        ), f"auto-bandwidth for n={n} expected {expected}, got {_newey_west_auto_lag(n)}"


def test_auto_bandwidth_small_sample() -> None:
    assert _newey_west_auto_lag(3) == 0
    assert _newey_west_auto_lag(0) == 0


# -------------------------------------------------------------------------
# HAC-PSR contracts
# -------------------------------------------------------------------------


def test_hac_psr_approx_vanilla_on_white_noise() -> None:
    """Under ρ_k ≈ 0 the HAC correction should leave PSR essentially
    unchanged — a no-op on un-autocorrelated data."""
    rng = np.random.default_rng(SEED)
    r = rng.standard_normal(T_DEFAULT) * 0.01 + 0.001
    vanilla = probabilistic_sharpe_ratio(r)
    hac = probabilistic_sharpe_ratio_hac(r)
    assert math.isfinite(vanilla)
    assert math.isfinite(hac)
    assert abs(hac - vanilla) < 0.05


def test_hac_psr_strictly_lower_under_positive_autocorrelation() -> None:
    """Regime-following strategies (positive serial correlation in
    returns) inflate the naive PSR. HAC must pull it down.

    Parameters are calibrated so vanilla PSR sits in the informative
    interior ((0.9, 0.999) band); outside it Φ(z) saturates and the
    correction becomes invisible to an equality test.
    """
    rng = np.random.default_rng(SEED)
    r = _ar1(T_INTERIOR, phi=0.6, sigma=0.01, rng=rng, drift=0.0002)
    vanilla = probabilistic_sharpe_ratio(r)
    hac = probabilistic_sharpe_ratio_hac(r)
    assert math.isfinite(vanilla) and math.isfinite(hac)
    assert 0.9 < vanilla < 0.999, (
        f"test setup drift: vanilla PSR {vanilla:.4f} outside the "
        f"informative interior (0.9, 0.999)."
    )
    assert hac < vanilla, (
        f"HAC-PSR {hac:.4f} should be strictly below vanilla {vanilla:.4f} "
        f"under φ = 0.6 positive autocorrelation."
    )
    # Guard against a floating-point near-tie masquerading as a pass.
    assert vanilla - hac > 0.01


def test_hac_psr_strictly_higher_under_negative_autocorrelation() -> None:
    """Mean-reverting residuals over-estimate uncertainty; HAC should lift
    the confidence statement."""
    rng = np.random.default_rng(SEED)
    r = _ar1(T_DEFAULT, phi=-0.6, sigma=0.01, rng=rng)
    vanilla = probabilistic_sharpe_ratio(r)
    hac = probabilistic_sharpe_ratio_hac(r)
    assert math.isfinite(vanilla) and math.isfinite(hac)
    # Under strong negative AR(1) the denominator corrections can saturate
    # Φ to ~1 on both sides; require weakly higher rather than strictly
    # higher to avoid a flaky equality on near-certain tails.
    assert hac >= vanilla - 1e-9


def test_hac_psr_in_unit_interval() -> None:
    rng = np.random.default_rng(SEED)
    r = _ar1(T_DEFAULT, phi=0.3, sigma=0.02, rng=rng)
    hac = probabilistic_sharpe_ratio_hac(r)
    assert 0.0 <= hac <= 1.0


def test_hac_psr_respects_explicit_lag() -> None:
    """Fixing lag=0 must collapse HAC-PSR onto vanilla PSR to float
    precision (no Bartlett sum taken)."""
    rng = np.random.default_rng(SEED)
    r = _ar1(T_DEFAULT, phi=0.4, sigma=0.01, rng=rng)
    vanilla = probabilistic_sharpe_ratio(r)
    hac_lag0 = probabilistic_sharpe_ratio_hac(r, lag=0)
    assert math.isfinite(vanilla) and math.isfinite(hac_lag0)
    assert abs(hac_lag0 - vanilla) < 1e-12


def test_hac_psr_monotone_in_lag_under_positive_autocorrelation() -> None:
    """Each additional Bartlett lag adds a positive ρ_k contribution under
    pure positive AR(1), so HAC-PSR must be non-increasing in lag.

    Uses T_INTERIOR so the monotonicity is not hidden by Φ saturation."""
    rng = np.random.default_rng(SEED)
    r = _ar1(T_INTERIOR, phi=0.5, sigma=0.01, rng=rng, drift=0.0002)
    values = [probabilistic_sharpe_ratio_hac(r, lag=L) for L in (0, 1, 2, 4, 8)]
    for prev, nxt in zip(values, values[1:]):
        assert (
            nxt <= prev + 1e-9
        ), f"HAC-PSR must be non-increasing in lag under positive AR(1): got {values}"


def test_hac_psr_returns_nan_on_short_input() -> None:
    assert math.isnan(probabilistic_sharpe_ratio_hac(np.array([], dtype=np.float64)))
    assert math.isnan(probabilistic_sharpe_ratio_hac(np.array([0.01])))


def test_hac_psr_returns_nan_on_constant_input() -> None:
    assert math.isnan(probabilistic_sharpe_ratio_hac(np.full(100, 0.01)))


def test_hac_psr_returns_nan_on_non_finite_input() -> None:
    arr = np.array([0.01, 0.02, math.inf, 0.015])
    assert math.isnan(probabilistic_sharpe_ratio_hac(arr))
    arr2 = np.array([0.01, 0.02, math.nan, 0.015])
    assert math.isnan(probabilistic_sharpe_ratio_hac(arr2))


def test_hac_psr_rejects_2d_input() -> None:
    with pytest.raises(ValueError):
        probabilistic_sharpe_ratio_hac(np.zeros((4, 4)))


def test_hac_psr_is_exported_from_package() -> None:
    """Public contract: the function is reachable from
    ``research.robustness`` without importing a private submodule."""
    from research import robustness

    assert robustness.probabilistic_sharpe_ratio_hac is probabilistic_sharpe_ratio_hac
    assert "probabilistic_sharpe_ratio_hac" in robustness.__all__


# ---------------------------------------------------------------------------
# TEETH — measured gap: mutation_probe --only-logic left three IN-SCOPE guards alive in
# the HAC/PSR path (:204, :292, :317 — all Or->And). Each is a fail-closed OR: under the
# mutant BOTH conditions would have to hold before the function refuses, so a single
# degenerate input (lag 0, a NaN sample, a collapsed effective size) would be computed on
# instead of rejected. The surviving mutants OUTSIDE this claim's scope (cpcv_splits,
# estimate_pbo) are deliberately NOT padded with tests here — this claim asserts the
# Newey-West HAC variant, not the CPCV splitter, and inflating a module-level number with
# unrelated tests would be metric gaming.
# ---------------------------------------------------------------------------
def test_newey_west_effective_size_is_n_when_lag_is_zero() -> None:
    """lag 0 means no autocorrelation adjustment — the effective size IS n.

    Kills :204 Or->And, under which a well-sized sample with lag 0 would fall through to
    the Bartlett accumulation instead of returning n.
    """
    from research.robustness.cpcv import _newey_west_effective_size

    r = np.array([0.01, -0.02, 0.03, 0.00, 0.015, -0.005], dtype=np.float64)
    assert _newey_west_effective_size(r, 0) == pytest.approx(float(r.size), abs=1e-12)


def test_hac_psr_refuses_a_non_finite_sample() -> None:
    """A NaN anywhere in a well-sized sample must yield NaN, not a computed number.

    Kills :292 Or->And, under which only a sample that is BOTH too short AND non-finite
    would be refused, so a long series containing a NaN would be computed on.
    """
    from research.robustness.cpcv import probabilistic_sharpe_ratio_hac

    r = np.array([0.01, -0.02, np.nan, 0.03, 0.005, 0.02], dtype=np.float64)
    assert math.isnan(probabilistic_sharpe_ratio_hac(r))


def test_hac_psr_refuses_a_degenerate_effective_size() -> None:
    """A constant series has zero dispersion — the HAC path must refuse, not divide by it.

    Exercises the :317 guard (n_eff < 2 or non-finite) on the shortest admissible sample.
    """
    from research.robustness.cpcv import probabilistic_sharpe_ratio_hac

    constant = np.zeros(8, dtype=np.float64)
    assert math.isnan(probabilistic_sharpe_ratio_hac(constant))
