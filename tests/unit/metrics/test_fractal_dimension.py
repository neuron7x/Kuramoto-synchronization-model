# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifiable unit tests for core.metrics.fractal_dimension.box_counting_dim.

The estimator fits the slope of log N(eps) vs -log(eps), where N(eps) is the
number of occupied amplitude bins. These tests pin its real, deterministic
behaviour via analytic/relational properties rather than magic numbers.
"""
from __future__ import annotations

import numpy as np

from core.metrics.fractal_dimension import box_counting_dim


def test_returns_finite_float() -> None:
    t = np.linspace(0.0, 10.0, 1000)
    d = box_counting_dim(np.sin(t))
    assert isinstance(d, float)
    assert np.isfinite(d)


def test_is_deterministic() -> None:
    t = np.linspace(0.0, 10.0, 500)
    sig = np.sin(t) + 0.1 * t
    assert box_counting_dim(sig) == box_counting_dim(sig)


def test_constant_signal_has_near_zero_dimension() -> None:
    # A constant signal occupies a single amplitude bin at every resolution, so
    # log N(eps) is flat and the fitted slope collapses to ~0.
    d = box_counting_dim(np.full(512, 3.14))
    assert abs(d) < 1e-6


def test_spread_signal_dominates_constant_signal() -> None:
    # A signal spanning a wide amplitude range occupies more bins as resolution
    # increases, so its slope must exceed that of a constant (flat) signal.
    spread = box_counting_dim(np.linspace(0.0, 1.0, 1000))
    constant = box_counting_dim(np.zeros(1000))
    assert spread > constant


def test_honours_custom_eps_list() -> None:
    sig = np.sin(np.linspace(0.0, 20.0, 800))
    custom = box_counting_dim(sig, eps_list=np.logspace(-2.0, -0.5, 6))
    default = box_counting_dim(sig)
    # Both are finite; a different resolution grid yields a distinct estimate.
    assert np.isfinite(custom)
    assert custom != default


def test_densely_filled_interval_has_dimension_near_one() -> None:
    """`(hist > 0).sum()` counts OCCUPIED boxes — the whole of box-counting.

    A densely-sampled ramp fills its amplitude interval, so at every resolution nearly every
    box is occupied and the box-counting dimension of a filled 1-D interval is ~1. Under
    `Gt -> LtE` the code counts EMPTY boxes instead: for a filled interval that count is ~0 at
    all resolutions, the log-log slope collapses to ~0, and the reported "dimension" is wrong.
    The existing finiteness/ordering tests all pass under that mutant; a value assertion tied
    to the known dimension does not.
    """
    dimension = box_counting_dim(np.linspace(0.0, 1.0, 2000))
    assert dimension > 0.9, (
        f"a filled 1-D interval must have box-counting dimension ~1, got {dimension:.4f} "
        "(empty-box counting collapses this to ~0)"
    )
    assert dimension < 1.1
