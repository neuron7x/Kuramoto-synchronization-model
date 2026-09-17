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

class AdmissionController:
    def __init__(self, contracts: Mapping[ClaimState, PromotionContract] | None=None,
                 policy_version: str="ECP-AS/0.1") -> None:
        self.contracts=dict(contracts or default_contracts())
        self.policy_version=policy_version

    def evaluate(self, claim: Claim, target: ClaimState, evidence: Iterable[Evidence],
                 negative_evidence: Iterable[NegativeEvidence]=(),
                 oracles: Iterable[Oracle]=(), *, falsifier_executed: bool=False) -> AdmissionDecision:
        validate_adjacent_transition(claim.state,target)
        contract=self.contracts.get(target)
        if contract is None:
            return AdmissionDecision(False, claim.state, target, ("no promotion contract",))
        ev=tuple(evidence); neg=tuple(negative_evidence); ors=tuple(oracles)
        blockers=[]
        valid_kinds={e.kind for e in ev if e.valid and e.claim_id==claim.claim_id}
        missing=sorted(k.value for k in contract.required_evidence-valid_kinds)
        if missing: blockers.append("missing evidence: "+", ".join(missing))
        if any(e.claim_id!=claim.claim_id for e in ev): blockers.append("cross-claim evidence rejected")
        if contract.requires_falsifier_execution and not falsifier_executed:
            blockers.append("falsifier not executed")
        active_blocking=[n for n in neg if n.claim_id==claim.claim_id and n.blocking and not n.resolved]
        if contract.requires_clean_negative_evidence and active_blocking:
            blockers.append("unresolved blocking negative evidence")
        if any(n.claim_id!=claim.claim_id for n in neg): blockers.append("cross-claim negative evidence rejected")
        if contract.requires_independent_oracle:
            reports=[evaluate_oracle_independence(claim,o) for o in ors]
            if not any(r.admissible for r in reports): blockers.append("no admissible independent oracle")
        if blockers:
            return AdmissionDecision(False, claim.state, target, tuple(sorted(set(blockers))))
        cert=make_certificate(claim,target,ev,neg,ors,self.policy_version)
        return AdmissionDecision(True, claim.state, target, (), cert)

    def promote(self, claim: Claim, target: ClaimState, evidence: Iterable[Evidence],
                negative_evidence: Iterable[NegativeEvidence]=(), oracles: Iterable[Oracle]=(),
                *, falsifier_executed: bool=False) -> tuple[Claim, AdmissionDecision]:
        decision=self.evaluate(claim,target,evidence,negative_evidence,oracles,
                               falsifier_executed=falsifier_executed)
        if not decision.allowed:
            return claim, decision
        return replace(claim,state=target), decision
