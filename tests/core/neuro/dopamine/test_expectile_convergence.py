# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The expectile learner must only ever return a *converged* fixed point.

Two guarantees are locked in here:
  1. The returned value satisfies the asymmetric-least-squares stationarity
     condition  tau*Σ(x-m)_+ = (1-tau)*Σ(m-x)_-  to numerical tolerance — this is
     exactly the fixed-point the IRLS solves, so it can only hold if the iteration
     actually converged (a fabricated non-converged iterate would violate it).
  2. When the iteration cannot converge within its cap, the function fails closed
     with a ValueError instead of silently returning the last iterate.
"""
from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import geosync.core.neuro.dopamine.expectile_value as expectile_mod
from geosync.core.neuro.dopamine.expectile_value import expectile_of_samples


def _stationarity_residual(samples: list[float], m: float, tau: float) -> float:
    x = np.asarray(samples, dtype=np.float64)
    upper = x >= m
    return float(tau * np.sum(x[upper] - m) + (1.0 - tau) * np.sum(x[~upper] - m))


@given(
    data=st.lists(
        st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=64,
    ),
    tau=st.floats(min_value=0.05, max_value=0.95),
)
@settings(max_examples=200)
def test_returned_value_satisfies_stationarity(data: list[float], tau: float) -> None:
    m = expectile_of_samples(data, tau)
    residual = _stationarity_residual(data, m, tau)
    scale = max(1.0, float(np.max(np.abs(np.asarray(data)))))
    # Tolerance scales with problem magnitude and sample count (residual is a sum).
    assert abs(residual) <= 1e-6 * scale * len(data)


def test_tau_one_half_recovers_the_mean() -> None:
    data = [0.0, 1.0, 2.0, 3.0, 10.0]
    assert expectile_of_samples(data, 0.5) == pytest.approx(float(np.mean(data)), rel=1e-9)


def test_asymmetric_tau_orders_below_and_above_the_mean() -> None:
    data = [0.0, 1.0, 2.0, 3.0, 10.0]
    low = expectile_of_samples(data, 0.1)
    mid = expectile_of_samples(data, 0.5)
    high = expectile_of_samples(data, 0.9)
    assert low < mid < high


def test_non_convergence_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Starve the iteration so it cannot meet the tolerance. An asymmetric tau on
    # spread data needs several Newton steps, so a single-iteration cap cannot
    # converge — the function must raise, never return the seed iterate.
    monkeypatch.setattr(expectile_mod, "_IRLS_MAX_ITER", 1)
    with pytest.raises(ValueError, match="did not converge"):
        expectile_of_samples([0.0, 1.0, 2.0, 3.0, 100.0], 0.05)


def test_degenerate_all_equal_samples_converge_immediately() -> None:
    # All-equal samples are a valid stationary point at that value for every tau.
    assert expectile_of_samples([4.0, 4.0, 4.0], 0.3) == pytest.approx(4.0)
