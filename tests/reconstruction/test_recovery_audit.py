# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for recovery_audit.py — GATE_2 + GATE_5."""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.recovery_audit import (
    RECOVERY_THRESHOLDS,
    audit_recovery,
    conservation_of_mass_passes,
)


def test_recovery_thresholds_match_spec() -> None:
    """X-10R Gate 5 thresholds are wired exactly as the spec demands."""
    assert RECOVERY_THRESHOLDS["spectral_radius_relative_error_max"] == 0.20
    assert RECOVERY_THRESHOLDS["top_k_hub_jaccard_min"] == 0.60
    assert RECOVERY_THRESHOLDS["row_sum_invariant_L1_relative_max"] == 0.05
    assert RECOVERY_THRESHOLDS["col_sum_invariant_L1_relative_max"] == 0.05


def test_audit_perfect_recovery_passes() -> None:
    rng = np.random.default_rng(7)
    w = rng.lognormal(mean=10.0, sigma=1.0, size=(40, 40))
    np.fill_diagonal(w, 0.0)
    report = audit_recovery(w, w.copy())
    assert report.passed is True
    assert report.spectral_radius_relative_error == 0.0
    assert report.top_k_hub_jaccard == 1.0


def test_audit_completely_wrong_recovery_fails() -> None:
    rng = np.random.default_rng(7)
    w_true = rng.lognormal(mean=10.0, sigma=1.0, size=(40, 40))
    np.fill_diagonal(w_true, 0.0)
    w_recon = rng.lognormal(mean=2.0, sigma=0.5, size=(40, 40))  # very different scale
    np.fill_diagonal(w_recon, 0.0)
    report = audit_recovery(w_true, w_recon)
    assert report.passed is False
    assert len(report.failure_reasons) >= 1


def test_audit_rejects_shape_mismatch() -> None:
    a = np.ones((10, 10))
    b = np.ones((5, 5))
    with pytest.raises(ValueError):
        audit_recovery(a, b)


def test_audit_rejects_non_square() -> None:
    """Both shape mismatch AND matching-but-non-square inputs are rejected.

    A pair like (10,5)/(10,5) used to slip past the early check and then
    crash inside numpy.linalg.eigvals — a controlled ValueError is the
    documented contract (Codex P2 hardening).
    """
    a = np.ones((10, 5))
    b = np.ones((10, 5))
    with pytest.raises(ValueError, match="square"):
        audit_recovery(a, b)
    a2 = np.ones((10, 10))
    b2 = np.ones((5, 5))
    with pytest.raises(ValueError, match="square"):
        audit_recovery(a2, b2)
    a3 = np.ones((6, 4))  # rectangular, identical
    with pytest.raises(ValueError, match="square"):
        audit_recovery(a3, a3)


def test_audit_strength_hubs_used_not_binary() -> None:
    """Hub jaccard should be based on strength s_out + s_in, not binary degree."""
    n = 50
    w_true = np.zeros((n, n))
    # Node 0 has one MASSIVE edge → highest strength but degree 1
    w_true[0, 1] = 1.0e9
    w_true[1, 0] = 1.0e9
    # Other nodes have small uniform structure: each has 5 small edges
    rng = np.random.default_rng(0)
    for i in range(2, n):
        for j in rng.choice(n, size=5, replace=False):
            if i != j:
                w_true[i, j] = 1.0
    # Recon has same node 0 = top strength but different topology
    w_recon = np.zeros((n, n))
    w_recon[0, 1] = 1.0e9
    w_recon[1, 0] = 1.0e9
    for i in range(2, n):
        # Different random topology
        for j in rng.choice(n, size=5, replace=False):
            if i != j:
                w_recon[i, j] = 1.0
    report = audit_recovery(w_true, w_recon, k_top=2)
    # Top-2 by strength are nodes 0 and 1 in both — jaccard should be 1.0
    assert report.top_k_hub_jaccard == 1.0


def test_conservation_of_mass_passes_for_balanced() -> None:
    s_out = np.array([1.0, 2.0, 3.0])
    s_in = np.array([2.0, 1.0, 3.0])  # same sum
    assert conservation_of_mass_passes(s_out, s_in) is True


def test_conservation_of_mass_fails_for_unbalanced() -> None:
    s_out = np.array([1.0, 2.0, 3.0])
    s_in = np.array([1.0, 1.0, 1.0])  # different sum
    assert conservation_of_mass_passes(s_out, s_in) is False


def test_conservation_of_mass_rejects_zero_in() -> None:
    s = np.zeros(5)
    assert conservation_of_mass_passes(s, s) is False


def test_audit_zero_w_true_gives_inf_relative_error() -> None:
    """Empty truth ⇒ ρ_true = 0 ⇒ relative error is +inf."""
    w_true = np.zeros((10, 10))
    w_recon = np.eye(10) * 0.5
    report = audit_recovery(w_true, w_recon)
    assert np.isinf(report.spectral_radius_relative_error)
    assert report.passed is False


def test_audit_default_k_top_is_n_over_10() -> None:
    n = 50
    w = np.eye(n)
    report = audit_recovery(w, w)
    assert report.k_top == max(1, n // 10)


def test_audit_explicit_k_top_overrides() -> None:
    n = 30
    w = np.eye(n)
    report = audit_recovery(w, w, k_top=7)
    assert report.k_top == 7
