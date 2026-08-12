# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end bank-level forward-signal pipeline (X-10R-1 PR #7 — FINAL).

This is the closing PR of the X-10R-1 epic. It wires the four
layers built in PRs #642–#646 into a single deterministic
function and emits a `BankLevelForwardSignalCertificate` that
finally distinguishes admissibility from validation.

Pipeline
========

    country aggregates                    (input)
        ⬇  CountryToBankAllocator + AllocatorPrior      [#642 + #643]
    bank-level marginals (s_in, s_out)
        ⬇  fit_cimini_squartini + IPF                   [PR #635]
    bank-level reconstructed adjacency W_recon
        ⬇  audit_recovery (Gate 5)                      [PR #635]
    GroundTruthRecoveryCertificate (synthetic side only)
        ⬇  gate_6_precursor_discriminative              [PR #635]
    Kuramoto R(∞) precursor verdict
        ⬇  check_composed_domain_of_validity            [PR #6, this epic]
    ComposedDomainCheck
        ⬇
    BankLevelForwardSignalCertificate

Contract
========

The certificate has TWO flags that must NOT be conflated:

    is_admissible_for_downstream_bank_level_test
        True iff composed DoV verdict is BOTH_WITHIN. This is
        the *necessary* prerequisite — the inputs are inside
        the regime where Gate 6 is well-defined.

    is_scientifically_validated_bank_level_result
        True iff (admissible AND Gate 6 PASS with a SIGNED
        precursor direction). This is the *sufficient* condition
        for emitting a bank-level forward signal.

Synthetic positive control vs real data
========================================

This module's PASS path covers SYNTHETIC ground truth — the only
substrate where we have a known network to reconstruct against.
On real BIS LBS marginals the validation flag has no meaning at
this layer because there is no bank-level ground truth (see
INV-RECONSTRUCTION-2 / INV-IDENTIFICATION-1). The flag is set
SOLELY by the synthetic-substrate pipeline; running this on real
data is a contract violation enforced by
`assert_real_data_input_not_validated_here`.

Lifting INV-IDENTIFICATION-1
============================

When this module's pipeline returns a certificate with
`is_scientifically_validated_bank_level_result == True` on a
SYNTHETIC substrate, the X-10R-1 epic is closed: the foundation
proves that an end-to-end allocator → reconstruction → Gate 6
forward signal CAN be emitted. Real-data inference is a
separate question (epic X-10R-3 / X-10R-4) and remains forbidden
by INV-IDENTIFICATION-1 until those epic layers land.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from research.reconstruction.allocator.allocator import CountryToBankAllocator
from research.reconstruction.allocator.dov_composition import (
    ComposedDomainCheck,
    ComposedDomainStatus,
    check_composed_domain_of_validity,
)
from research.reconstruction.cimini_squartini import (
    fit_cimini_squartini,
    p_link,
)
from research.reconstruction.kuramoto_on_reconstruction import (
    KuramotoRecoveryCertificate,
    PrecursorDirection,
    issue_kuramoto_recovery_certificate,
)
from research.reconstruction.positive_control import (
    GroundTruthRecoveryCertificate,
)
from research.reconstruction.weighted_allocation import (
    allocate_weights,
    sample_adjacency_bernoulli,
)


@dataclass(frozen=True)
class BankLevelForwardSignalCertificate:
    """Final closing certificate of the X-10R-1 epic.

    Carries both:
      * the per-layer artefacts (allocator + reconstruction +
        composed DoV verdict + Gate 6 verdict) for full audit
      * the two-property admissibility / validation surface the
        downstream consumer reads
    """

    composed_check: ComposedDomainCheck
    kuramoto_certificate: KuramotoRecoveryCertificate
    bank_level_w_reconstructed_shape: tuple[int, int]
    bank_level_inferred_density_estimate: float

    @property
    def is_admissible_for_downstream_bank_level_test(self) -> bool:
        """Necessary condition. True iff composed DoV verdict is
        BOTH_WITHIN — meaning the Gate 6 forward signal is
        well-defined on these inputs."""
        return self.composed_check.is_admissible_for_downstream_bank_level_test

    @property
    def is_scientifically_validated_bank_level_result(self) -> bool:
        """Sufficient condition. True iff:

        * `is_admissible_for_downstream_bank_level_test` is True
          (composed DoV verdict is BOTH_WITHIN), AND
        * Gate 6 precursor PASSES with a *signed* direction —
          either FACILITATED or HINDERED, NOT NO_SIGNAL.
        """
        if not self.is_admissible_for_downstream_bank_level_test:
            return False
        if not self.kuramoto_certificate.passed:
            return False
        return self.kuramoto_certificate.report.direction is not PrecursorDirection.NO_SIGNAL

    @property
    def precursor_direction(self) -> PrecursorDirection:
        return self.kuramoto_certificate.report.direction


def assert_real_data_input_not_validated_here(
    is_synthetic_ground_truth: bool,
) -> None:
    """Contract: this module sets `is_scientifically_validated_bank_
    level_result == True` only on SYNTHETIC substrates with known
    ground truth. On real BIS LBS marginals there is no bank-level
    truth (INV-RECONSTRUCTION-2), so this flag has no meaning and
    the caller must NOT use this pipeline as a real-data validator.
    """
    if not is_synthetic_ground_truth:
        raise ValueError(
            "INV-RECONSTRUCTION-2 + INV-IDENTIFICATION-1 VIOLATED: "
            "BankLevelForwardSignalCertificate is only valid on "
            "synthetic substrates with known ground truth. Real BIS "
            "LBS path requires a separate (out-of-epic) layer; do "
            "NOT call this module on real marginals."
        )


def emit_bank_level_forward_signal(
    *,
    country_aggregates_in: dict[str, float],
    country_aggregates_out: dict[str, float],
    bank_country_map: tuple[tuple[str, str], ...],
    allocator: CountryToBankAllocator,
    recovery_certificate: GroundTruthRecoveryCertificate,
    cimini_target_density: float = 0.05,
    bernoulli_seed: int = 42,
    kuramoto_seed: int = 42,
    kuramoto_n_bootstrap: int = 8,
    is_synthetic_ground_truth: bool = True,
) -> BankLevelForwardSignalCertificate:
    """Run the full X-10R-1 forward-signal pipeline.

    Steps:
      1. Allocator splits country aggregates → bank-level marginals.
      2. Cimini-Squartini fitness fit + Bernoulli sampling + IPF
         projection reconstruct a directed weighted bank-level
         adjacency W_recon.
      3. Kuramoto R(∞) precursor (Gate 6) on W_recon vs
         topology-randomised null.
      4. Composed DoV gate: real-like bank-level marginals against
         the supplied recovery_certificate envelope AND the
         allocator's own coverage envelope.
      5. Build BankLevelForwardSignalCertificate carrying both
         per-layer artefacts and the two-property admissibility/
         validation surface.

    `is_synthetic_ground_truth` is mandatory (default True) — this
    pipeline's validation flag has no meaning on real data; the
    contract is enforced upstream by
    `assert_real_data_input_not_validated_here`.
    """
    assert_real_data_input_not_validated_here(is_synthetic_ground_truth)

    # Step 1 — allocator
    bank_cert = allocator.allocate(
        country_aggregates_in,
        country_aggregates_out,
        bank_country_map=bank_country_map,
    )

    # Step 2 — bank-level reconstruction (Cimini + Bernoulli + IPF)
    fit = fit_cimini_squartini(
        bank_cert.s_out, bank_cert.s_in, target_density=cimini_target_density
    )
    p = p_link(fit.x, fit.y, fit.z)
    rng = np.random.default_rng(bernoulli_seed)
    a = sample_adjacency_bernoulli(p, rng=rng)
    w_recon = allocate_weights(a, bank_cert.s_out, bank_cert.s_in)
    inferred_density = float((w_recon > 0).sum() / max(w_recon.size - w_recon.shape[0], 1))

    # Step 3 — Gate 6
    n_required = 8
    gate6_cert: KuramotoRecoveryCertificate
    if w_recon.shape[0] >= n_required:
        gate6_cert = issue_kuramoto_recovery_certificate(
            w_recon, seed=kuramoto_seed, n_bootstrap=kuramoto_n_bootstrap
        )
    else:
        # Too few banks for Gate 6 (engine requires N ≥ 8). Build a
        # certificate that explicitly signals NO_SIGNAL.
        from research.reconstruction.kuramoto_on_reconstruction import (
            PrecursorReport,
        )

        report = PrecursorReport(
            n_nodes=w_recon.shape[0],
            k_test=0.0,
            n_bootstrap=0,
            r_recon_median=0.0,
            r_shuffled_median=0.0,
            delta_r_median=0.0,
            delta_r_ci_low=0.0,
            delta_r_ci_high=0.0,
            min_precursor_gap=0.0,
            passed=False,
            failure_reason=f"too few banks for Gate 6: N={w_recon.shape[0]} < 8",
            direction=PrecursorDirection.NO_SIGNAL,
        )
        gate6_cert = KuramotoRecoveryCertificate(
            n_nodes=w_recon.shape[0],
            report=report,
            passed=False,
            cert_id="0" * 64,
        )

    # Step 4 — composed DoV gate
    composed = check_composed_domain_of_validity(
        bank_cert.s_out,
        bank_cert.s_in,
        recovery_certificate=recovery_certificate,
        allocator_certificate=bank_cert,
        reconstruction_inferred_density=cimini_target_density,
    )

    return BankLevelForwardSignalCertificate(
        composed_check=composed,
        kuramoto_certificate=gate6_cert,
        bank_level_w_reconstructed_shape=(w_recon.shape[0], w_recon.shape[1]),
        bank_level_inferred_density_estimate=inferred_density,
    )


def composed_status_admits(
    status: ComposedDomainStatus,
) -> bool:
    """Helper: only BOTH_WITHIN admits the next-step test."""
    return status is ComposedDomainStatus.BOTH_WITHIN
