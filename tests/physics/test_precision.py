# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for the numerical_drift_bound law."""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.physics.precision import (
    assert_numerical_stability,
    deterministic_hash,
    drift_bound,
    stable_sum,
    ulp_distance,
)


def _seeded_run(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(size=256))


def test_seeded_hash_is_stable() -> None:
    """Positive witness: a seeded pipeline hashes identically across repeats."""
    assert deterministic_hash(_seeded_run(123)) == deterministic_hash(_seeded_run(123))


def test_ill_conditioned_input_is_rejected() -> None:
    """Negative control: a near-singular matrix exceeds the conditioning ceiling."""
    ill = np.array([[1.0, 1.0], [1.0, 1.0 + 1e-14]])
    with pytest.raises(ValueError, match="NUMERICAL-STABILITY VIOLATED"):
        assert_numerical_stability(ill, kappa_max=1e8)


def test_well_conditioned_input_passes() -> None:
    """A well-conditioned matrix passes and returns a finite condition number."""
    cond = assert_numerical_stability(np.eye(4) * 2.0, kappa_max=1e8)
    assert cond == 1.0


def test_nan_inf_is_rejected() -> None:
    """NaN/Inf in the matrix fails closed before conditioning is even computed."""
    with pytest.raises(ValueError, match="NaN/Inf"):
        assert_numerical_stability(np.array([[1.0, np.nan], [0.0, 1.0]]), kappa_max=1e8)
    with pytest.raises(ValueError, match="NaN/Inf"):
        deterministic_hash(np.array([1.0, np.inf]))


def test_unstable_summation_is_detected() -> None:
    """Compensated summation differs from a naive sum on a catastrophic cancellation."""
    values = np.array([1e16, 1.0, -1e16])
    naive = float(np.asarray(values).sum())  # loses the 1.0
    stable = stable_sum(values)  # recovers 1.0
    assert stable == 1.0
    assert drift_bound(stable, naive) > 0


def test_tolerance_abuse_fails() -> None:
    """A non-positive conditioning ceiling (tolerance abuse) is rejected."""
    with pytest.raises(ValueError, match="kappa_max must be finite and > 0"):
        assert_numerical_stability(np.eye(2), kappa_max=0.0)


def test_ulp_distance_zero_iff_identical() -> None:
    """ULP distance is exactly 0 for bit-identical values, positive otherwise."""
    assert ulp_distance(1.0, 1.0) == 0
    assert ulp_distance(1.0, np.nextafter(1.0, 2.0)) == 1


def test_ulp_distance_rejects_nonfinite_and_orders_negatives() -> None:
    """`not (isfinite(a) and isfinite(b))` fail-closes; `_ordered_int` handles negatives.

    Under `And -> Or` the finite guard fires only when BOTH inputs are non-finite, so a single
    NaN slips through into ULP arithmetic. Under `Lt -> GtE` in the ordering map, negative
    doubles take the positive branch and adjacent negatives no longer measure 1 ULP apart.
    """
    with pytest.raises(ValueError, match="finite"):
        ulp_distance(float("nan"), 1.0)
    with pytest.raises(ValueError, match="finite"):
        ulp_distance(1.0, float("inf"))

    # Adjacent negative doubles are exactly 1 ULP apart; the ordering must be monotone.
    assert ulp_distance(-1.0, math.nextafter(-1.0, 0.0)) == 1
    assert ulp_distance(-2.5, -2.5) == 0
    assert ulp_distance(-1.0, 1.0) == ulp_distance(1.0, -1.0)
    # The ordering is monotone across zero, so ULP distance is additive along it. Under the
    # mutated `bits >= 0`, negatives map to raw (large) bit values and additivity across zero
    # breaks.
    assert ulp_distance(-1.0, 1.0) == ulp_distance(-1.0, 0.0) + ulp_distance(0.0, 1.0)
