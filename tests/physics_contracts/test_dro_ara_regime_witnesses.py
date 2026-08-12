# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the DRO-ARA regime-observer laws in the catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real ``core.dro_ara.engine``, deriving every tolerance
from the law. Three previously-unwitnessed laws gain witnesses:

* ``dro_ara.gamma_derivation`` — γ is derived from the Hurst exponent as
  γ = 2H + 1, never assigned independently (INV-DRO1).
* ``dro_ara.risk_scalar_bounds`` — rs(γ) = max(0, 1 − |γ − 1|) is bounded in
  [0, 1] and Lipschitz-1 in γ (INV-DRO2).
* ``dro_ara.fail_closed_input`` — degenerate input raises ValueError with no
  silent numeric repair (INV-DRO5).

Nothing here is a market claim. These are regime-estimator contract facts.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.dro_ara.engine import derive_gamma, risk_scalar
from physics_contracts.law import law

# Catalog ``dro_ara.gamma_derivation`` tolerance: |γ − (2H + 1)| < 1e-5.
GAMMA_TOLERANCE = 1e-5
# rs is a strict definitional bound; only float round-off is allowed.
RISK_EPS = 1e-12
# Lipschitz-1 slack for the finite-difference estimate of |Δrs/Δγ|.
LIPSCHITZ_SLACK = 1e-9


@law("dro_ara.gamma_derivation", n_series=40, series_length=128)
def test_gamma_is_derived_as_two_hurst_plus_one() -> None:
    """INV-DRO1: γ = 2H + 1 to float precision for every admissible series.

    derive_gamma returns (γ, H, …); the witness checks that γ is exactly the
    Peng-relation function of the Hurst exponent the same call computed, so γ can
    never be assigned independently of H. Swept over random price series.
    """
    n_series = 40
    series_length = 128
    rng = np.random.default_rng(seed=0)
    worst_error = 0.0
    for _ in range(n_series):
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=series_length)))
        gamma, hurst = derive_gamma(prices)[:2]
        worst_error = max(worst_error, abs(gamma - (2.0 * hurst + 1.0)))
    assert worst_error <= GAMMA_TOLERANCE, (
        "INV-DRO1 violated: observed worst |γ − (2H + 1)| = "
        f"{worst_error:.2e} must be ≤ {GAMMA_TOLERANCE:.0e} over n_series={n_series} "
        "with seed=0; γ must be derived from H, never assigned independently"
    )


@law("dro_ara.risk_scalar_bounds", n_points=2000, gamma_range=8.0)
def test_risk_scalar_is_bounded_and_lipschitz() -> None:
    """INV-DRO2: rs(γ) = max(0, 1 − |γ − 1|) stays in [0, 1] and is Lipschitz-1.

    The risk scalar is a definitional bound, not a numerical estimate: it must
    never leave [0, 1] for any real γ, and its slope magnitude must never exceed
    1. The witness sweeps γ over a wide grid and tracks the worst excursions and
    the maximum finite-difference slope.
    """
    n_points = 2000
    gamma_range = 8.0
    gammas = np.linspace(-gamma_range, gamma_range, n_points)
    rs = np.array([risk_scalar(float(g)) for g in gammas])
    worst_low = float(rs.min())
    worst_high = float(rs.max())
    max_slope = float(np.max(np.abs(np.diff(rs)) / np.abs(np.diff(gammas))))
    assert worst_low >= 0.0 - RISK_EPS, (
        "INV-DRO2 violated: observed min rs = "
        f"{worst_low:.6f} must be ≥ 0 (tolerance {RISK_EPS:.0e}) over n_points={n_points} "
        f"with gamma_range=±{gamma_range}; rs is bounded below by 0"
    )
    assert worst_high <= 1.0 + RISK_EPS, (
        "INV-DRO2 violated: observed max rs = "
        f"{worst_high:.6f} must be ≤ 1 (tolerance {RISK_EPS:.0e}) over n_points={n_points} "
        f"with gamma_range=±{gamma_range}; rs is bounded above by 1"
    )
    assert max_slope <= 1.0 + LIPSCHITZ_SLACK, (
        "INV-DRO2 violated: observed max |Δrs/Δγ| = "
        f"{max_slope:.6f} must be ≤ 1 (tolerance {LIPSCHITZ_SLACK:.0e}) over "
        f"n_points={n_points} with gamma_range=±{gamma_range}; rs must be Lipschitz-1 in γ"
    )


@law("dro_ara.fail_closed_input", n_clean_controls=10, series_length=96)
def test_degenerate_input_fails_closed() -> None:
    """INV-DRO5: degenerate input raises ValueError; clean input does not.

    NaN, Inf, constant, too-short, and 2-D inputs must each raise ValueError with
    no fall-through to the numeric path. A clean control series confirms the gate
    is not simply rejecting everything (it accepts admissible input).
    """
    series_length = 96
    rng = np.random.default_rng(seed=1)
    clean = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=series_length)))
    degenerate = {
        "nan": np.concatenate([clean[:40], np.array([np.nan]), clean[40:]]),
        "inf": np.concatenate([clean[:40], np.array([np.inf]), clean[40:]]),
        "constant": np.full(series_length, 100.0),
        "too_short": np.array([100.0, 101.0, 102.0]),
        "two_dim": np.ones((2, series_length)),
    }
    for name, bad in degenerate.items():
        with pytest.raises(ValueError):
            derive_gamma(bad)
    # Negative control: admissible input must NOT raise (gate is not vacuous).
    n_clean_controls = 10
    accepted = 0
    for _ in range(n_clean_controls):
        series = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=series_length)))
        derive_gamma(series)
        accepted += 1
    assert accepted == n_clean_controls, (
        "INV-DRO5 violated: observed accepted = "
        f"{accepted} of {n_clean_controls} clean series must all be accepted with "
        "seed=1; the fail-closed gate must not reject admissible input"
    )
