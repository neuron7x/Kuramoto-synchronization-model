# SPDX-License-Identifier: MIT
"""Tests for the physics-invariant calibration harness.

These tests pin two contracts:

1. **Determinism (INV-HPC1)** — every public calibration entry
   point is reproducible to bit-identity given the same seed.
2. **Pass/fail correctness** — on the canonical default grid, all
   reports must pass. A regression that pushes recovery error
   above the documented tolerance fails the suite.

The fBm generator is exercised directly: at ``H = 0.5`` it must
produce fGn whose lag-1 autocorrelation is near zero (white noise,
the canonical Brownian case).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.physics.calibration import (
    CalibrationReport,
    calibrate_dro_hurst,
    calibrate_ott_antonsen_steady,
    format_markdown_table,
    generate_fractional_brownian_motion,
    run_calibration_suite,
)

# ---------------------------------------------------------------------------
# fBm generator basic invariants
# ---------------------------------------------------------------------------


def test_fbm_rejects_invalid_H() -> None:
    for bad in (-0.1, 0.0, 1.0, 1.5, math.nan):
        with pytest.raises(ValueError, match="H must lie in"):
            generate_fractional_brownian_motion(bad, 256, seed=0)


def test_fbm_rejects_invalid_n() -> None:
    for bad in (0, -1, -100):
        with pytest.raises(ValueError, match="n must be a positive integer"):
            generate_fractional_brownian_motion(0.5, bad, seed=0)


def test_fbm_deterministic_under_seed() -> None:
    a = generate_fractional_brownian_motion(0.7, 1024, seed=42)
    b = generate_fractional_brownian_motion(0.7, 1024, seed=42)
    np.testing.assert_array_equal(a, b)


def test_fbm_at_half_yields_uncorrelated_increments() -> None:
    """H = 0.5 reduces fBm to standard Brownian motion: increments are i.i.d.

    The generator must produce a path whose first-difference series
    has lag-1 autocorrelation near zero.
    """
    series = generate_fractional_brownian_motion(0.5, 4096, seed=42)
    increments = np.diff(series)
    autocorr_lag1 = float(np.corrcoef(increments[:-1], increments[1:])[0, 1])
    assert abs(autocorr_lag1) < 0.1, (
        f"fBm(H=0.5) increments expected uncorrelated, got "
        f"autocorr_lag1 = {autocorr_lag1:.4f}; |autocorr| ≥ 0.1 "
        "implies the Davies-Harte embedding has drifted from the "
        "white-noise baseline."
    )


def test_fbm_persistent_increments_for_high_H() -> None:
    """H > 0.5 produces persistent increments — positive lag-1 autocorr."""
    series = generate_fractional_brownian_motion(0.9, 4096, seed=42)
    increments = np.diff(series)
    autocorr_lag1 = float(np.corrcoef(increments[:-1], increments[1:])[0, 1])
    assert autocorr_lag1 > 0.1, (
        f"fBm(H=0.9) expected persistent (positive autocorr), got "
        f"autocorr_lag1 = {autocorr_lag1:.4f}; persistent fBm should have "
        "lag-1 autocorr clearly above zero."
    )


def test_fbm_anti_persistent_increments_for_low_H() -> None:
    """H < 0.5 produces anti-persistent increments — negative lag-1 autocorr."""
    series = generate_fractional_brownian_motion(0.2, 4096, seed=42)
    increments = np.diff(series)
    autocorr_lag1 = float(np.corrcoef(increments[:-1], increments[1:])[0, 1])
    assert autocorr_lag1 < -0.1, (
        f"fBm(H=0.2) expected anti-persistent (negative autocorr), got "
        f"autocorr_lag1 = {autocorr_lag1:.4f}; anti-persistent fBm should "
        "have lag-1 autocorr clearly below zero."
    )


# ---------------------------------------------------------------------------
# CalibrationReport correctness on canonical cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("H_target", [0.3, 0.5, 0.7, 0.9])
def test_calibrate_dro_hurst_passes_on_canonical_grid(H_target: float) -> None:
    """The default grid (H ∈ {0.3, 0.5, 0.7, 0.9}) must pass."""
    report = calibrate_dro_hurst(H_target=H_target, n=4096, seed=42)
    assert isinstance(report, CalibrationReport)
    assert report.invariant_id == "INV-DRO1"
    assert report.passes, (
        f"INV-DRO1 calibration regression: H_target={H_target}, "
        f"H_estimated={report.estimated:.4f}, abs_error={report.abs_error:.4f} > "
        f"spec_tolerance={report.spec_tolerance:.2f}. "
        "If this fires, either the DFA estimator drifted or the fBm "
        "generator's Hurst-targeting drifted."
    )


@pytest.mark.parametrize(
    ("K", "delta"),
    [(1.5, 0.5), (2.0, 0.5), (3.0, 0.5), (5.0, 0.5), (10.0, 0.5)],
)
def test_calibrate_ott_antonsen_passes_on_supercritical_grid(K: float, delta: float) -> None:
    report = calibrate_ott_antonsen_steady(K=K, delta=delta)
    assert report.invariant_id == "INV-OA2"
    assert report.passes, (
        f"INV-OA2 calibration regression: K={K}, delta={delta}, "
        f"R_estimated={report.estimated:.6f}, "
        f"R_analytical={report.ground_truth:.6f}, "
        f"abs_error={report.abs_error:.3e} > "
        f"spec_tolerance={report.spec_tolerance:.0e}. "
        "If this fires, the OA integrator's RK4 step drifted from "
        "the analytical fixed point."
    )


def test_calibrate_ott_antonsen_rejects_subcritical() -> None:
    with pytest.raises(ValueError, match=r"K > 2.delta"):
        calibrate_ott_antonsen_steady(K=0.5, delta=0.5)


# ---------------------------------------------------------------------------
# Suite + formatting
# ---------------------------------------------------------------------------


def test_run_calibration_suite_returns_per_invariant_dict() -> None:
    suite = run_calibration_suite()
    assert "INV-DRO1" in suite
    assert "INV-OA2" in suite
    assert all(isinstance(r, CalibrationReport) for r in suite["INV-DRO1"])
    assert all(isinstance(r, CalibrationReport) for r in suite["INV-OA2"])


def test_run_calibration_suite_all_pass_on_default_grid() -> None:
    suite = run_calibration_suite()
    flat = [r for reports in suite.values() for r in reports]
    failed = [r for r in flat if not r.passes]
    assert not failed, (
        f"calibration suite has {len(failed)} failing case(s) on the "
        f"default grid: {[(r.invariant_id, r.case, r.abs_error) for r in failed]}. "
        "If this fires, either an estimator drifted or the fBm "
        "generator's Hurst-targeting drifted."
    )


def test_format_markdown_table_includes_all_columns() -> None:
    reports = [
        calibrate_dro_hurst(H_target=0.5, n=2048, seed=7),
        calibrate_ott_antonsen_steady(K=2.0, delta=0.5),
    ]
    table = format_markdown_table(reports)
    for column in [
        "INV",
        "Estimator",
        "Case",
        "Truth",
        "Estimated",
        "Error",
        "Tolerance",
        "Pass",
    ]:
        assert column in table, (
            f"format_markdown_table missing column {column!r}; "
            "the engineer-facing artifact contract has drifted."
        )


def test_format_markdown_table_empty_returns_empty_string() -> None:
    assert format_markdown_table([]) == ""


def test_calibration_report_is_frozen() -> None:
    report = calibrate_dro_hurst(H_target=0.5, n=2048, seed=7)
    with pytest.raises((AttributeError, TypeError)):
        report.passes = False  # type: ignore[misc]
