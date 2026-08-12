# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verdict emitter — closed enum, gate-checked.

emit_verdict() returns INVALID_INSTRUMENT or OUT_OF_SCOPE BEFORE running
the score function if the gating preconditions are not met. This is the
single chokepoint for any external claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from instrument_validation.discrimination import (
    DiscriminationReport,
    DiscriminationVerdict,
)
from instrument_validation.negative_control import NegativeControlCertificate
from instrument_validation.positive_control import PosControlCertificate
from instrument_validation.scope import InstrumentScope, scope_match


class ClaimTier(Enum):
    EXPLORATORY_DESCRIPTIVE = "exploratory_descriptive"
    VALIDATED_NEGATIVE = "validated_negative"
    NOT_DISTINGUISHED = "not_distinguished"
    INVALID_INSTRUMENT = "invalid_instrument"


class Verdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_DISTINGUISHED = "not_distinguished"
    INVALID_INSTRUMENT = "invalid_instrument"
    OUT_OF_SCOPE = "out_of_scope"


class ClaimType(Enum):
    DESCRIPTIVE_TOPOLOGY = "descriptive_topology"
    GENERATIVE_MECHANISM = "generative_mechanism"
    LIQUIDITY_CONTAGION_MODEL = "liquidity_contagion_model"


@dataclass(frozen=True)
class EmittedVerdict:
    verdict: Verdict
    claim_tier: ClaimTier
    reason: str
    discrimination_report: DiscriminationReport | None
    extra: dict[str, Any]


def emit_verdict(
    *,
    scope: InstrumentScope,
    pos_cert: PosControlCertificate | None,
    neg_cert: NegativeControlCertificate | None,
    discrimination: DiscriminationReport | None,
    runtime_substrate: str,
    runtime_n: int,
    runtime_density: float,
    runtime_obs_per_corr: int | None = None,
    claim_type: ClaimType = ClaimType.DESCRIPTIVE_TOPOLOGY,
) -> EmittedVerdict:
    """Single emission chokepoint. Order of checks is non-negotiable."""
    # 1. Scope match — fastest fail; never run score_fn out of regime.
    if not scope_match(
        scope,
        n=runtime_n,
        substrate=runtime_substrate,
        density=runtime_density,
        obs_per_corr=runtime_obs_per_corr,
    ):
        return EmittedVerdict(
            verdict=Verdict.OUT_OF_SCOPE,
            claim_tier=ClaimTier.INVALID_INSTRUMENT,
            reason=(
                f"runtime regime (n={runtime_n}, substrate={runtime_substrate!r}, "
                f"density={runtime_density:.3f}, obs_per_corr={runtime_obs_per_corr}) "
                f"outside declared scope ({scope.valid_for_substrate}, "
                f"n∈{scope.valid_for_n_range}, density∈{scope.valid_for_density_range})"
            ),
            discrimination_report=None,
            extra={"scope_id": scope.instrument_id},
        )
    # 2. Positive-control certificate must exist and validate this instrument.
    if pos_cert is None or not pos_cert.is_valid_for(scope.instrument_id):
        pos_reason = (
            pos_cert.failure_reason or "no failure reason recorded"
            if pos_cert is not None
            else "no certificate"
        )
        return EmittedVerdict(
            verdict=Verdict.INVALID_INSTRUMENT,
            claim_tier=ClaimTier.INVALID_INSTRUMENT,
            reason=f"positive-control certificate missing or invalid: {pos_reason}",
            discrimination_report=None,
            extra={"scope_id": scope.instrument_id},
        )
    # 3. Negative-control certificate must exist and validate this instrument.
    if neg_cert is None or not neg_cert.is_valid_for(scope.instrument_id):
        neg_reason = (
            neg_cert.failure_reason or "no failure reason recorded"
            if neg_cert is not None
            else "no certificate"
        )
        return EmittedVerdict(
            verdict=Verdict.INVALID_INSTRUMENT,
            claim_tier=ClaimTier.INVALID_INSTRUMENT,
            reason=f"negative-control certificate missing or invalid: {neg_reason}",
            discrimination_report=None,
            extra={"scope_id": scope.instrument_id},
        )
    # 4. Cross-model claims require a discrimination report.
    if claim_type is ClaimType.GENERATIVE_MECHANISM and discrimination is None:
        return EmittedVerdict(
            verdict=Verdict.INVALID_INSTRUMENT,
            claim_tier=ClaimTier.INVALID_INSTRUMENT,
            reason="generative-mechanism claim requires DiscriminationReport",
            discrimination_report=None,
            extra={"scope_id": scope.instrument_id},
        )
    # 5. For mechanism claims, require BA_FAVORED aggregate.
    if claim_type is ClaimType.GENERATIVE_MECHANISM and discrimination is not None:
        if discrimination.aggregate_verdict is DiscriminationVerdict.BA_FAVORED:
            return EmittedVerdict(
                verdict=Verdict.PASS,
                claim_tier=ClaimTier.VALIDATED_NEGATIVE,  # rare even when present
                reason="BA_FAVORED on ≥4/6 metrics after Bonferroni",
                discrimination_report=discrimination,
                extra={"scope_id": scope.instrument_id},
            )
        return EmittedVerdict(
            verdict=Verdict.NOT_DISTINGUISHED,
            claim_tier=ClaimTier.NOT_DISTINGUISHED,
            reason=(
                f"discrimination aggregate = {discrimination.aggregate_verdict.value}; "
                f"BA mechanism not uniquely identified at this N"
            ),
            discrimination_report=discrimination,
            extra={"scope_id": scope.instrument_id},
        )
    # 6. Liquidity-contagion claims are forbidden under country-aggregate scope.
    if claim_type is ClaimType.LIQUIDITY_CONTAGION_MODEL:
        return EmittedVerdict(
            verdict=Verdict.OUT_OF_SCOPE,
            claim_tier=ClaimTier.INVALID_INSTRUMENT,
            reason=(
                "liquidity-contagion claim requires bank-level substrate; "
                f"current substrate is {scope.valid_for_substrate}"
            ),
            discrimination_report=discrimination,
            extra={"scope_id": scope.instrument_id},
        )
    # 7. Descriptive topology — always allowed once scope + certs hold.
    return EmittedVerdict(
        verdict=Verdict.PASS,
        claim_tier=ClaimTier.EXPLORATORY_DESCRIPTIVE,
        reason="descriptive topology claim — scope + pos/neg cert satisfied",
        discrimination_report=discrimination,
        extra={"scope_id": scope.instrument_id},
    )
