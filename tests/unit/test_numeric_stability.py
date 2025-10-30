# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Numerical stability tests shared across CPU architectures."""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from core.indicators.kuramoto import compute_phase, kuramoto_order
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL


def test_compute_phase_filters_non_finite_values() -> None:
    """compute_phase should sanitise NaN/Inf inputs before processing."""

    raw = np.array([0.0, np.nan, np.inf, -np.inf, 1e12, -1e12], dtype=float)
    phases = compute_phase(raw)

    assert phases.shape == raw.shape
    assert np.all(np.isfinite(phases))
    assert np.all(np.abs(phases) <= np.pi + 1e-12)


def test_kuramoto_order_consistent_precision() -> None:
    """Float32 and float64 execution paths should agree within global tolerances."""

    rng = np.random.default_rng(2024)
    samples = rng.normal(size=4096)

    phases64 = compute_phase(samples, use_float32=False)
    phases32 = compute_phase(samples, use_float32=True)

    baseline = kuramoto_order(phases64)
    reduced = kuramoto_order(phases32)

    assert reduced == pytest.approx(baseline, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)


def test_kuramoto_order_handles_nan_and_inf_matrix() -> None:
    """Matrix inputs containing NaN/Inf should clamp to finite probabilities."""

    matrix = np.array(
        [
            [0.0, np.nan, np.pi / 2],
            [np.inf, -np.inf, 0.0],
            [np.pi / 4, -np.pi / 4, np.nan],
        ],
        dtype=float,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        values = kuramoto_order(matrix)

    assert not caught
    assert values.shape == (3,)
    assert np.all(np.isfinite(values))
    assert np.all((0.0 <= values) & (values <= 1.0))


def test_kuramoto_order_accepts_complex_inputs_without_warning() -> None:
    """Complex-valued phases should be projected safely onto the unit circle."""

    phases = np.linspace(-np.pi, np.pi, 128)
    complex_phases = np.exp(1j * phases)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        complex_value = kuramoto_order(complex_phases)

    assert not caught
    real_value = kuramoto_order(phases)
    assert complex_value == pytest.approx(
        real_value, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
    )
