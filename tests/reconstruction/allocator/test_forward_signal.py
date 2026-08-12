# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the X-10R-1 final epic PR #7 — E2E forward-signal pipeline.

This is the closing test surface of the X-10R-1 epic. The pipeline
under test wires four merged layers into one deterministic
function:

    allocator → bank-level marginals → reconstruction → Gate 6
        → composed DoV → BankLevelForwardSignalCertificate

Two flags must NOT be conflated:

    is_admissible_for_downstream_bank_level_test  (necessary)
    is_scientifically_validated_bank_level_result (sufficient)

Sufficiency requires: composed DoV BOTH_WITHIN AND Gate 6 PASS
with a SIGNED precursor direction (FACILITATED or HINDERED, NOT
NO_SIGNAL).
"""

from __future__ import annotations

import pytest

from research.reconstruction.allocator import (
    ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT,
    BankLevelForwardSignalCertificate,
    ComposedDomainStatus,
    CountryToBankAllocator,
    SizeWeightedPrior,
    UniformPrior,
    assert_real_data_input_not_validated_here,
    composed_status_admits,
    emit_bank_level_forward_signal,
)
from research.reconstruction.allocator.data import MFI_DEMO_TSV
from research.reconstruction.allocator.mfi_loader import load_mfi_registry
from research.reconstruction.kuramoto_on_reconstruction import PrecursorDirection
from research.reconstruction.positive_control import (
    GroundTruthRecoveryCertificate,
    ground_truth_core_periphery,
    run_recovery_on_substrate,
)


def _within_recovery_cert(n: int, seed: int = 42) -> GroundTruthRecoveryCertificate:
    w = ground_truth_core_periphery(n=n, core_frac=0.30, seed=seed)
    return run_recovery_on_substrate(f"CP_{n}_e2e", w, seed=seed)


def _agg_for_demo() -> tuple[dict[str, float], dict[str, float]]:
    return (
        {"DE": 800.0, "FR": 700.0, "IT": 500.0, "ES": 450.0, "NL": 350.0},
        {"DE": 750.0, "FR": 660.0, "IT": 470.0, "ES": 420.0, "NL": 320.0},
    )


# ---------------------------------------------------------------------------
# Real-data contract
# ---------------------------------------------------------------------------


def test_real_data_input_path_is_explicitly_blocked() -> None:
    """Calling the pipeline with `is_synthetic_ground_truth=False`
    raises with INV-RECONSTRUCTION-2 + INV-IDENTIFICATION-1 named.
    Forbids the validation flag from leaking onto real data."""
    with pytest.raises(ValueError, match="INV-RECONSTRUCTION-2"):
        assert_real_data_input_not_validated_here(False)


def test_synthetic_path_is_admitted() -> None:
    """The synthetic-ground-truth path must NOT raise; it just
    returns None (the function is a fail-closed guard, not a value
    producer)."""
    assert_real_data_input_not_validated_here(True)


# ---------------------------------------------------------------------------
# Helper: composed_status_admits
# ---------------------------------------------------------------------------


def test_composed_status_admits_only_both_within() -> None:
    assert composed_status_admits(ComposedDomainStatus.BOTH_WITHIN) is True
    for s in (
        ComposedDomainStatus.RECONSTRUCTION_OUT,
        ComposedDomainStatus.ALLOCATOR_OUT,
        ComposedDomainStatus.BOTH_OUT,
    ):
        assert composed_status_admits(s) is False


# ---------------------------------------------------------------------------
# E2E pipeline — synthetic happy path
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_e2e_demo_fixture_emits_bank_level_certificate() -> None:
    """Load the frozen MFI demo fixture, build a SizeWeighted allocator,
    run the full pipeline. Must return a BankLevelForwardSignalCertificate
    with the two-property surface populated."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    rec_cert = _within_recovery_cert(n=out.n_rows, seed=42)
    agg_in, agg_out = _agg_for_demo()
    allocator = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out.bank_country_map,
            bank_weights=out.bank_weights,
            prior_id_tag="mfi_demo_v1",
        )
    )
    cert = emit_bank_level_forward_signal(
        country_aggregates_in=agg_in,
        country_aggregates_out=agg_out,
        bank_country_map=out.bank_country_map,
        allocator=allocator,
        recovery_certificate=rec_cert,
        cimini_target_density=0.05,
        bernoulli_seed=42,
        kuramoto_seed=42,
        kuramoto_n_bootstrap=8,
    )
    assert isinstance(cert, BankLevelForwardSignalCertificate)
    assert cert.bank_level_w_reconstructed_shape == (out.n_rows, out.n_rows)
    # Both flags must be present and bool.
    assert cert.is_admissible_for_downstream_bank_level_test in (True, False)
    assert cert.is_scientifically_validated_bank_level_result in (True, False)


@pytest.mark.slow
def test_e2e_validated_implies_admissible_and_signed_direction() -> None:
    """If the validation flag is True, the admissibility flag MUST
    be True AND the precursor direction MUST be signed (not NO_SIGNAL)."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    rec_cert = _within_recovery_cert(n=out.n_rows, seed=42)
    agg_in, agg_out = _agg_for_demo()
    cert = emit_bank_level_forward_signal(
        country_aggregates_in=agg_in,
        country_aggregates_out=agg_out,
        bank_country_map=out.bank_country_map,
        allocator=CountryToBankAllocator(
            prior=SizeWeightedPrior(
                bank_country_map=out.bank_country_map,
                bank_weights=out.bank_weights,
            )
        ),
        recovery_certificate=rec_cert,
    )
    if cert.is_scientifically_validated_bank_level_result:
        assert cert.is_admissible_for_downstream_bank_level_test is True
        assert cert.precursor_direction in (
            PrecursorDirection.SYNCHRONIZATION_FACILITATED,
            PrecursorDirection.SYNCHRONIZATION_HINDERED,
        )


@pytest.mark.slow
def test_e2e_admissible_does_not_imply_validated() -> None:
    """An admissible certificate MAY have validation False —
    Gate 6 PASS / NO_SIGNAL is independent of DoV. Pin the gap."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    rec_cert = _within_recovery_cert(n=out.n_rows, seed=42)
    agg_in, agg_out = _agg_for_demo()
    cert = emit_bank_level_forward_signal(
        country_aggregates_in=agg_in,
        country_aggregates_out=agg_out,
        bank_country_map=out.bank_country_map,
        allocator=CountryToBankAllocator(
            prior=SizeWeightedPrior(
                bank_country_map=out.bank_country_map,
                bank_weights=out.bank_weights,
            )
        ),
        recovery_certificate=rec_cert,
    )
    # Admissibility is True (composed DoV BOTH_WITHIN at matched
    # envelope). Validation may be either; the property is allowed
    # to be False without contradicting admissibility.
    assert cert.is_admissible_for_downstream_bank_level_test is True
    if not cert.is_scientifically_validated_bank_level_result:
        # NO_SIGNAL OR Gate 6 FAIL — both are legitimate "not yet
        # validated" outcomes.
        assert cert.kuramoto_certificate.passed is False or (
            cert.precursor_direction is PrecursorDirection.NO_SIGNAL
        )


# ---------------------------------------------------------------------------
# Fail-closed direction: when DoV not BOTH_WITHIN, validation is False
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_e2e_uniform_prior_low_coverage_yields_not_validated() -> None:
    """A `UniformPrior` over a SUBSET of countries (so coverage drops
    below 0.80) MUST yield is_scientifically_validated_bank_level_result
    = False, regardless of Gate 6. The gate is fail-closed on the
    necessary-condition layer."""
    out = load_mfi_registry(MFI_DEMO_TSV)
    rec_cert = _within_recovery_cert(n=out.n_rows, seed=42)
    agg_in, agg_out = _agg_for_demo()
    # Uniform with the same registry: coverage_ratio = 1.0 by
    # UniformPrior contract — it has "evidence" for every country
    # in its bank_country_map. To get LOW coverage we need a mismatch
    # between aggregates and the bank_country_map. Forge that:
    # only 2 of 5 countries get banks.
    truncated_bcm = tuple((b, c) for b, c in out.bank_country_map if c in {"DE", "FR"})
    allocator = CountryToBankAllocator(
        prior=UniformPrior(bank_country_map=truncated_bcm),
        fallback_policy="drop_country",
    )
    cert = emit_bank_level_forward_signal(
        country_aggregates_in=agg_in,
        country_aggregates_out=agg_out,
        bank_country_map=truncated_bcm,
        allocator=allocator,
        recovery_certificate=rec_cert,
    )
    # On a smaller bank_country_map the reconstruction's n_nodes
    # will not match the recovery_certificate's tested_at_n_nodes
    # envelope OR the allocator coverage will trip — either way,
    # validation must be False.
    assert cert.is_scientifically_validated_bank_level_result is False


# ---------------------------------------------------------------------------
# Pipeline shape contract
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_e2e_reconstructed_w_shape_matches_n_banks() -> None:
    out = load_mfi_registry(MFI_DEMO_TSV)
    rec_cert = _within_recovery_cert(n=out.n_rows, seed=42)
    agg_in, agg_out = _agg_for_demo()
    cert = emit_bank_level_forward_signal(
        country_aggregates_in=agg_in,
        country_aggregates_out=agg_out,
        bank_country_map=out.bank_country_map,
        allocator=CountryToBankAllocator(
            prior=SizeWeightedPrior(
                bank_country_map=out.bank_country_map,
                bank_weights=out.bank_weights,
            )
        ),
        recovery_certificate=rec_cert,
    )
    n = out.n_rows
    assert cert.bank_level_w_reconstructed_shape == (n, n)
    assert 0.0 <= cert.bank_level_inferred_density_estimate <= 1.0


# ---------------------------------------------------------------------------
# Kuramoto cert N >= 8 guard
# ---------------------------------------------------------------------------


def test_e2e_too_few_banks_yields_no_signal_not_crash() -> None:
    """If the bank-level network has < 8 banks the Kuramoto engine
    cannot run (it requires N ≥ 8). The pipeline must surface a
    NO_SIGNAL precursor direction and a non-validated certificate
    rather than crashing."""
    bcm = tuple((f"B{i}", "C0") for i in range(4))  # 4 banks → too few
    rec_cert = _within_recovery_cert(n=4, seed=42)  # mismatched on purpose
    cert = emit_bank_level_forward_signal(
        country_aggregates_in={"C0": 100.0},
        country_aggregates_out={"C0": 100.0},
        bank_country_map=bcm,
        allocator=CountryToBankAllocator(prior=UniformPrior(bank_country_map=bcm)),
        recovery_certificate=rec_cert,
    )
    assert cert.precursor_direction is PrecursorDirection.NO_SIGNAL
    assert cert.is_scientifically_validated_bank_level_result is False


# ---------------------------------------------------------------------------
# Default coverage threshold check via the helper
# ---------------------------------------------------------------------------


def test_default_coverage_threshold_value() -> None:
    """Sanity: the helper module exposes the same default."""
    assert ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT == 0.80
