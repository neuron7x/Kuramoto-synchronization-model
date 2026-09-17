"""Canonical data model for evidence-carrying scientific claims."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Tuple

class ClaimState(str, Enum):
    UNOBSERVED = "UNOBSERVED"
    CONJECTURE = "CONJECTURE"
    TESTABLE = "TESTABLE"
    INSTRUMENTED = "INSTRUMENTED"
    OBSERVED = "OBSERVED"
    REPLICATED = "REPLICATED"
    BOUNDED = "BOUNDED"
    TRANSFER_TESTED = "TRANSFER_TESTED"
    FALSIFIED = "FALSIFIED"
    STALE = "STALE"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    CONFLICTED = "CONFLICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    RETIRED = "RETIRED"

PROMOTABLE_STATES: Tuple[ClaimState, ...] = (
    ClaimState.UNOBSERVED, ClaimState.CONJECTURE, ClaimState.TESTABLE,
    ClaimState.INSTRUMENTED, ClaimState.OBSERVED, ClaimState.REPLICATED,
    ClaimState.BOUNDED, ClaimState.TRANSFER_TESTED,
)

class EvidenceKind(str, Enum):
    OPERATIONAL_DEFINITION = "OPERATIONAL_DEFINITION"
    FALSIFIER_DEFINED = "FALSIFIER_DEFINED"
    INSTRUMENT = "INSTRUMENT"
    OBSERVATION = "OBSERVATION"
    REPLICATION = "REPLICATION"
    PROVENANCE = "PROVENANCE"
    REPLAY = "REPLAY"
    NULL_COMPARISON = "NULL_COMPARISON"
    BASELINE_COMPARISON = "BASELINE_COMPARISON"
    BOUNDARY = "BOUNDARY"
    TRANSFER_TEST = "TRANSFER_TEST"

class NegativeEvidenceKind(str, Enum):
    FAILED_NULL_COMPARISON = "FAILED_NULL_COMPARISON"
    INVALID_INPUT = "INVALID_INPUT"
    CALIBRATION_MISS = "CALIBRATION_MISS"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    EXTERNAL_ORACLE_DISAGREEMENT = "EXTERNAL_ORACLE_DISAGREEMENT"
    OOD_FAILURE = "OOD_FAILURE"
    MECHANISM_NONTRANSFER = "MECHANISM_NONTRANSFER"
    DATA_PROVENANCE_FAILURE = "DATA_PROVENANCE_FAILURE"
    VALIDATION_INVALID = "VALIDATION_INVALID"
    REPORTING_INCONSISTENCY = "REPORTING_INCONSISTENCY"
    INDEPENDENT_REPLICATION_FAILURE = "INDEPENDENT_REPLICATION_FAILURE"
    AUTHORSHIP_PROVENANCE_FAILURE = "AUTHORSHIP_PROVENANCE_FAILURE"

class OracleAxis(str, Enum):
    PROVENANCE = "P"
    CONTROL = "C"
    ACQUISITION = "A"
    INTERPRETATION = "I"

@dataclass(frozen=True, slots=True)
class OracleIndependence:
    provenance: bool
    control: bool
    acquisition: bool
    interpretation: bool

    @property
    def fully_independent(self) -> bool:
        return all((self.provenance, self.control, self.acquisition, self.interpretation))

@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    kind: EvidenceKind
    digest: str
    source: str
    version: str
    claim_id: str
    valid: bool = True
    metadata: Tuple[Tuple[str, str], ...] = ()

@dataclass(frozen=True, slots=True)
class NegativeEvidence:
    evidence_id: str
    kind: NegativeEvidenceKind
    digest: str
    claim_id: str
    blocking: bool
    resolved: bool = False
    note: str = ""

@dataclass(frozen=True, slots=True)
class Oracle:
    oracle_id: str
    claim_id: str
    digest: str
    independence: OracleIndependence
    ancestors: FrozenSet[str] = frozenset()
    admissible: bool = True

@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    proposition: str
    domain: str
    scope: str
    state: ClaimState = ClaimState.UNOBSERVED
    assumptions: Tuple[str, ...] = ()
    uncertainty: Tuple[str, ...] = ()
    invalidation_conditions: Tuple[str, ...] = ()
    version: str = "1"
    generator_ancestors: FrozenSet[str] = frozenset()

@dataclass(frozen=True, slots=True)
class PromotionCertificate:
    claim_id: str
    previous_state: ClaimState
    new_state: ClaimState
    proposition_digest: str
    evidence_digest: str
    oracle_digest: str
    negative_evidence_digest: str
    policy_version: str
    claim_version: str

@dataclass(frozen=True, slots=True)
class ExperimentCandidate:
    experiment_id: str
    expected_information_gain: float
    falsification_probability: float
    independence_gain: float
    cost: float
    tags: Tuple[str, ...] = field(default_factory=tuple)
