# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for kuramoto_on_reconstruction.py — Gate 6 precursor test."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.kuramoto_on_reconstruction import (
    MIN_PRECURSOR_GAP,
    KuramotoRecoveryCertificate,
    PrecursorReport,
    gate_6_precursor_discriminative,
    issue_kuramoto_recovery_certificate,
)


def _structured_w(n: int = 50, seed: int = 0) -> np.ndarray:
    """Synthetic structured W: log-normal weights on Erdős–Rényi at p=0.2."""
    rng = np.random.default_rng(seed)
    a = (rng.uniform(size=(n, n)) < 0.2).astype(np.float64)
    np.fill_diagonal(a, 0.0)
    weights = rng.lognormal(mean=2.0, sigma=1.0, size=(n, n))
    w: np.ndarray = (a * weights).astype(np.float64)
    np.fill_diagonal(w, 0.0)
    return w


def test_min_precursor_gap_constant() -> None:
    assert MIN_PRECURSOR_GAP == 0.05


def test_gate_6_returns_precursor_report() -> None:
    w = _structured_w(n=30, seed=0)
    report = gate_6_precursor_discriminative(w, seed=42, n_bootstrap=4)
    assert isinstance(report, PrecursorReport)
    assert 0.0 <= report.r_recon_median <= 1.0
    assert 0.0 <= report.r_shuffled_median <= 1.0


def test_gate_6_rejects_too_small_n() -> None:
    w = np.zeros((4, 4))
    w[0, 1] = 1.0
    w[1, 0] = 1.0
    with pytest.raises(ValueError, match="N >= 8"):
        gate_6_precursor_discriminative(w, n_bootstrap=4)


def test_gate_6_rejects_too_few_bootstrap() -> None:
    w = _structured_w(n=20, seed=0)
    with pytest.raises(ValueError, match="n_bootstrap"):
        gate_6_precursor_discriminative(w, n_bootstrap=2)


def test_gate_6_rejects_non_positive_min_gap() -> None:
    """Codex P1: a non-positive min_gap makes the CI test trivially true,
    producing false-positive certificates. Must raise ValueError up front."""
    w = _structured_w(n=20, seed=0)
    with pytest.raises(ValueError, match="min_gap"):
        gate_6_precursor_discriminative(w, n_bootstrap=4, min_gap=0.0)
    with pytest.raises(ValueError, match="min_gap"):
        gate_6_precursor_discriminative(w, n_bootstrap=4, min_gap=-0.05)


def test_gate_6_rejects_non_square() -> None:
    w = np.zeros((10, 5))
    with pytest.raises(ValueError):
        gate_6_precursor_discriminative(w, n_bootstrap=4)


def test_gate_6_ci_bounds_consistent() -> None:
    w = _structured_w(n=30, seed=1)
    report = gate_6_precursor_discriminative(w, seed=42, n_bootstrap=4)
    assert report.delta_r_ci_low <= report.delta_r_median <= report.delta_r_ci_high


def test_gate_6_passed_iff_ci_excludes_zero_band() -> None:
    """passed iff the 95% CI lies entirely outside [-min_gap, +min_gap]."""
    w = _structured_w(n=30, seed=2)
    report = gate_6_precursor_discriminative(w, seed=42, n_bootstrap=4, min_gap=0.05)
    if report.passed:
        assert report.delta_r_ci_low >= 0.05 or report.delta_r_ci_high <= -0.05
    else:
        assert (
            -0.05 < report.delta_r_ci_low < 0.05
            or -0.05 < report.delta_r_ci_high < 0.05
            or (report.delta_r_ci_low < 0.05 and report.delta_r_ci_high > -0.05)
        )


def test_gate_6_failure_reason_set_when_failed() -> None:
    """If the report is reported as failed, failure_reason must be non-None."""
    # Use a near-symmetric W to make ΔR small.
    n = 30
    w = np.ones((n, n))
    np.fill_diagonal(w, 0.0)
    report = gate_6_precursor_discriminative(w, seed=0, n_bootstrap=4, min_gap=0.5)
    if not report.passed:
        assert report.failure_reason is not None
        assert "Gate 6" in report.failure_reason


def test_issue_certificate_is_64_hex() -> None:
    w = _structured_w(n=20, seed=0)
    cert = issue_kuramoto_recovery_certificate(w, seed=0, n_bootstrap=4)
    assert isinstance(cert, KuramotoRecoveryCertificate)
    assert len(cert.cert_id) == 64
    int(cert.cert_id, 16)


def test_issue_certificate_seed_sensitive() -> None:
    w = _structured_w(n=20, seed=0)
    cert_a = issue_kuramoto_recovery_certificate(w, seed=10, n_bootstrap=4)
    cert_b = issue_kuramoto_recovery_certificate(w, seed=11, n_bootstrap=4)
    # Different seeds → different cert_ids (R medians differ)
    assert cert_a.cert_id != cert_b.cert_id


def test_certificate_passed_matches_report() -> None:
    w = _structured_w(n=20, seed=3)
    cert = issue_kuramoto_recovery_certificate(w, seed=0, n_bootstrap=4)
    assert cert.passed == cert.report.passed


def test_certificate_is_valid_only_when_passed() -> None:
    w = _structured_w(n=20, seed=4)
    cert = issue_kuramoto_recovery_certificate(w, seed=0, n_bootstrap=4)
    assert cert.is_valid() == (cert.passed and bool(cert.cert_id))
