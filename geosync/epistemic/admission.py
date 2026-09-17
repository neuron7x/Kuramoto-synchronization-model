"""Runtime admission controller for claim promotion."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping, Tuple

from .certificates import make_certificate
from .contracts import PromotionContract, default_contracts, validate_adjacent_transition
from .lineage import evaluate_oracle_independence
from .models import Claim, ClaimState, Evidence, NegativeEvidence, Oracle, PromotionCertificate


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    allowed: bool
    current_state: ClaimState
    target_state: ClaimState
    blockers: Tuple[str, ...]
    certificate: PromotionCertificate | None = None


def _evidence_blockers(
    claim: Claim,
    contract: PromotionContract,
    evidence: tuple[Evidence, ...],
) -> list[str]:
    blockers: list[str] = []
    valid_kinds = {e.kind for e in evidence if e.valid and e.claim_id == claim.claim_id}
    missing = sorted(k.value for k in contract.required_evidence - valid_kinds)
    if missing:
        blockers.append("missing evidence: " + ", ".join(missing))
    if any(e.claim_id != claim.claim_id for e in evidence):
        blockers.append("cross-claim evidence rejected")
    return blockers


def _negative_evidence_blockers(
    claim: Claim,
    contract: PromotionContract,
    negative: tuple[NegativeEvidence, ...],
) -> list[str]:
    blockers: list[str] = []
    active = [
        n
        for n in negative
        if n.claim_id == claim.claim_id and n.blocking and not n.resolved
    ]
    if contract.requires_clean_negative_evidence and active:
        blockers.append("unresolved blocking negative evidence")
    if any(n.claim_id != claim.claim_id for n in negative):
        blockers.append("cross-claim negative evidence rejected")
    return blockers


def _oracle_blockers(
    claim: Claim,
    contract: PromotionContract,
    oracles: tuple[Oracle, ...],
) -> list[str]:
    if not contract.requires_independent_oracle:
        return []
    reports = [evaluate_oracle_independence(claim, oracle) for oracle in oracles]
    if any(report.admissible for report in reports):
        return []
    return ["no admissible independent oracle"]


class AdmissionController:
    def __init__(
        self,
        contracts: Mapping[ClaimState, PromotionContract] | None = None,
        policy_version: str = "ECP-AS/0.1",
    ) -> None:
        self.contracts = dict(contracts or default_contracts())
        self.policy_version = policy_version

    def evaluate(
        self,
        claim: Claim,
        target: ClaimState,
        evidence: Iterable[Evidence],
        negative_evidence: Iterable[NegativeEvidence] = (),
        oracles: Iterable[Oracle] = (),
        *,
        falsifier_executed: bool = False,
    ) -> AdmissionDecision:
        validate_adjacent_transition(claim.state, target)
        contract = self.contracts.get(target)
        if contract is None:
            return AdmissionDecision(False, claim.state, target, ("no promotion contract",))

        ev = tuple(evidence)
        neg = tuple(negative_evidence)
        ors = tuple(oracles)
        blockers = _evidence_blockers(claim, contract, ev)
        blockers.extend(_negative_evidence_blockers(claim, contract, neg))
        blockers.extend(_oracle_blockers(claim, contract, ors))
        if contract.requires_falsifier_execution and not falsifier_executed:
            blockers.append("falsifier not executed")

        if blockers:
            return AdmissionDecision(
                False,
                claim.state,
                target,
                tuple(sorted(set(blockers))),
            )

        certificate = make_certificate(claim, target, ev, neg, ors, self.policy_version)
        return AdmissionDecision(True, claim.state, target, (), certificate)

    def promote(
        self,
        claim: Claim,
        target: ClaimState,
        evidence: Iterable[Evidence],
        negative_evidence: Iterable[NegativeEvidence] = (),
        oracles: Iterable[Oracle] = (),
        *,
        falsifier_executed: bool = False,
    ) -> tuple[Claim, AdmissionDecision]:
        decision = self.evaluate(
            claim,
            target,
            evidence,
            negative_evidence,
            oracles,
            falsifier_executed=falsifier_executed,
        )
        if not decision.allowed:
            return claim, decision
        return replace(claim, state=target), decision
