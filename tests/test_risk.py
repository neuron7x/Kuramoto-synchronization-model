"""Tests for fail-closed risk scalar computation."""

from coherence_bridge.risk import compute_risk_scalar


def test_metastable_gamma_gives_max_risk() -> None:
    assert compute_risk_scalar(1.0) == 1.0


def test_far_gamma_gives_low_risk() -> None:
    assert compute_risk_scalar(1.5) == 0.5
    assert compute_risk_scalar(0.0) == 0.0
    assert compute_risk_scalar(2.0) == 0.0


def test_negative_gamma_clamps_to_zero() -> None:
    assert compute_risk_scalar(-0.5) == 0.0


def test_fail_closed_nan() -> None:
    assert compute_risk_scalar(float("nan"), fail_closed=True) == 0.0


def test_fail_closed_inf() -> None:
    assert compute_risk_scalar(float("inf"), fail_closed=True) == 0.0
    assert compute_risk_scalar(float("-inf"), fail_closed=True) == 0.0


def test_fail_open_nan() -> None:
    assert compute_risk_scalar(float("nan"), fail_closed=False) == 1.0


def test_symmetry() -> None:
    """Distance from 1.0 is symmetric."""
    assert compute_risk_scalar(0.7) == compute_risk_scalar(1.3)
