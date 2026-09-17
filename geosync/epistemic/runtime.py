"""Authoritative ECP-AS runtime backed by a verified hash-chain ledger."""
from __future__ import annotations
from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Tuple
from .admission import AdmissionController, AdmissionDecision
from .ledger import HashChainLedger
from .models import (Claim, ClaimState, Evidence, EvidenceKind, NegativeEvidence, NegativeEvidenceKind, Oracle, OracleIndependence, PromotionCertificate)

DEGRADED_STATES=frozenset({ClaimState.FALSIFIED,ClaimState.STALE,ClaimState.OUT_OF_DOMAIN,ClaimState.CONFLICTED,ClaimState.INCONCLUSIVE,ClaimState.RETIRED})

def _norm(v: Any) -> Any:
    if isinstance(v,Enum): return v.value
    if isinstance(v,frozenset): return sorted(v)
    if isinstance(v,tuple): return [_norm(x) for x in v]
    if hasattr(v,"__dataclass_fields__"): return {k:_norm(getattr(v,k)) for k in v.__dataclass_fields__}
    if isinstance(v,dict): return {str(k):_norm(x) for k,x in v.items()}
    return v

class EpistemicRuntime:
    def __init__(self, ledger_path: str | Path, controller: AdmissionController | None=None) -> None:
        self.ledger=HashChainLedger(ledger_path)
        self.controller=controller or AdmissionController()

    def register_claim(self, claim: Claim) -> None:
        if claim.state is not ClaimState.UNOBSERVED:
            raise ValueError("claims must enter runtime at UNOBSERVED; pre-promoted claims are forbidden")
        if self.ledger.for_claim(claim.claim_id): raise ValueError("claim already registered")
        self.ledger.append("CLAIM_REGISTERED",claim.claim_id,_norm(claim))

    def _events(self, claim_id: str):
        events=self.ledger.for_claim(claim_id)
        if not events or events[0].event_type!="CLAIM_REGISTERED": raise KeyError(f"unknown claim {claim_id}")
        return events

    def claim(self, claim_id: str) -> Claim:
        events=self._events(claim_id); raw=events[0].payload
        claim=Claim(claim_id=raw["claim_id"],proposition=raw["proposition"],domain=raw["domain"],scope=raw["scope"],state=ClaimState(raw["state"]),assumptions=tuple(raw.get("assumptions",())),uncertainty=tuple(raw.get("uncertainty",())),invalidation_conditions=tuple(raw.get("invalidation_conditions",())),version=raw.get("version","1"),generator_ancestors=frozenset(raw.get("generator_ancestors",())))
        for e in events[1:]:
            if e.event_type=="PROMOTION_ALLOWED": claim=replace(claim,state=ClaimState(e.payload["new_state"]))
            elif e.event_type=="CLAIM_DEGRADED": claim=replace(claim,state=ClaimState(e.payload["new_state"]))
        return claim

    def evidence(self, claim_id: str) -> Tuple[Evidence,...]:
        out=[]
        for e in self._events(claim_id):
            if e.event_type!="EVIDENCE_ADDED": continue
            r=e.payload; out.append(Evidence(r["evidence_id"],EvidenceKind(r["kind"]),r["digest"],r["source"],r["version"],r["claim_id"],bool(r["valid"]),tuple(tuple(x) for x in r.get("metadata",()))))
        return tuple(out)

    def negative_evidence(self, claim_id: str) -> Tuple[NegativeEvidence,...]:
        out={}
        for e in self._events(claim_id):
            if e.event_type=="NEGATIVE_EVIDENCE_ADDED":
                r=e.payload; out[r["evidence_id"]]=NegativeEvidence(r["evidence_id"],NegativeEvidenceKind(r["kind"]),r["digest"],r["claim_id"],bool(r["blocking"]),bool(r["resolved"]),r.get("note",""))
            elif e.event_type=="NEGATIVE_EVIDENCE_RESOLVED":
                evidence_id=e.payload["evidence_id"]
                if evidence_id not in out: raise ValueError("negative-evidence resolution references unknown evidence")
                prior=out[evidence_id]
                out[evidence_id]=replace(prior,resolved=True,note=prior.note+" | resolved: "+e.payload["justification_ref"])
        return tuple(out[k] for k in sorted(out))

    def oracles(self, claim_id: str) -> Tuple[Oracle,...]:
        out=[]
        for e in self._events(claim_id):
            if e.event_type!="ORACLE_ADDED": continue
            r=e.payload; i=r["independence"]; ind=OracleIndependence(bool(i["provenance"]),bool(i["control"]),bool(i["acquisition"]),bool(i["interpretation"]))
            out.append(Oracle(r["oracle_id"],r["claim_id"],r["digest"],ind,frozenset(r.get("ancestors",())),bool(r.get("admissible",True))))
        return tuple(out)

    def add_evidence(self, evidence: Evidence) -> None:
        self._events(evidence.claim_id); self.ledger.append("EVIDENCE_ADDED",evidence.claim_id,_norm(evidence))

    def add_negative_evidence(self, evidence: NegativeEvidence) -> None:
        self._events(evidence.claim_id)
        if any(n.evidence_id==evidence.evidence_id for n in self.negative_evidence(evidence.claim_id)):
            raise ValueError("negative evidence id already exists; append a resolution event instead")
        self.ledger.append("NEGATIVE_EVIDENCE_ADDED",evidence.claim_id,_norm(evidence))

    def resolve_negative_evidence(self, claim_id: str, evidence_id: str, justification_ref: str) -> None:
        if not justification_ref: raise ValueError("resolution requires justification_ref")
        rows={n.evidence_id:n for n in self.negative_evidence(claim_id)}
        if evidence_id not in rows: raise KeyError(f"unknown negative evidence {evidence_id}")
        if rows[evidence_id].resolved: raise ValueError("negative evidence already resolved")
        self.ledger.append("NEGATIVE_EVIDENCE_RESOLVED",claim_id,{"evidence_id":evidence_id,"justification_ref":justification_ref})

    def add_oracle(self, oracle: Oracle) -> None:
        self._events(oracle.claim_id); self.ledger.append("ORACLE_ADDED",oracle.claim_id,_norm(oracle))

    def promote(self, claim_id: str, target: ClaimState, *, falsifier_executed: bool=False) -> AdmissionDecision:
        claim=self.claim(claim_id)
        if claim.state in DEGRADED_STATES: raise ValueError(f"degraded claim cannot be promoted: {claim.state.value}")
        decision=self.controller.evaluate(claim,target,self.evidence(claim_id),self.negative_evidence(claim_id),self.oracles(claim_id),falsifier_executed=falsifier_executed)
        if decision.allowed:
            self.ledger.append("PROMOTION_ALLOWED",claim_id,{"old_state":claim.state.value,"new_state":target.value,"certificate":_norm(decision.certificate)})
        else:
            self.ledger.append("PROMOTION_BLOCKED",claim_id,{"old_state":claim.state.value,"target_state":target.value,"blockers":list(decision.blockers)})
        return decision

    def degrade(self, claim_id: str, target: ClaimState, reason: str, evidence_ref: str) -> None:
        if target not in DEGRADED_STATES: raise ValueError("target is not a degradation/terminal state")
        if not reason or not evidence_ref: raise ValueError("degradation requires reason and evidence_ref")
        current=self.claim(claim_id)
        self.ledger.append("CLAIM_DEGRADED",claim_id,{"old_state":current.state.value,"new_state":target.value,"reason":reason,"evidence_ref":evidence_ref})

    def invalidate_claims(self, claim_ids: Iterable[str], *, reason: str, evidence_ref: str) -> Tuple[str,...]:
        changed=[]
        for claim_id in sorted(set(claim_ids)):
            current=self.claim(claim_id)
            if current.state in DEGRADED_STATES:
                continue
            self.degrade(claim_id,ClaimState.STALE,reason,evidence_ref)
            changed.append(claim_id)
        return tuple(changed)
    def apply_external_adjudication(self, event, *, policy=None):
        """Apply one externally grounded adjudication event exactly once.

        Editorial authority may invalidate an evidence artifact without being treated as
        an omniscient truth oracle.  Stronger states such as FALSIFIED remain policy-gated.
        """
        from .adjudication import (
            AdjudicationAction, ExternalAdjudicationPolicy,
        )

        self._events(event.claim_id)
        for row in self.ledger.for_claim(event.claim_id):
            if row.event_type == "EXTERNAL_ADJUDICATION_RECEIVED" and row.payload.get("event_id") == event.event_id:
                raise ValueError("external adjudication event already applied")

        policy = policy or ExternalAdjudicationPolicy()
        decision = policy.evaluate(event)
        self.ledger.append(
            "EXTERNAL_ADJUDICATION_RECEIVED",
            event.claim_id,
            {
                "event_id": event.event_id,
                "kind": event.kind.value,
                "authority": event.authority.value,
                "source_url": event.source_url,
                "source_digest": event.source_digest,
                "decision_action": decision.action.value,
                "decision_target": decision.target_state.value if decision.target_state else None,
            },
        )
        if decision.action is AdjudicationAction.DEGRADE:
            evidence = NegativeEvidence(
                evidence_id=f"external:{event.event_id}",
                kind=decision.negative_kind,
                digest=event.source_digest,
                claim_id=event.claim_id,
                blocking=True,
                resolved=False,
                note=decision.reason,
            )
            self.add_negative_evidence(evidence)
            self.degrade(
                event.claim_id,
                decision.target_state,
                reason=decision.reason,
                evidence_ref=event.source_url,
            )
        elif decision.action is AdjudicationAction.REVIEW_REQUIRED:
            self.ledger.append(
                "EXTERNAL_ADJUDICATION_REVIEW_REQUIRED",
                event.claim_id,
                {"event_id": event.event_id, "reason": decision.reason},
            )
        else:
            self.ledger.append(
                "EXTERNAL_ADJUDICATION_PRESERVED",
                event.claim_id,
                {"event_id": event.event_id, "reason": decision.reason},
            )
        return decision
