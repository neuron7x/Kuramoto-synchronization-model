"""Deterministic certificate construction."""
from __future__ import annotations
import hashlib, json
from typing import Iterable
from .models import Claim, ClaimState, Evidence, NegativeEvidence, Oracle, PromotionCertificate

def _hash_rows(rows: Iterable[object]) -> str:
    payload=[]
    for row in rows:
        if hasattr(row, "__dataclass_fields__"):
            item={name:getattr(row,name) for name in row.__dataclass_fields__}
            for k,v in list(item.items()):
                if hasattr(v, "value"): item[k]=v.value
                elif isinstance(v, frozenset): item[k]=sorted(v)
                elif hasattr(v, "__dataclass_fields__"):
                    item[k]={n:(getattr(v,n).value if hasattr(getattr(v,n),"value") else getattr(v,n)) for n in v.__dataclass_fields__}
            payload.append(item)
        else: payload.append(str(row))
    blob=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()
    return hashlib.sha256(blob).hexdigest()

def make_certificate(claim: Claim, target: ClaimState, evidence: Iterable[Evidence],
                     negative: Iterable[NegativeEvidence], oracles: Iterable[Oracle],
                     policy_version: str) -> PromotionCertificate:
    proposition_digest=hashlib.sha256(claim.proposition.encode()).hexdigest()
    return PromotionCertificate(
        claim_id=claim.claim_id, previous_state=claim.state, new_state=target,
        proposition_digest=proposition_digest, evidence_digest=_hash_rows(evidence),
        oracle_digest=_hash_rows(oracles), negative_evidence_digest=_hash_rows(negative),
        policy_version=policy_version, claim_version=claim.version)
