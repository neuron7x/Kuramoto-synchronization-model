# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for cimini_squartini.py (X-10R C01)."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.cimini_squartini import (
    HiddenFitness,
    fit_cimini_squartini,
    p_link,
)
from research.reconstruction.density_calibration import inferred_density


def _heterogeneous_marginals(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    s_out = rng.lognormal(mean=10.0, sigma=1.5, size=n)
    # Match totals so conservation of mass holds.
    s_in = s_out.copy()
    rng.shuffle(s_in)
    return s_out, s_in


def test_p_link_diagonal_is_zero() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([0.5, 0.7, 1.0])
    p = p_link(x, y, z=1.5)
    assert np.allclose(np.diag(p), 0.0)


def test_p_link_in_unit_interval() -> None:
    rng = np.random.default_rng(7)
    n = 30
    x = rng.uniform(0.1, 5.0, size=n)
    y = rng.uniform(0.1, 5.0, size=n)
    for z in (0.001, 0.1, 1.0, 10.0, 1000.0):
        p = p_link(x, y, z)
        assert np.all(p >= 0.0)
        assert np.all(p <= 1.0)


def test_p_link_rejects_negative_z() -> None:
    with pytest.raises(ValueError):
        p_link(np.array([1.0, 2.0]), np.array([1.0, 2.0]), z=-0.1)


def test_p_link_rejects_negative_fitness() -> None:
    with pytest.raises(ValueError):
        p_link(np.array([-1.0, 2.0]), np.array([1.0, 2.0]), z=1.0)


def test_p_link_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError):
        p_link(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0]), z=1.0)


def test_fit_returns_hidden_fitness_with_unit_mean() -> None:
    s_out, s_in = _heterogeneous_marginals(50, seed=1)
    fit = fit_cimini_squartini(s_out, s_in, target_density=0.05)
    assert isinstance(fit, HiddenFitness)
    assert np.isclose(fit.x.mean(), 1.0, atol=1e-12)
    assert np.isclose(fit.y.mean(), 1.0, atol=1e-12)


def test_fit_calibrates_density_to_target() -> None:
    s_out, s_in = _heterogeneous_marginals(80, seed=2)
    for d in (0.03, 0.05, 0.08, 0.12):
        fit = fit_cimini_squartini(s_out, s_in, target_density=d)
        d_inferred = inferred_density(fit)
        assert abs(d_inferred - d) < 1e-3, f"target {d}, got {d_inferred}"


def test_fit_density_is_monotone_in_z() -> None:
    """Higher z ⇒ higher density (saturating to 1)."""
    s_out, s_in = _heterogeneous_marginals(40, seed=3)
    densities = []
    for d in (0.02, 0.05, 0.10, 0.20, 0.35):
        fit = fit_cimini_squartini(s_out, s_in, target_density=d)
        densities.append(fit.z)
    diffs = np.diff(densities)
    assert np.all(diffs > 0), f"z should increase with target_density; got {densities}"


def test_fit_rejects_negative_marginals() -> None:
    with pytest.raises(ValueError):
        fit_cimini_squartini(
            np.array([1.0, -2.0, 3.0]), np.array([1.0, 2.0, 3.0]), target_density=0.05
        )


def test_fit_rejects_target_density_out_of_range() -> None:
    s = np.array([1.0, 2.0, 3.0])
    for d in (0.0, 1.0, 2.0, -0.1):
        with pytest.raises(ValueError):
            fit_cimini_squartini(s, s, target_density=d)


def test_fit_rejects_short_input() -> None:
    with pytest.raises(ValueError):
        fit_cimini_squartini(np.array([1.0]), np.array([1.0]), target_density=0.5)


def test_fit_is_deterministic() -> None:
    """Same marginals + same target ⇒ identical fitness."""
    s_out, s_in = _heterogeneous_marginals(60, seed=4)
    fit_a = fit_cimini_squartini(s_out, s_in, target_density=0.07)
    fit_b = fit_cimini_squartini(s_out, s_in, target_density=0.07)
    np.testing.assert_array_equal(fit_a.x, fit_b.x)
    np.testing.assert_array_equal(fit_a.y, fit_b.y)
    assert fit_a.z == fit_b.z
