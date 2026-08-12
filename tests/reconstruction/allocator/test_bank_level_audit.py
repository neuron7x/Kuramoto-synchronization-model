# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the BankLevelGate5Audit (X-10R-1 PR #3).

Pins five contracts:
  1. Reports four metrics simultaneously, ``passed`` is the AND.
  2. Default thresholds match the X-10R-1 spec (0.20 / 0.60 / 0.05 / 1e-9).
  3. Perfect recovery ⇒ all metrics at their best, passed=True.
  4. Each threshold is independently testable (a failure on metric M
     surfaces in failure_reasons regardless of other metrics).
  5. Per-country relative L1 catches local distortions that the
     aggregate L1 averages out.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.allocator import (
    BankLevelRecoveryReport,
    CountryToBankAllocator,
    SizeWeightedPrior,
    UniformPrior,
    audit_bank_level_recovery,
    synthetic_country_aggregates,
)
from research.reconstruction.allocator.bank_level_audit import (
    CONSERVATION_TOTAL_RELATIVE_ERROR_MAX_DEFAULT,
    PER_COUNTRY_RELATIVE_L1_MAX_DEFAULT,
    TOP_K_BANK_JACCARD_MIN_DEFAULT,
    TOTAL_RELATIVE_L1_MAX_DEFAULT,
)


def _make_substrate(n_countries: int = 3, n_banks: int = 6, seed: int = 42) -> tuple[
    dict[str, float],
    dict[str, float],
    np.ndarray,
    np.ndarray,
    tuple[tuple[str, str], ...],
]:
    return synthetic_country_aggregates(
        n_countries=n_countries,
        n_banks_per_country=n_banks,
        share_distribution="lognormal",
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Defaults match the spec
# ---------------------------------------------------------------------------


def test_default_thresholds_match_x10r1_spec() -> None:
    assert TOTAL_RELATIVE_L1_MAX_DEFAULT == 0.20
    assert TOP_K_BANK_JACCARD_MIN_DEFAULT == 0.60
    assert PER_COUNTRY_RELATIVE_L1_MAX_DEFAULT == 0.05
    assert CONSERVATION_TOTAL_RELATIVE_ERROR_MAX_DEFAULT == 1e-9


# ---------------------------------------------------------------------------
# Perfect-recovery direction
# ---------------------------------------------------------------------------


def test_perfect_recovery_passes_all_thresholds() -> None:
    """Allocated == ground truth ⇒ passed=True with every metric at
    its best value."""
    _agg_in, _agg_out, gt_in, gt_out, bcm = _make_substrate(seed=1)
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=gt_in.copy(),
        allocated_s_out=gt_out.copy(),
        bank_country_map=bcm,
    )
    assert isinstance(report, BankLevelRecoveryReport)
    assert report.passed is True
    assert report.failure_reasons == ()
    assert report.total_relative_l1 == 0.0
    assert report.top_k_bank_jaccard == 1.0
    assert report.per_country_relative_l1_max == 0.0
    assert report.conservation_total_relative_error == 0.0


def test_aligned_size_weighted_prior_passes_audit_end_to_end() -> None:
    """Realistic check: a SizeWeightedPrior with weights aligned to
    the ground truth should pass the audit end-to-end via the
    allocator."""
    agg_in, agg_out, gt_in, gt_out, bcm = _make_substrate(n_banks=6, seed=2)
    weights = {bank: float(gt_in[i]) for i, (bank, _) in enumerate(bcm)}
    cert = CountryToBankAllocator(
        prior=SizeWeightedPrior(bank_country_map=bcm, bank_weights=weights)
    ).allocate(agg_in, agg_out, bank_country_map=bcm)
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=cert.s_in,
        allocated_s_out=cert.s_out,
        bank_country_map=bcm,
    )
    assert report.passed is True


# ---------------------------------------------------------------------------
# Each metric is independently triggerable
# ---------------------------------------------------------------------------


def test_uniform_prior_fails_total_l1_on_lognormal() -> None:
    """UniformPrior on lognormal substrate fails the aggregate L1
    bound (0.20). This is the falsification anchor surface — if the
    audit fails to detect it, downstream priors have nothing to beat."""
    agg_in, agg_out, gt_in, gt_out, bcm = _make_substrate(n_banks=8, seed=3)
    cert = CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm)).allocate(
        agg_in, agg_out, bank_country_map=bcm
    )
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=cert.s_in,
        allocated_s_out=cert.s_out,
        bank_country_map=bcm,
    )
    assert report.passed is False
    assert any("total_relative_l1" in r for r in report.failure_reasons)


def test_per_country_l1_catches_local_distortion_aggregate_misses() -> None:
    """A pathological allocator that gets the country aggregates RIGHT
    but the within-country distribution wrong would pass total_l1 and
    fail per_country_l1. The audit's per-country term must surface this
    distinct failure mode."""
    # 2 countries × 5 banks. Ground truth: bank 0 is the giant in C0;
    # all others equal.
    bcm = (
        ("B0", "C0"),
        ("B1", "C0"),
        ("B2", "C0"),
        ("B3", "C0"),
        ("B4", "C0"),
        ("B5", "C1"),
        ("B6", "C1"),
        ("B7", "C1"),
    )
    gt_in = np.array([100.0, 1.0, 1.0, 1.0, 1.0, 10.0, 10.0, 10.0])
    gt_out = gt_in.copy()
    # Allocator output: same country totals (104, 30) but completely
    # rearranged within-country.
    al_in = np.array([1.0, 1.0, 1.0, 1.0, 100.0, 10.0, 10.0, 10.0])
    al_out = al_in.copy()
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=al_in,
        allocated_s_out=al_out,
        bank_country_map=bcm,
    )
    # Total L1 is non-zero but country totals match exactly.
    assert report.conservation_total_relative_error < 1e-9
    # Per-country must catch the within-country shuffle.
    assert report.per_country_relative_l1_max > 0.05
    assert any("per_country_relative_l1_max" in r for r in report.failure_reasons)
    assert report.per_country_relative_l1_argmax == "C0"


def test_top_k_jaccard_fails_when_top_banks_misidentified() -> None:
    """If the allocator inverts the bank ranking, the top-k jaccard
    drops below 0.6. Catches the situation where the per-country
    distribution is wrong AND the worst-bank is now ranked top —
    a correctness signal that aggregate L1 alone cannot spot."""
    bcm = (
        ("B0", "C0"),
        ("B1", "C0"),
        ("B2", "C0"),
        ("B3", "C0"),
        ("B4", "C0"),
        ("B5", "C0"),
        ("B6", "C0"),
        ("B7", "C0"),
    )
    n = 8
    gt = np.arange(1, n + 1, dtype=np.float64)  # 1..8
    al = gt[::-1].copy()  # 8..1 — full inversion
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt,
        ground_truth_s_out=gt,
        allocated_s_in=al,
        allocated_s_out=al,
        bank_country_map=bcm,
    )
    # Top-k = N//5 = 1; the top bank is fully inverted ⇒ jaccard = 0.
    assert report.top_k_bank_jaccard == 0.0
    assert any("top_k_bank_jaccard" in r for r in report.failure_reasons)


def test_conservation_failure_surfaces_separately() -> None:
    """Total mass mismatch (allocator broke GATE_A1 upstream) must be
    a distinct failure reason — we don't conflate it with L1."""
    bcm = (("B0", "C0"), ("B1", "C0"))
    gt = np.array([100.0, 100.0])
    al = np.array([100.0, 50.0])  # 25% missing mass in country
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt,
        ground_truth_s_out=gt,
        allocated_s_in=al,
        allocated_s_out=al,
        bank_country_map=bcm,
    )
    assert any("conservation_total_relative_error" in r for r in report.failure_reasons)


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------


def test_audit_rejects_shape_mismatch() -> None:
    bcm = (("B0", "C0"), ("B1", "C0"))
    gt = np.zeros(2)
    al_wrong = np.zeros(3)
    with pytest.raises(ValueError, match="same shape"):
        audit_bank_level_recovery(
            ground_truth_s_in=gt,
            ground_truth_s_out=gt,
            allocated_s_in=al_wrong,
            allocated_s_out=gt,
            bank_country_map=bcm,
        )


def test_audit_rejects_bank_country_map_length_mismatch() -> None:
    bcm = (("B0", "C0"),)  # length 1
    gt = np.zeros(2)  # length 2
    with pytest.raises(ValueError, match="bank_country_map length"):
        audit_bank_level_recovery(
            ground_truth_s_in=gt,
            ground_truth_s_out=gt,
            allocated_s_in=gt,
            allocated_s_out=gt,
            bank_country_map=bcm,
        )


def test_audit_rejects_non_finite_inputs() -> None:
    bcm = (("B0", "C0"), ("B1", "C0"))
    gt = np.array([1.0, 2.0])
    bad = np.array([1.0, np.nan])
    with pytest.raises(ValueError, match="finite"):
        audit_bank_level_recovery(
            ground_truth_s_in=bad,
            ground_truth_s_out=gt,
            allocated_s_in=gt,
            allocated_s_out=gt,
            bank_country_map=bcm,
        )
    with pytest.raises(ValueError, match="finite"):
        audit_bank_level_recovery(
            ground_truth_s_in=gt,
            ground_truth_s_out=gt,
            allocated_s_in=np.array([1.0, np.inf]),
            allocated_s_out=gt,
            bank_country_map=bcm,
        )


# ---------------------------------------------------------------------------
# Threshold customisation
# ---------------------------------------------------------------------------


def test_custom_thresholds_change_pass_outcome() -> None:
    """Loosening the bound on a failing case lets it pass; tightening
    on a passing case lets it fail."""
    _agg_in, _agg_out, gt_in, gt_out, bcm = _make_substrate(seed=11)
    report_strict = audit_bank_level_recovery(
        ground_truth_s_in=gt_in,
        ground_truth_s_out=gt_out,
        allocated_s_in=gt_in.copy(),
        allocated_s_out=gt_out.copy(),
        bank_country_map=bcm,
        top_k_bank_jaccard_min=2.0,  # impossible threshold
    )
    assert report_strict.passed is False
    assert any("top_k_bank_jaccard" in r for r in report_strict.failure_reasons)


def test_k_top_override_changes_jaccard_resolution() -> None:
    """With k_top=1 only the top bank matters; with k_top=N every
    bank does. Different k → different jaccard for partial overlap."""
    bcm = tuple((f"B{i}", "C0") for i in range(10))
    gt = np.arange(1, 11, dtype=np.float64)
    # Partial inversion: swap top-1 with bottom-1 only.
    al = gt.copy()
    al[0], al[9] = gt[9], gt[0]
    r_k1 = audit_bank_level_recovery(
        ground_truth_s_in=gt,
        ground_truth_s_out=gt,
        allocated_s_in=al,
        allocated_s_out=al,
        bank_country_map=bcm,
        k_top=1,
    )
    r_k10 = audit_bank_level_recovery(
        ground_truth_s_in=gt,
        ground_truth_s_out=gt,
        allocated_s_in=al,
        allocated_s_out=al,
        bank_country_map=bcm,
        k_top=10,
    )
    # k=1 → top is now the one that was bottom → jaccard = 0
    # k=10 → all banks are in both top-10 sets → jaccard = 1
    assert r_k1.top_k_bank_jaccard == 0.0
    assert r_k10.top_k_bank_jaccard == 1.0


# ---------------------------------------------------------------------------
# Argmax country reporting
# ---------------------------------------------------------------------------


def test_per_country_argmax_identifies_worst_country() -> None:
    """When multiple countries fail at different L1 levels, the report
    must name the WORST one — useful for triage."""
    bcm = (
        ("B0", "C0"),
        ("B1", "C0"),
        ("B2", "C1"),
        ("B3", "C1"),
    )
    gt = np.array([10.0, 10.0, 10.0, 10.0])
    # C0 perfectly recovered; C1 wildly off.
    al = np.array([10.0, 10.0, 1.0, 19.0])
    report = audit_bank_level_recovery(
        ground_truth_s_in=gt,
        ground_truth_s_out=gt,
        allocated_s_in=al,
        allocated_s_out=al,
        bank_country_map=bcm,
    )
    assert report.per_country_relative_l1_argmax == "C1"
