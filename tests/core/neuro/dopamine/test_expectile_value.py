# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant tests for the expectile-ensemble dopamine learner."""

from __future__ import annotations

import math
import warnings
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pytest

from geosync.core.neuro.dopamine.expectile_value import (
    ExpectileChannel,
    ExpectileEnsembleValue,
    expectile_of_samples,
)

FloatArray = npt.NDArray[np.float64]


@pytest.mark.parametrize("tau", [0.05, 0.25, 0.5, 0.75, 0.95])
def test_tau_recovered_from_asymmetric_rates(tau: float) -> None:
    ch = ExpectileChannel(tau=tau, learning_rate=0.1)
    assert abs(ch.recovered_tau() - tau) < 1e-12


def test_channel_normalizes_validated_scalar_fields() -> None:
    ch = ExpectileChannel(
        tau=cast(Any, "0.5"),
        learning_rate=cast(Any, "0.1"),
    )
    assert isinstance(ch.tau, float)
    assert isinstance(ch.learning_rate, float)
    assert ch.alpha_pos == pytest.approx(0.05)
    assert ch.recovered_tau() == pytest.approx(0.5)


def test_half_expectile_equals_mean() -> None:
    rng = np.random.default_rng(0)
    samples = rng.normal(2.0, 3.0, size=5000)
    assert abs(expectile_of_samples(samples, 0.5) - float(samples.mean())) < 1e-9


def test_expectile_solver_handles_large_finite_constant_samples() -> None:
    learned = expectile_of_samples([1.0e308, 1.0e308, 1.0e308], 0.5)
    assert math.isfinite(learned)
    assert learned == pytest.approx(1.0e308)


def test_symmetric_channel_recovers_canonical_mean() -> None:
    ens = ExpectileEnsembleValue.symmetric(n_channels=1, learning_rate=0.02)
    rng = np.random.default_rng(1)
    samples = rng.normal(1.0, 0.5, size=20000)
    for sample in samples:
        ens.observe_return(float(sample))
    assert abs(ens.canonical_value() - float(samples.mean())) < 0.05


def test_td_target_channel_tracks_scalar_anchor() -> None:
    ens = ExpectileEnsembleValue.symmetric(n_channels=1, learning_rate=0.05)
    reward, next_value, gamma = 0.7, 0.4, 0.9
    for _ in range(3000):
        ens.observe_td_target(reward, next_value, gamma)
    assert abs(ens.canonical_value() - (reward + gamma * next_value)) < 1e-6


def test_expectile_curve_is_monotone() -> None:
    ens = ExpectileEnsembleValue.spread(n_channels=9, learning_rate=0.02)
    rng = np.random.default_rng(2)
    samples = rng.gamma(shape=2.0, scale=1.5, size=20000)
    for sample in samples:
        ens.observe_return(float(sample))
    taus, values = ens.expectile_curve()
    assert np.all(np.diff(taus) > 0)
    assert np.all(np.diff(values) >= -1e-9)
    assert ens.dispersion() > 0.0


def test_values_bounded_by_target_hull() -> None:
    ens = ExpectileEnsembleValue.spread(n_channels=7, learning_rate=0.3)
    lo, hi = -2.0, 5.0
    rng = np.random.default_rng(3)
    samples = rng.uniform(lo, hi, size=5000)
    for sample in samples:
        ens.observe_return(float(sample))
        vals = ens.values
        assert np.all(vals >= lo - 1e-9)
        assert np.all(vals <= hi + 1e-9)


@pytest.mark.parametrize("tau", [0.1, 0.3, 0.5, 0.7, 0.9])
def test_analytic_expectile_is_a_true_fixed_point(tau: float) -> None:
    rng = np.random.default_rng(int(tau * 100))
    samples = rng.normal(0.0, 1.0, size=400)
    e = expectile_of_samples(samples, tau)
    weights = np.where(samples > e, tau, 1.0 - tau)
    residual = float(np.sum(weights * (samples - e)))
    assert abs(residual) < 1e-9


@pytest.mark.parametrize("tau", [0.1, 0.3, 0.7, 0.9])
def test_quantile_substitution_does_not_satisfy_expectile_residual(tau: float) -> None:
    rng = np.random.default_rng(int(tau * 1000))
    samples = rng.normal(0.0, 1.0, size=800)
    fake_quantile = float(np.quantile(samples, tau))
    weights = np.where(samples > fake_quantile, tau, 1.0 - tau)
    residual = abs(float(np.sum(weights * (samples - fake_quantile))))
    assert residual > 1.0


@pytest.mark.parametrize("tau", [0.1, 0.3, 0.7, 0.9])
def test_online_learner_converges_to_analytic_expectile(tau: float) -> None:
    rng = np.random.default_rng(int(tau * 100))
    targets = rng.normal(0.0, 1.0, size=400)
    truth = expectile_of_samples(targets, tau)
    ens = ExpectileEnsembleValue.from_levels([tau], learning_rate=0.02)
    tail: list[float] = []
    for period in range(300):
        for target in targets:
            ens.observe_return(float(target))
        if period >= 200:
            tail.append(float(ens.values[0]))
    assert abs(float(np.mean(tail)) - truth) < 0.05


def test_risk_adjusted_value_orders_by_tau() -> None:
    ens = ExpectileEnsembleValue.spread(n_channels=9, learning_rate=0.02)
    rng = np.random.default_rng(7)
    samples = rng.normal(0.0, 1.0, size=15000)
    for sample in samples:
        ens.observe_return(float(sample))
    assert ens.risk_adjusted_value(0.1) < ens.canonical_value()
    assert ens.canonical_value() < ens.risk_adjusted_value(0.9)


def test_swapped_alpha_direction_reverses_ordering() -> None:
    rng = np.random.default_rng(17)
    samples = rng.normal(0.0, 1.0, size=20000)

    def run_direction(tau: float, *, swapped: bool) -> float:
        value = 0.0
        learning_rate = 0.02
        alpha_pos = learning_rate * tau
        alpha_neg = learning_rate * (1.0 - tau)
        if swapped:
            alpha_pos, alpha_neg = alpha_neg, alpha_pos
        for sample in samples:
            delta = float(sample) - value
            value += (alpha_pos if delta > 0.0 else alpha_neg) * delta
        return value

    assert run_direction(0.1, swapped=False) < run_direction(0.9, swapped=False)
    assert run_direction(0.1, swapped=True) > run_direction(0.9, swapped=True)


def test_constant_stream_collapses_dispersion() -> None:
    ens = ExpectileEnsembleValue.spread(n_channels=9, learning_rate=0.05)
    for _ in range(6000):
        ens.observe_return(3.25)
    assert ens.dispersion() <= 1e-9


def test_extreme_tau_stability_and_hull_bounds() -> None:
    ens = ExpectileEnsembleValue.from_levels(
        [0.01, 0.05, 0.95, 0.99],
        learning_rate=0.01,
    )
    rng = np.random.default_rng(23)
    samples = rng.uniform(-4.0, 7.0, size=12000)
    for sample in samples:
        ens.observe_return(float(sample))
    values = ens.values
    assert np.all(np.isfinite(values))
    assert np.all(values >= float(samples.min()) - 1e-9)
    assert np.all(values <= float(samples.max()) + 1e-9)
    assert np.all(np.diff(values) >= -1e-9)


@pytest.mark.parametrize("bad_tau", [0.0, 1.0, -0.1, 1.5, math.nan, math.inf])
def test_channel_rejects_bad_tau(bad_tau: float) -> None:
    with pytest.raises(ValueError):
        ExpectileChannel(tau=bad_tau, learning_rate=0.1)


@pytest.mark.parametrize("bad_eta", [0.0, -0.1, 1.5, math.nan])
def test_channel_rejects_bad_learning_rate(bad_eta: float) -> None:
    with pytest.raises(ValueError):
        ExpectileChannel(tau=0.5, learning_rate=bad_eta)


def test_ensemble_rejects_empty_and_duplicate_levels() -> None:
    empty_channels: list[ExpectileChannel] = []
    with pytest.raises(ValueError):
        ExpectileEnsembleValue(empty_channels)
    with pytest.raises(ValueError):
        ExpectileEnsembleValue.from_levels([0.5, 0.5])


def test_observe_rejects_nonfinite_and_bad_gamma() -> None:
    ens = ExpectileEnsembleValue.symmetric()
    with pytest.raises(ValueError):
        ens.observe_return(math.nan)
    with pytest.raises(ValueError):
        ens.observe_td_target(1.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        ens.observe_td_target(1.0, 1.0, 1.5)


def test_observe_return_rejects_overflowed_delta_without_mutating_state() -> None:
    ens = ExpectileEnsembleValue(
        [ExpectileChannel(tau=0.5, learning_rate=0.05)],
        init_value=-1.0e308,
    )
    with pytest.raises(ValueError, match="distributional deltas must be finite"):
        ens.observe_return(1.0e308)
    assert ens.n_updates == 0
    assert ens.values[0] == pytest.approx(-1.0e308)


def test_observe_return_overflow_leaks_no_runtime_warning() -> None:
    # regression: overflow must be a deterministic contract error, never a leaked
    # numpy RuntimeWarning (guarded by np.errstate in observe_return).
    ens = ExpectileEnsembleValue(
        [ExpectileChannel(tau=0.5, learning_rate=0.05)],
        init_value=-1.0e308,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(ValueError, match="distributional deltas must be finite"):
            ens.observe_return(1.0e308)


def test_observe_td_target_rejects_overflowed_target() -> None:
    ens = ExpectileEnsembleValue.symmetric()
    with pytest.raises(ValueError, match="td_target must be finite"):
        ens.observe_td_target(1.0e308, 1.0e308, 1.0)
    assert ens.n_updates == 0


def test_expectile_solver_rejects_empty_and_bad_tau() -> None:
    with pytest.raises(ValueError):
        expectile_of_samples([], 0.5)
    with pytest.raises(ValueError):
        expectile_of_samples([1.0, 2.0], 0.0)
    with pytest.raises(ValueError):
        expectile_of_samples([1.0, math.inf], 0.5)


def test_determinism_bit_identical() -> None:
    rng = np.random.default_rng(11)
    samples = rng.normal(0.0, 1.0, size=2000)

    def run() -> FloatArray:
        ens = ExpectileEnsembleValue.spread(n_channels=5, learning_rate=0.03)
        for sample in samples:
            ens.observe_return(float(sample))
        return ens.values

    a, b = run(), run()
    assert np.array_equal(a, b), "estimator must be deterministic"
