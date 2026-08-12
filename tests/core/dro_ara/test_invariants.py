# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical invariants of the DRO-ARA v7 engine.

These tests pin the derivation contract ``gamma = 2·H + 1`` (INV-DRO1)
and validate the fail-closed posture against degenerate inputs
(INV-DRO5). They also cover the bounded-Lipschitz risk scalar
contract (INV-DRO2), the regime-validity gate (INV-DRO3), and the
LONG-signal pre-conditions (INV-DRO4). They are pure unit tests: no
stochastic generators, no external data, no non-determinism.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.dro_ara import (
    H_CRITICAL,
    H_DRIFT,
    R2_MIN,
    RS_LONG_THRESH,
    Regime,
    classify,
    derive_gamma,
    geosync_observe,
    risk_scalar,
)


def test_gamma_is_derived_from_H() -> None:
    """INV-DRO1: γ = 2·H + 1 to float precision."""
    rng = np.random.default_rng(42)
    price = 100.0 + np.cumsum(rng.normal(0, 1, size=2048))
    gamma, H, r2 = derive_gamma(price)
    assert abs(gamma - (2 * H + 1)) < 1e-5
    assert 0.01 <= H <= 0.99
    assert 0.0 <= r2 <= 1.0


def test_risk_scalar_bounds() -> None:
    """INV-DRO2: rs = max(0, 1 − |γ − 1|) ∈ [0, 1] (Lipschitz-1 in γ)."""
    assert risk_scalar(1.0) == 1.0
    assert risk_scalar(0.0) == 0.0
    assert risk_scalar(2.0) == 0.0
    assert 0.0 <= risk_scalar(1.4) <= 1.0
    assert risk_scalar(-5.0) == 0.0


def test_classify_invalid_when_not_stationary() -> None:
    """INV-DRO3: regime == INVALID iff (¬stationary ∨ R² < R2_MIN)."""
    assert classify(gamma=1.8, r2=0.95, stationary=False) is Regime.INVALID


def test_classify_invalid_when_r2_below_gate() -> None:
    """INV-DRO3: R² gate (R2_MIN = 0.90) rejects under-fit ADF."""
    assert classify(gamma=1.8, r2=R2_MIN - 0.01, stationary=True) is Regime.INVALID


def test_classify_critical_boundary() -> None:
    """INV-DRO4 supporting test: CRITICAL region reachable below H_CRITICAL."""
    gamma_critical = 2 * (H_CRITICAL - 0.01) + 1
    assert classify(gamma=gamma_critical, r2=0.95, stationary=True) is Regime.CRITICAL


def test_classify_drift_boundary() -> None:
    """INV-DRO4 supporting test: DRIFT regime never satisfies LONG."""
    gamma_drift = 2 * (H_DRIFT + 0.01) + 1
    assert classify(gamma=gamma_drift, r2=0.95, stationary=True) is Regime.DRIFT


def test_classify_transition() -> None:
    """INV-DRO4 supporting test: TRANSITION at H = 0.5, blocks LONG."""
    gamma_mid = 2 * 0.50 + 1
    assert classify(gamma=gamma_mid, r2=0.95, stationary=True) is Regime.TRANSITION


def test_rs_long_threshold_constant() -> None:
    """INV-DRO4: LONG signal requires CRITICAL ∧ rs > 0.33."""
    assert RS_LONG_THRESH == 0.33


def test_observe_rejects_nan() -> None:
    """INV-DRO5: NaN input → ValueError, no silent numeric repair."""
    price = np.full(1024, 100.0)
    price[500] = np.nan
    with pytest.raises(ValueError, match="NaN/Inf"):
        geosync_observe(price)


def test_observe_rejects_inf() -> None:
    """INV-DRO5: Inf input → ValueError, no silent numeric repair."""
    price = np.full(1024, 100.0)
    price[500] = np.inf
    with pytest.raises(ValueError, match="NaN/Inf"):
        geosync_observe(price)


def test_observe_rejects_constant() -> None:
    """INV-DRO5: constant input → ValueError (rank-deficient)."""
    with pytest.raises(ValueError, match="constant"):
        geosync_observe(np.full(1024, 100.0))


def test_observe_rejects_too_short() -> None:
    """INV-DRO5: short window → ValueError (insufficient lag fit)."""
    with pytest.raises(ValueError, match="need"):
        geosync_observe(np.arange(10, dtype=np.float64))


def test_observe_rejects_2d() -> None:
    """INV-DRO5: rank > 1 input → ValueError (1-D required)."""
    with pytest.raises(ValueError, match="1-D required"):
        geosync_observe(np.zeros((100, 100)))


def test_observe_deterministic() -> None:
    rng = np.random.default_rng(17)
    price = 100.0 + np.cumsum(rng.normal(0, 1, size=1024))
    a = geosync_observe(price)
    b = geosync_observe(price)
    assert a == b


def test_inv_dro3_tightening_post_rfc_ou_stationary_rate() -> None:
    """INV-DRO3 semantic tightening (PR #345 RFC): ADF on log-returns.

    Before the RFC, ADF ran on raw prices → near-tautology that declared
    virtually every I(1) asset non-stationary. After the RFC, stationarity
    is a non-trivial property of returns. For a *true* stationary process
    (Ornstein–Uhlenbeck), INV-DRO3 must be satisfied on the vast majority
    of seeds: > 50 % stationary rate across independent draws.

    If this test regresses, the convention has likely been reverted.
    """
    rng_seeds = list(range(30))
    stationary_count = 0
    for seed in rng_seeds:
        r = np.random.default_rng(seed)
        n = 1024
        mu, theta, sigma = 100.0, 0.08, 0.6
        x = np.empty(n, dtype=np.float64)
        x[0] = mu
        for t in range(1, n):
            x[t] = x[t - 1] + theta * (mu - x[t - 1]) + sigma * r.normal()
        out = geosync_observe(x)
        if out["stationary"] is True:
            stationary_count += 1
    rate = stationary_count / len(rng_seeds)
    assert rate > 0.50, (
        f"INV-DRO3 tightening regressed: OU stationary rate = {rate:.2f} "
        f"({stationary_count}/{len(rng_seeds)}), expected > 0.50. "
        f"Convention may have been reverted to ADF-on-raw-prices."
    )
