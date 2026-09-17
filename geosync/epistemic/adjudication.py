"""External adjudication semantics for ECP-AS.

External actions are not treated as omniscient truth oracles.  The policy
separates (a) authority to invalidate an evidence artifact from (b) technical
independence sufficient to falsify a scientific proposition.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet

from .models import ClaimState, NegativeEvidenceKind


class AdjudicationKind(str, Enum):
    EDITORIAL_RETRACTION = "EDITORIAL_RETRACTION"
    EDITORIAL_CORRECTION = "EDITORIAL_CORRECTION"
    EDITORIAL_ADDENDUM = "EDITORIAL_ADDENDUM"
    INDEPENDENT_REPLICATION = "INDEPENDENT_REPLICATION"


class AuthorityClass(str, Enum):
    PUBLISHER_EDITORIAL = "PUBLISHER_EDITORIAL"
    INDEPENDENT_SCHOLARLY = "INDEPENDENT_SCHOLARLY"


class IndependenceLevel(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


class DefectClass(str, Enum):
    ADMINISTRATIVE_METADATA = "ADMINISTRATIVE_METADATA"
    METHODOLOGICAL_EXTENSION = "METHODOLOGICAL_EXTENSION"
    DATA_PROVENANCE_INVALID = "DATA_PROVENANCE_INVALID"
    VALIDATION_METHODOLOGY_INVALID = "VALIDATION_METHODOLOGY_INVALID"
    REPORTING_INCONSISTENCY = "REPORTING_INCONSISTENCY"
    METHOD_VALIDITY = "METHOD_VALIDITY"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    AUTHORSHIP_PROVENANCE = "AUTHORSHIP_PROVENANCE"
    REFERENCE_INTEGRITY = "REFERENCE_INTEGRITY"
    INDEPENDENT_REPLICATION_FAILURE = "INDEPENDENT_REPLICATION_FAILURE"


class AdjudicationAction(str, Enum):
    PRESERVE = "PRESERVE"
    DEGRADE = "DEGRADE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class ExternalAdjudicationEvent:
    event_id: str
    claim_id: str
    kind: AdjudicationKind
    authority: AuthorityClass
    source_url: str
    source_title: str
    source_date: str
    source_digest: str
    defects: FrozenSet[DefectClass]
    source_authenticity_verified: bool
    independence_level: IndependenceLevel
    explicit_conclusions_unsupported: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class AdjudicationDecision:
    action: AdjudicationAction
    target_state: ClaimState | None
    negative_kind: NegativeEvidenceKind | None
    reason: str

    @property
    def degrades(self) -> bool:
        return self.action is AdjudicationAction.DEGRADE


class ExternalAdjudicationPolicy:
    """Map externally grounded events to conservative claim-state changes."""

    def evaluate(self, event: ExternalAdjudicationEvent) -> AdjudicationDecision:
        if not event.source_authenticity_verified:
            return AdjudicationDecision(
                AdjudicationAction.REVIEW_REQUIRED,
                None,
                None,
                "source authenticity is not verified",
            )

        defects = event.defects
        if not defects or defects <= {
            DefectClass.ADMINISTRATIVE_METADATA,
            DefectClass.METHODOLOGICAL_EXTENSION,
        }:
            return AdjudicationDecision(
                AdjudicationAction.PRESERVE,
                None,
                None,
                "external action does not invalidate scientific evidence",
            )

        if DefectClass.VALIDATION_METHODOLOGY_INVALID in defects:
            # Falsification is stronger than evidence retirement. Require both an
            # explicit unsupported-conclusion finding and verified technical independence.
            if (
                event.explicit_conclusions_unsupported
                and event.independence_level is IndependenceLevel.VERIFIED
            ):
                return AdjudicationDecision(
                    AdjudicationAction.DEGRADE,
                    ClaimState.FALSIFIED,
                    NegativeEvidenceKind.VALIDATION_INVALID,
                    "independent validation found the reported conclusion unsupported",
                )
            return AdjudicationDecision(
                AdjudicationAction.DEGRADE,
                ClaimState.INCONCLUSIVE,
                NegativeEvidenceKind.VALIDATION_INVALID,
                "validation methodology is materially invalid but falsification threshold is unmet",
            )

        if DefectClass.INDEPENDENT_REPLICATION_FAILURE in defects:
            return AdjudicationDecision(
                AdjudicationAction.DEGRADE,
                ClaimState.CONFLICTED,
                NegativeEvidenceKind.INDEPENDENT_REPLICATION_FAILURE,
                "independent evidence conflicts with the promoted claim",
            )

        if defects & {
            DefectClass.DATA_PROVENANCE_INVALID,
            DefectClass.DATA_UNAVAILABLE,
            DefectClass.AUTHORSHIP_PROVENANCE,
        }:
            kind = (
                NegativeEvidenceKind.AUTHORSHIP_PROVENANCE_FAILURE
                if DefectClass.AUTHORSHIP_PROVENANCE in defects
                else NegativeEvidenceKind.DATA_PROVENANCE_FAILURE
            )
            return AdjudicationDecision(
                AdjudicationAction.DEGRADE,
                ClaimState.STALE,
                kind,
                "supporting evidence is no longer admissible or independently auditable",
            )

        if defects & {
            DefectClass.REPORTING_INCONSISTENCY,
            DefectClass.METHOD_VALIDITY,
            DefectClass.REFERENCE_INTEGRITY,
        }:
            return AdjudicationDecision(
                AdjudicationAction.DEGRADE,
                ClaimState.INCONCLUSIVE,
                NegativeEvidenceKind.REPORTING_INCONSISTENCY,
                "external adjudication undermines reproducible interpretation of the evidence",
            )

        return AdjudicationDecision(
            AdjudicationAction.REVIEW_REQUIRED,
            None,
            None,
            "material external event has no declared transition rule",
        )
