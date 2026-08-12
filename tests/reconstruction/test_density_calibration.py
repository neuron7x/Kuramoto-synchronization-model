# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for density_calibration.py + GATE_3 enforcement."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.density_calibration import (
    DENSITY_LOWER,
    DENSITY_UPPER,
    calibrate_density_z,
    density_bound_passes,
    inferred_density,
)


def _marginals(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    s = rng.lognormal(mean=10.0, sigma=1.5, size=n)
    s_in = s.copy()
    rng.shuffle(s_in)
    return s, s_in


def test_density_bound_lower_inclusive() -> None:
    assert density_bound_passes(DENSITY_LOWER) is True


def test_density_bound_upper_inclusive() -> None:
    assert density_bound_passes(DENSITY_UPPER) is True


def test_density_bound_below_rejected() -> None:
    assert density_bound_passes(DENSITY_LOWER - 1e-9) is False


def test_density_bound_above_rejected() -> None:
    assert density_bound_passes(DENSITY_UPPER + 1e-9) is False


def test_density_bound_zero_rejected() -> None:
    assert density_bound_passes(0.0) is False


def test_density_bound_one_rejected() -> None:
    assert density_bound_passes(1.0) is False


def test_calibrate_matches_target() -> None:
    s_out, s_in = _marginals(50, seed=11)
    for d in (0.03, 0.05, 0.10, 0.14):
        fit = calibrate_density_z(s_out, s_in, target_density=d)
        assert abs(inferred_density(fit) - d) < 1e-3


def test_calibrate_rejects_target_out_of_unit() -> None:
    s_out, s_in = _marginals(20, seed=12)
    for d in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            calibrate_density_z(s_out, s_in, target_density=d)


def test_inferred_density_in_unit_interval() -> None:
    s_out, s_in = _marginals(30, seed=13)
    for d in (0.02, 0.05, 0.10):
        fit = calibrate_density_z(s_out, s_in, target_density=d)
        assert 0.0 <= inferred_density(fit) <= 1.0
