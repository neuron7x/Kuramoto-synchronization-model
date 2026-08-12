# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Composed Domain-of-Validity ADMISSIBILITY gate (X-10R-1 PR #6).

NAMING DISCIPLINE (per ILS-2026 critique on PR #646)
====================================================
This gate certifies *admissibility*, NOT *validity*. A `BOTH_WITHIN`
verdict means the inputs fall inside the regime where downstream
testing IS DEFINED — it does NOT mean the bank-level marginals are
scientifically validated. Validity requires a downstream Gate 6
forward signal on the reconstructed bank-level network. This is
deliberately a *necessary* condition, not a sufficient one.

Concretely:

    is_admissible_for_downstream_bank_level_test == True
        ⇏ is_scientifically_validated_bank_level_result == True

The latter is set by a separate Gate 6 layer (epic PR #7). Both
flags appear on `ComposedDomainCheck` so a downstream consumer
cannot accidentally treat admissibility as validation.

WHY ARCHITECTURE
================
Per epic #638: a real-data bank-level run becomes admissible only
if BOTH the country-to-bank ALLOCATOR layer AND the X-10R
RECONSTRUCTION layer certify the inputs. Each layer's
domain-of-validity is independent — the allocator's certificate
envelope (registry size, coverage_ratio, reciprocity / size-signal
evidence) is orthogonal to the reconstruction's envelope (n_nodes,
density, network reciprocity). Lifting one layer's WITHIN to a
bank-level claim without the other's WITHIN would smuggle an
unverified assumption into the verdict.

This module ships the *composition surface*:

    check_composed_domain_of_validity(
        s_out_real, s_in_real,
        recovery_certificate=...,         # X-10R reconstruction cert
        allocator_certificate=...,        # bank-level allocator cert
        reconstruction_inferred_density=...,
    ) -> ComposedDomainCheck

The composed verdict semantics:

    BOTH_WITHIN          recovery + allocator both WITHIN
    RECONSTRUCTION_OUT   recovery layer says OUT or INSUFFICIENT
    ALLOCATOR_OUT        allocator layer says OUT or INSUFFICIENT
    BOTH_OUT             both layers fail

Composition is FAIL-CLOSED: anything other than `BOTH_WITHIN`
forbids the next-step downstream test. INV-IDENTIFICATION-1
stays in force until BOTH `BOTH_WITHIN` clears AND a downstream
Gate 6 forward signal lands.

COVERAGE RATIO IS NECESSARY, NOT SUFFICIENT
============================================
The default coverage threshold (`ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT
= 0.80`) answers: "did the prior have evidence for ≥ 80 % of
countries?". It does NOT answer: "is that evidence informative
enough to allocate country aggregates correctly?". Coverage is a
necessary condition — without it the prior is degenerate — but it
is NOT sufficient. Sufficiency requires real-data validation
landing in epic PR #7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from research.reconstruction.allocator.certificate import (
    BankLevelMarginalsCertificate,
)
from research.reconstruction.recovery_audit import (
    DomainCheck,
    DomainOfValidityStatus,
    check_domain_of_validity,
)


class ComposedDomainStatus(Enum):
    """Verdict surface of the composed gate.

    Disjoint from the per-layer DomainOfValidityStatus to keep
    bank-level admissibility strictly ABOVE the per-layer surface
    in the type hierarchy (a caller cannot accidentally pass a
    DomainOfValidityStatus where ComposedDomainStatus is required).
    """

    BOTH_WITHIN = "both_within_validated_domain"
    RECONSTRUCTION_OUT = "reconstruction_out_of_validated_domain"
    ALLOCATOR_OUT = "allocator_out_of_validated_domain"
    BOTH_OUT = "both_out_of_validated_domain"


@dataclass(frozen=True)
class ComposedDomainCheck:
    """Frozen composite verdict.

    Carries the per-layer DomainCheck (from recovery_audit) AND the
    allocator-side per-dimension envelope checks. Both layers are
    surfaced separately so a downstream consumer can show the user
    *which* layer caused a NOT-BOTH-WITHIN verdict.
    """

    status: ComposedDomainStatus
    reconstruction_check: DomainCheck
    allocator_checks: dict[str, bool] = field(default_factory=dict)
    allocator_measured: dict[str, float] = field(default_factory=dict)
    allocator_envelope: dict[str, tuple[float, float]] = field(default_factory=dict)
    notes: str = ""

    @property
    def is_admissible_for_downstream_bank_level_test(self) -> bool:
        """Single boolean for downstream consumers. True iff the
        composed verdict is BOTH_WITHIN — meaning the *next-step*
        test (Gate 6 forward signal in epic PR #7) is well-defined
        on these inputs.

        This is admissibility, NOT validation. A True here is
        *necessary* but NOT *sufficient* for a bank-level claim.
        The full validation contract requires
        `is_scientifically_validated_bank_level_result` to also
        be True (set only by a Gate 6 PASS in epic PR #7)."""
        return self.status is ComposedDomainStatus.BOTH_WITHIN

    @property
    def is_scientifically_validated_bank_level_result(self) -> bool:
        """Always False at this layer. Validation requires a Gate 6
        forward signal on the reconstructed bank-level network,
        which is owned by epic PR #7. This property exists so a
        downstream consumer that tries to use `is_admissible_…` as
        a validation flag will fail loudly: validation lives on a
        DIFFERENT property and is set by a DIFFERENT layer."""
        return False


# Default thresholds for the allocator-side composition layer.
# coverage_ratio_min: by default we require the allocator to have
# real evidence for ≥ 80 % of the countries it allocated to (the
# fallback policy explains the rest, but full evidence is the
# admissibility bar).
ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT: float = 0.80
"""Default coverage_ratio threshold for the composed gate."""


def check_composed_domain_of_validity(
    s_out_real: np.ndarray,
    s_in_real: np.ndarray,
    *,
    recovery_certificate: object,  # GroundTruthRecoveryCertificate
    allocator_certificate: BankLevelMarginalsCertificate,
    reconstruction_inferred_density: float,
    allocator_coverage_ratio_min: float = ALLOCATOR_COVERAGE_RATIO_MIN_DEFAULT,
) -> ComposedDomainCheck:
    """Compose the X-10R reconstruction DoV gate with the allocator's
    own coverage / fallback envelope.

    Returns
    -------
    ComposedDomainCheck — see verdict matrix in module docstring.
    """
    # Layer 1: reconstruction-side DoV (existing X-10R surface).
    recovery_check = check_domain_of_validity(
        s_out_real,
        s_in_real,
        recovery_certificate,  # type: ignore[arg-type]
        inferred_density=reconstruction_inferred_density,
    )

    # Layer 2: allocator-side admissibility envelope.
    allocator_checks: dict[str, bool] = {}
    allocator_measured: dict[str, float] = {}
    allocator_envelope: dict[str, tuple[float, float]] = {}

    # coverage_ratio is the gate-able allocator metric; defaults
    # require ≥ 0.80 of countries to have real prior evidence.
    coverage_ok = allocator_certificate.coverage_ratio >= allocator_coverage_ratio_min
    allocator_checks["coverage_ratio"] = coverage_ok
    allocator_measured["coverage_ratio"] = float(allocator_certificate.coverage_ratio)
    allocator_envelope["coverage_ratio"] = (
        float(allocator_coverage_ratio_min),
        1.0,
    )

    # Provenance fields surfaced (informational, not gated):
    allocator_measured["n_banks"] = float(allocator_certificate.n_banks)
    allocator_measured["n_countries"] = float(allocator_certificate.n_countries)

    allocator_within = all(allocator_checks.values())
    reconstruction_within = recovery_check.status is DomainOfValidityStatus.WITHIN_VALIDATED_DOMAIN

    if reconstruction_within and allocator_within:
        status = ComposedDomainStatus.BOTH_WITHIN
        notes = "both layers certify; bank-level claim admissible"
    elif not reconstruction_within and not allocator_within:
        status = ComposedDomainStatus.BOTH_OUT
        notes = (
            f"reconstruction: {recovery_check.notes}; "
            f"allocator: coverage_ratio={allocator_certificate.coverage_ratio:.3f} "
            f"< {allocator_coverage_ratio_min}"
        )
    elif not reconstruction_within:
        status = ComposedDomainStatus.RECONSTRUCTION_OUT
        notes = f"reconstruction layer out: {recovery_check.notes}"
    else:
        status = ComposedDomainStatus.ALLOCATOR_OUT
        notes = (
            f"allocator coverage_ratio={allocator_certificate.coverage_ratio:.3f} "
            f"< {allocator_coverage_ratio_min}"
        )

    return ComposedDomainCheck(
        status=status,
        reconstruction_check=recovery_check,
        allocator_checks=allocator_checks,
        allocator_measured=allocator_measured,
        allocator_envelope=allocator_envelope,
        notes=notes,
    )
