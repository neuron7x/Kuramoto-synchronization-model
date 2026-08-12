# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the composed Domain-of-Validity gate (X-10R-1 PR #6).

The composition is a 4-cell verdict matrix:

    reconstruction WITHIN  &  allocator WITHIN  ⇒ BOTH_WITHIN
    reconstruction OUT     &  allocator WITHIN  ⇒ RECONSTRUCTION_OUT
    reconstruction WITHIN  &  allocator OUT     ⇒ ALLOCATOR_OUT
    reconstruction OUT     &  allocator OUT     ⇒ BOTH_OUT

Only BOTH_WITHIN admits a bank-level claim. Anything else keeps
INV-IDENTIFICATION-1 in force.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.reconstruction.allocator import (
    ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT,
    BankLevelMarginalsCertificate,
    ComposedDomainCheck,
    ComposedDomainStatus,
    CountryToBankAllocator,
    SizeWeightedPrior,
    check_composed_domain_of_validity,
    load_mfi_registry,
)
from research.reconstruction.allocator.data import MFI_DEMO_TSV
from research.reconstruction.positive_control import (
    GroundTruthRecoveryCertificate,
    ground_truth_core_periphery,
    run_recovery_on_substrate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _within_recovery_cert(n: int = 80, seed: int = 42) -> GroundTruthRecoveryCertificate:
    w = ground_truth_core_periphery(n=n, core_frac=0.30, seed=seed)
    return run_recovery_on_substrate(f"CP_{n}_dov_compose", w, seed=seed)


def _stub_allocator_cert(coverage: float) -> BankLevelMarginalsCertificate:
    """Construct a BankLevelMarginalsCertificate with the requested
    coverage_ratio. Other fields filled with minimal valid values
    so the dataclass post-init invariants pass."""
    s = np.array([1.0], dtype=np.float64)
    return BankLevelMarginalsCertificate(
        prior_id="stub",
        n_countries=1,
        n_banks=1,
        coverage_ratio=coverage,
        fallback_policy="uniform_within_country",
        bank_country_map=(("B0", "C0"),),
        s_in=s,
        s_out=s,
        country_aggregates_in=(("C0", 1.0),),
        country_aggregates_out=(("C0", 1.0),),
        cert_id="0" * 64,
    )


def _balanced_marginals_at_n(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    s_out = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = rng.lognormal(mean=10.0, sigma=1.0, size=n)
    s_in = s_in * (s_out.sum() / s_in.sum())
    return s_out, s_in


# ---------------------------------------------------------------------------
# Verdict matrix — the four canonical paths
# ---------------------------------------------------------------------------


def test_both_within_when_both_layers_certify() -> None:
    """Reconstruction WITHIN + allocator coverage ≥ 0.80 ⇒ BOTH_WITHIN.
    This is the only verdict that admits a bank-level claim."""
    rec_cert = _within_recovery_cert(n=80, seed=1)
    alloc_cert = _stub_allocator_cert(coverage=1.0)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=11)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    assert isinstance(composed, ComposedDomainCheck)
    assert composed.status is ComposedDomainStatus.BOTH_WITHIN
    assert composed.is_admissible_for_downstream_bank_level_test is True


def test_reconstruction_out_when_only_allocator_certifies() -> None:
    """Reconstruction OUT + allocator WITHIN ⇒ RECONSTRUCTION_OUT.
    Bank-level claim still forbidden."""
    rec_cert = _within_recovery_cert(n=80, seed=2)
    alloc_cert = _stub_allocator_cert(coverage=1.0)
    # Push reconstruction OUT: real N way above the certified envelope.
    s_out, s_in = _balanced_marginals_at_n(n=400, seed=12)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    assert composed.status is ComposedDomainStatus.RECONSTRUCTION_OUT
    assert composed.is_admissible_for_downstream_bank_level_test is False


def test_allocator_out_when_coverage_below_threshold() -> None:
    """Reconstruction WITHIN + allocator coverage < 0.80 ⇒
    ALLOCATOR_OUT. Bank-level claim still forbidden."""
    rec_cert = _within_recovery_cert(n=80, seed=3)
    # Coverage 0.50 < 0.80 default threshold.
    alloc_cert = _stub_allocator_cert(coverage=0.50)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=13)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    assert composed.status is ComposedDomainStatus.ALLOCATOR_OUT
    assert composed.is_admissible_for_downstream_bank_level_test is False
    assert composed.allocator_checks["coverage_ratio"] is False


def test_both_out_when_neither_layer_certifies() -> None:
    """Reconstruction OUT + allocator OUT ⇒ BOTH_OUT.
    Both reasons are surfaced in `notes`."""
    rec_cert = _within_recovery_cert(n=80, seed=4)
    alloc_cert = _stub_allocator_cert(coverage=0.40)
    # Push reconstruction OUT.
    s_out, s_in = _balanced_marginals_at_n(n=400, seed=14)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    assert composed.status is ComposedDomainStatus.BOTH_OUT
    assert composed.is_admissible_for_downstream_bank_level_test is False
    assert "reconstruction" in composed.notes
    assert "coverage_ratio" in composed.notes


# ---------------------------------------------------------------------------
# Coverage threshold customisation
# ---------------------------------------------------------------------------


def test_default_coverage_threshold_is_0_80() -> None:
    assert ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT == 0.80


def test_custom_coverage_threshold_changes_verdict() -> None:
    """A caller can tighten the coverage threshold to push an
    otherwise-WITHIN allocator into OUT territory."""
    rec_cert = _within_recovery_cert(n=80, seed=5)
    alloc_cert = _stub_allocator_cert(coverage=0.95)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=15)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
        allocator_coverage_ratio_min=0.99,  # tighter than default
    )
    assert composed.status is ComposedDomainStatus.ALLOCATOR_OUT


# ---------------------------------------------------------------------------
# Provenance fields surfaced in measured but not gated
# ---------------------------------------------------------------------------


def test_n_banks_and_n_countries_surface_as_measured_only() -> None:
    """`n_banks` and `n_countries` are PROVENANCE — they appear in
    `allocator_measured` for inspection but do NOT drive the verdict
    (separate from `allocator_checks`)."""
    rec_cert = _within_recovery_cert(n=80, seed=6)
    alloc_cert = _stub_allocator_cert(coverage=1.0)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=16)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    assert "n_banks" in composed.allocator_measured
    assert "n_countries" in composed.allocator_measured
    assert "n_banks" not in composed.allocator_checks
    assert "n_countries" not in composed.allocator_checks


def test_allocator_envelope_carries_coverage_threshold() -> None:
    """`allocator_envelope` records the threshold so reviewers can
    audit which bound was applied."""
    rec_cert = _within_recovery_cert(n=80, seed=7)
    alloc_cert = _stub_allocator_cert(coverage=1.0)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=17)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
        allocator_coverage_ratio_min=0.85,
    )
    assert composed.allocator_envelope["coverage_ratio"] == (0.85, 1.0)


# ---------------------------------------------------------------------------
# End-to-end: real fixture → real allocator cert → composed gate
# ---------------------------------------------------------------------------


def test_e2e_demo_fixture_produces_both_within_at_matched_envelopes() -> None:
    """Final E2E: load the frozen MFI demo fixture, build a real
    BankLevelMarginalsCertificate via SizeWeightedPrior + the
    allocator, build a real reconstruction certificate at matched
    N + density, and verify the composed gate emits BOTH_WITHIN
    on within-envelope marginals."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    n_banks = out.n_rows  # 25 banks
    # Reconstruction certificate at the same N as the bank count.
    rec_cert = _within_recovery_cert(n=n_banks, seed=42)

    agg_in = {"DE": 100.0, "FR": 90.0, "IT": 70.0, "ES": 60.0, "NL": 50.0}
    agg_out = {"DE": 95.0, "FR": 85.0, "IT": 65.0, "ES": 55.0, "NL": 45.0}
    alloc_cert = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out.bank_country_map,
            bank_weights=out.bank_weights,
        )
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)

    s_out, s_in = _balanced_marginals_at_n(n=n_banks, seed=42)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    assert composed.status is ComposedDomainStatus.BOTH_WITHIN
    assert composed.is_admissible_for_downstream_bank_level_test is True
    # Allocator coverage on the demo fixture is 1.0 (every country
    # has positive total weight).
    assert composed.allocator_measured["coverage_ratio"] == pytest.approx(1.0)
    assert composed.allocator_measured["n_banks"] == 25.0
    assert composed.allocator_measured["n_countries"] == 5.0


# ---------------------------------------------------------------------------
# Admissibility ≠ validation discipline
# ---------------------------------------------------------------------------


def test_both_within_does_not_imply_gate6_ready_or_validated() -> None:
    """A BOTH_WITHIN composed verdict means inputs are admissible
    for the NEXT downstream test (Gate 6 forward signal in epic
    PR #7). It does NOT mean the bank-level result is
    scientifically validated. The two properties are deliberately
    distinct so a downstream consumer cannot conflate them."""
    rec_cert = _within_recovery_cert(n=80, seed=8)
    alloc_cert = _stub_allocator_cert(coverage=1.0)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=21)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    composed = check_composed_domain_of_validity(
        s_out,
        s_in,
        recovery_certificate=rec_cert,
        allocator_certificate=alloc_cert,
        reconstruction_inferred_density=inside,
    )
    # The two flags are independent properties. Admissibility True,
    # validation False — that gap is the entire point of this layer.
    assert composed.is_admissible_for_downstream_bank_level_test is True
    assert composed.is_scientifically_validated_bank_level_result is False


def test_validated_flag_is_false_on_every_verdict() -> None:
    """`is_scientifically_validated_bank_level_result` is hard-coded
    False on every ComposedDomainCheck — validation is owned by
    Gate 6 (epic PR #7), NOT by the DoV gate. This test pins the
    property's invariant: it cannot be flipped True by composition
    alone, regardless of how many envelopes certify."""
    rec_cert = _within_recovery_cert(n=80, seed=9)
    s_out, s_in = _balanced_marginals_at_n(n=80, seed=22)
    inside = float((min(rec_cert.tested_at_densities) + max(rec_cert.tested_at_densities)) / 2.0)
    # Run every cell of the verdict matrix; the validated flag must
    # stay False on each.
    for coverage, expected_status in [
        (1.0, ComposedDomainStatus.BOTH_WITHIN),
        (0.40, ComposedDomainStatus.ALLOCATOR_OUT),
    ]:
        alloc_cert = _stub_allocator_cert(coverage=coverage)
        composed = check_composed_domain_of_validity(
            s_out,
            s_in,
            recovery_certificate=rec_cert,
            allocator_certificate=alloc_cert,
            reconstruction_inferred_density=inside,
        )
        assert composed.status is expected_status
        assert composed.is_scientifically_validated_bank_level_result is False, (
            f"validation flag must remain False at {expected_status.value}; "
            "validation is owned by Gate 6 (epic PR #7), not the DoV gate"
        )
