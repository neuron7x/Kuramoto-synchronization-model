"""Fail-closed promotion contracts for claim-state transitions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import FrozenSet, Mapping
from .models import ClaimState, EvidenceKind, PROMOTABLE_STATES

@dataclass(frozen=True, slots=True)
class PromotionContract:
    target: ClaimState
    required_evidence: FrozenSet[EvidenceKind]
    requires_falsifier_execution: bool = False
    requires_independent_oracle: bool = False
    requires_clean_negative_evidence: bool = False

def default_contracts() -> Mapping[ClaimState, PromotionContract]:
    E=EvidenceKind
    return {
        ClaimState.CONJECTURE: PromotionContract(ClaimState.CONJECTURE, frozenset()),
        ClaimState.TESTABLE: PromotionContract(
            ClaimState.TESTABLE, frozenset({E.OPERATIONAL_DEFINITION, E.FALSIFIER_DEFINED})),
        ClaimState.INSTRUMENTED: PromotionContract(
            ClaimState.INSTRUMENTED, frozenset({E.INSTRUMENT, E.PROVENANCE})),
        ClaimState.OBSERVED: PromotionContract(
            ClaimState.OBSERVED, frozenset({E.OBSERVATION, E.PROVENANCE}),
            requires_falsifier_execution=True),
        ClaimState.REPLICATED: PromotionContract(
            ClaimState.REPLICATED, frozenset({E.REPLICATION, E.REPLAY, E.PROVENANCE}),
            requires_falsifier_execution=True, requires_independent_oracle=True,
            requires_clean_negative_evidence=True),
        ClaimState.BOUNDED: PromotionContract(
            ClaimState.BOUNDED, frozenset({E.NULL_COMPARISON, E.BASELINE_COMPARISON, E.BOUNDARY, E.REPLAY, E.PROVENANCE}),
            requires_falsifier_execution=True, requires_independent_oracle=True,
            requires_clean_negative_evidence=True),
        ClaimState.TRANSFER_TESTED: PromotionContract(
            ClaimState.TRANSFER_TESTED, frozenset({E.TRANSFER_TEST, E.BOUNDARY, E.REPLAY, E.PROVENANCE}),
            requires_falsifier_execution=True, requires_independent_oracle=True,
            requires_clean_negative_evidence=True),
    }

def validate_adjacent_transition(current: ClaimState, target: ClaimState) -> None:
    if current not in PROMOTABLE_STATES or target not in PROMOTABLE_STATES:
        raise ValueError("terminal/degraded states cannot be used as promotion rungs")
    ci=PROMOTABLE_STATES.index(current); ti=PROMOTABLE_STATES.index(target)
    if ti != ci + 1:
        raise ValueError(f"state skipping forbidden: {current.value} -> {target.value}")
