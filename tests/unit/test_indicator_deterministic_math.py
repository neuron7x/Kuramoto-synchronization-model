# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic math regression tests for core indicators.

These tests cover the analytical edge cases for the Kuramoto order parameter,
Ollivier–Ricci curvature, Hurst exponent estimation, and Shannon entropy.
The goal is to guarantee that the closed-form formulas remain correct even
after refactors and to ensure that boundary conditions never regress.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from core.indicators import entropy as entropy_module
from core.indicators import hurst as hurst_module
from core.indicators import kuramoto as kuramoto_module
from core.indicators import ricci as ricci_module


def test_kuramoto_order_is_zero_for_uniform_phase_distribution() -> None:
    """Phases evenly distributed on the unit circle must yield R ≈ 0."""

    phases = np.array([0.0, 2 * np.pi / 3.0, 4 * np.pi / 3.0], dtype=float)
    result = kuramoto_module.kuramoto_order(phases)
    assert math.isfinite(result)
    assert result == pytest.approx(0.0, abs=1e-12)


def test_multi_asset_kuramoto_detects_antiphase_assets() -> None:
    """Two perfectly anti-phase oscillators must have zero synchrony."""

    t = np.linspace(0.0, 2 * np.pi, 512, endpoint=False)
    series_a = np.sin(t)
    series_b = np.sin(t + np.pi)

    R = kuramoto_module.multi_asset_kuramoto([series_a, series_b])
    assert math.isfinite(R)
    assert R == pytest.approx(0.0, abs=1e-12)


def test_ricci_curvature_equilateral_triangle_is_unity() -> None:
    """Fully connected triangle has identical neighbourhoods ⇒ κ = 1."""

    G = ricci_module.nx.Graph()
    G.add_weighted_edges_from([(0, 1, 1.0), (1, 2, 1.0), (2, 0, 1.0)])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        curvature = ricci_module.ricci_curvature_edge(G, 0, 1)

    assert curvature == pytest.approx(1.0, rel=1e-12)


def test_mean_ricci_matches_average_edge_curvature_for_path_graph() -> None:
    """Mean Ricci curvature should equal the arithmetic mean of edges."""

    G = ricci_module.nx.Graph()
    G.add_weighted_edges_from([(0, 1, 1.0), (1, 2, 1.0), (2, 3, 1.0)])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        edge_curvatures = [ricci_module.ricci_curvature_edge(G, u, v) for u, v in G.edges()]
        mean_curvature = ricci_module.mean_ricci(G)

    expected = float(np.mean(edge_curvatures))
    assert mean_curvature == pytest.approx(expected, rel=1e-12)


def _manual_hurst(series: np.ndarray, min_lag: int, max_lag: int) -> float:
    """Re-implement the rescaled range regression to validate hurst_exponent."""

    x = np.asarray(series, dtype=float)
    lags = np.arange(min_lag, max_lag + 1)
    tau = np.array([np.std(x[lag:] - x[:-lag]) for lag in lags])
    y = np.log(tau)
    X = np.vstack([np.ones_like(lags, dtype=float), np.log(lags)]).T
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(np.clip(beta[1], 0.0, 1.0))


def test_hurst_matches_manual_rescaled_range_regression() -> None:
    """Hurst exponent should equal the slope of the log-log regression."""

    series = np.array(
        [
            0.0,
            0.5,
            1.5,
            3.0,
            5.0,
            7.5,
            10.5,
            14.0,
            18.0,
            22.5,
            27.5,
            33.0,
            39.0,
            45.5,
            52.5,
            60.0,
        ],
        dtype=float,
    )
    min_lag, max_lag = 2, 5

    manual = _manual_hurst(series, min_lag, max_lag)
    implementation = hurst_module.hurst_exponent(series, min_lag=min_lag, max_lag=max_lag)

    assert implementation == pytest.approx(manual, rel=1e-12)


def test_entropy_binary_distribution_equals_ln_two() -> None:
    """Binary distribution with equal mass has entropy log(2)."""

    series = np.array([0.0, 0.0, 1.0, 1.0], dtype=float)
    result = entropy_module.entropy(series, bins=2)
    assert result == pytest.approx(math.log(2.0), rel=1e-12)


def test_delta_entropy_detects_entropy_jump_between_windows() -> None:
    """Delta entropy must measure the difference between consecutive windows."""

    first_window = np.zeros(100, dtype=float)
    second_window = np.tile([0.0, 1.0], 50).astype(float)
    series = np.concatenate([first_window, second_window])

    delta = entropy_module.delta_entropy(series, window=100, bins_range=(2, 10))
    assert delta == pytest.approx(math.log(2.0), rel=1e-12)
