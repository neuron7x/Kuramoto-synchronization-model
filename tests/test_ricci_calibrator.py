# mypy: ignore-errors
"""Tests for Ricci temporal calibrator — honest measurement."""

from __future__ import annotations

import numpy as np
import pytest

from geosync.estimators.ricci_calibrator import (
    RicciLeadTimeCalibrator,
    RicciTemporalCalibrator,
)


def test_backward_compat_alias() -> None:
    """RicciLeadTimeCalibrator is alias for RicciTemporalCalibrator."""
    assert RicciLeadTimeCalibrator is RicciTemporalCalibrator


def test_random_data_remove_claim() -> None:
    """Random κ and returns → not predictive → REMOVE_CLAIM."""
    rng = np.random.default_rng(42)
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(rng.standard_normal(500) * 0.3, rng.standard_normal(500) * 0.01)
    assert result.recommendation in ("REMOVE_CLAIM", "CAUTION")
    assert len(result.honest_statement) > 20


def test_honest_statement_never_contains_precedes() -> None:
    """honest_statement never uses 'precedes'."""
    rng = np.random.default_rng(42)
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(rng.standard_normal(500) * 0.5, rng.standard_normal(500) * 0.01)
    assert "precedes" not in result.honest_statement.lower()


def test_honest_statement_never_contains_5_15() -> None:
    """honest_statement never uses '5-15'."""
    rng = np.random.default_rng(42)
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(rng.standard_normal(500) * 0.5, rng.standard_normal(500) * 0.01)
    assert "5-15" not in result.honest_statement


def test_fragile_classification() -> None:
    """κ < -0.3 → 'fragile' classification."""
    rng = np.random.default_rng(42)
    kappa = np.full(200, -0.8) + rng.standard_normal(200) * 0.05
    returns = rng.standard_normal(200) * 0.01
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(kappa, returns)
    assert result.regime_classification == "fragile"


def test_not_calibrated_when_no_data() -> None:
    """Insufficient data → is_calibrated=False."""
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(np.zeros(10), np.zeros(10))
    assert not result.is_calibrated
    assert result.empirical_offset_bars is None


def test_calibration_result_frozen() -> None:
    """CalibrationResult is frozen."""
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(np.zeros(10), np.zeros(10))
    with pytest.raises(AttributeError):
        result.ricci_value = 999.0  # type: ignore[misc]


def test_n_events_counted() -> None:
    """n_events matches κ < threshold count."""
    rng = np.random.default_rng(42)
    kappa = np.zeros(200)
    kappa[10] = -0.5
    kappa[50] = -0.5
    kappa[100] = -0.5
    returns = rng.standard_normal(200) * 0.01
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(kappa, returns, kappa_threshold=-0.3)
    assert result.n_events == 3


def test_honest_statement_contains_ricci_value() -> None:
    """honest_statement always includes Ricci= value."""
    rng = np.random.default_rng(42)
    cal = RicciTemporalCalibrator()
    result = cal.calibrate(rng.standard_normal(200) * 0.5, rng.standard_normal(200) * 0.01)
    assert "Ricci=" in result.honest_statement
