# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strike R4 — Phase 0c (0.05 < p < 0.95) rejects collapse, not powerlessness.

Attack
------
A uniform-p degenerate null passes ``0.05 < p_empirical < 0.95`` while
having zero discriminability. ``phase0c_power_calibration`` injects a
known δ shift and measures detection rate; this test exercises that
helper across δ ∈ {0, 0.1σ, 0.5σ} and asserts the expected ordering and
monotonicity (zero δ < small δ < large δ).

Verdict (from Phase A audit)
---------------------------
R4 was UNTESTED. After the Phase-C patch
``phase0c_power_calibration`` is added; this test asserts the new
helper is monotonic in injected effect size and produces a meaningful
detection rate.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002g_phase0_verification import (
    phase0c_power_calibration,
)

# Power calibration over many δ values — gate behind `slow` so
# python-fast-tests stays under its 20-min cap.
pytestmark = pytest.mark.slow


def test_R4_power_calibration_monotonic_in_delta() -> None:
    """Detection rate must increase (weakly) with effect size."""
    rng = np.random.default_rng(0)
    p = rng.normal(0, 1, 50)
    n = rng.normal(0, 1, 50)
    rate_null = phase0c_power_calibration(
        p, n, delta_over_sigma=0.0, n_replicates=50, n_shuffles=200, rng_seed=11
    )
    rate_small = phase0c_power_calibration(
        p, n, delta_over_sigma=0.1, n_replicates=50, n_shuffles=200, rng_seed=11
    )
    rate_large = phase0c_power_calibration(
        p, n, delta_over_sigma=0.5, n_replicates=50, n_shuffles=200, rng_seed=11
    )
    # Null detection rate must hover near α = 0.05 (Type-I error
    # nominal coverage). We allow up to 0.20 to absorb finite-replicate noise.
    assert rate_null < 0.20, (
        f"R4 VIOLATED: detection rate at δ=0 is {rate_null:.3f} >> α=0.05. "
        "The permutation test does not control Type-I error."
    )
    # Monotonicity in injected effect.
    assert rate_null <= rate_small + 1e-9, (
        f"R4 VIOLATED: detection rate non-monotonic (null > small): "
        f"{rate_null:.3f} > {rate_small:.3f}"
    )
    assert rate_small <= rate_large + 1e-9, (
        f"R4 VIOLATED: detection rate non-monotonic (small > large): "
        f"{rate_small:.3f} > {rate_large:.3f}"
    )


def test_R4_power_calibration_strong_signal_above_floor() -> None:
    """Large effect (δ=0.5σ) must clear the 0.5 detection-rate floor."""
    rng = np.random.default_rng(0)
    p = rng.normal(0, 1, 50)
    n = rng.normal(0, 1, 50)
    rate = phase0c_power_calibration(
        p, n, delta_over_sigma=0.5, n_replicates=80, n_shuffles=200, rng_seed=7
    )
    assert rate > 0.5, (
        f"R4 VIOLATED: detection rate at δ=0.5σ is {rate:.3f} ≤ 0.5 — "
        "phase0c is powerless even for medium effects, so its "
        "PASS verdict cannot certify discriminability."
    )


def test_R4_power_calibration_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    p = rng.normal(0, 1, 50)
    n = rng.normal(0, 1, 50)
    a = phase0c_power_calibration(
        p, n, delta_over_sigma=0.1, n_replicates=30, n_shuffles=100, rng_seed=42
    )
    b = phase0c_power_calibration(
        p, n, delta_over_sigma=0.1, n_replicates=30, n_shuffles=100, rng_seed=42
    )
    assert a == b, f"R4 VIOLATED: power calibration not deterministic: {a} vs {b}"
