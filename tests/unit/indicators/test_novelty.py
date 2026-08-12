# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifiable unit tests for core.indicators.novelty.

These pin the mathematical invariants of the KL-divergence and cosine-novelty
helpers (no magic numbers — every assertion is an analytic property that fails
if the implementation drifts).
"""
from __future__ import annotations

import numpy as np
import pytest

from core.indicators.novelty import kl_div, novelty_score


# --- kl_div -----------------------------------------------------------------


def test_kl_div_is_zero_for_identical_distributions() -> None:
    p = np.array([0.2, 0.3, 0.5])
    assert kl_div(p, p) == pytest.approx(0.0, abs=1e-12)


def test_kl_div_is_nonnegative_gibbs_inequality() -> None:
    rng = np.random.default_rng(7)
    for _ in range(50):
        p = rng.random(6)
        q = rng.random(6)
        assert kl_div(p, q) >= -1e-12  # D_KL >= 0 (Gibbs)


def test_kl_div_is_asymmetric() -> None:
    p = np.array([0.7, 0.2, 0.1])
    q = np.array([0.2, 0.3, 0.5])
    assert kl_div(p, q) != pytest.approx(kl_div(q, p), abs=1e-6)


def test_kl_div_is_invariant_to_input_scaling() -> None:
    # Inputs are renormalised internally, so an unnormalised vector and its
    # rescaled twin must yield the same divergence.
    p = np.array([1.0, 2.0, 7.0])
    q = np.array([3.0, 3.0, 4.0])
    assert kl_div(p, q) == pytest.approx(kl_div(2.0 * p, 5.0 * q), abs=1e-12)


def test_kl_div_matches_closed_form_two_point() -> None:
    # Hand-computed: p=(0.5,0.5), q=(0.25,0.75)
    #   0.5*ln(0.5/0.25) + 0.5*ln(0.5/0.75)
    p = np.array([0.5, 0.5])
    q = np.array([0.25, 0.75])
    expected = 0.5 * np.log(0.5 / 0.25) + 0.5 * np.log(0.5 / 0.75)
    assert kl_div(p, q) == pytest.approx(float(expected), abs=1e-9)


# --- novelty_score ----------------------------------------------------------


def test_novelty_zero_for_identical_vectors() -> None:
    z = np.array([1.0, 2.0, 3.0])
    assert novelty_score(z, z) == pytest.approx(0.0, abs=1e-6)


def test_novelty_two_for_antiparallel_vectors() -> None:
    z = np.array([1.0, 2.0, 3.0])
    assert novelty_score(z, -z) == pytest.approx(2.0, abs=1e-6)


def test_novelty_one_for_orthogonal_vectors() -> None:
    assert novelty_score(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(
        1.0, abs=1e-6
    )


def test_novelty_is_bounded_in_unit_interval_times_two() -> None:
    rng = np.random.default_rng(11)
    for _ in range(50):
        a = rng.standard_normal(8)
        b = rng.standard_normal(8)
        score = novelty_score(a, b)
        assert -1e-9 <= score <= 2.0 + 1e-9


def test_novelty_is_scale_invariant_in_each_argument() -> None:
    a = np.array([3.0, -1.0, 2.0])
    b = np.array([0.5, 4.0, -2.0])
    assert novelty_score(a, b) == pytest.approx(novelty_score(10.0 * a, 0.1 * b), abs=1e-6)
