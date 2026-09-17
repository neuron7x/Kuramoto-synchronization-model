"""Oracle-independence evaluation with explicit lineage overlap."""
from __future__ import annotations
from dataclasses import dataclass
from typing import FrozenSet
from .models import Claim, Oracle

@dataclass(frozen=True, slots=True)
class IndependenceReport:
    admissible: bool
    shared_ancestors: FrozenSet[str]
    axes_pass: bool
    reason: str

def evaluate_oracle_independence(
    claim: Claim, oracle: Oracle, allowed_shared: FrozenSet[str] = frozenset()
) -> IndependenceReport:
    if oracle.claim_id != claim.claim_id:
        return IndependenceReport(False, frozenset(), False, "oracle bound to different claim")
    shared=(claim.generator_ancestors & oracle.ancestors) - allowed_shared
    axes=oracle.independence.fully_independent and oracle.admissible
    if shared:
        return IndependenceReport(False, frozenset(shared), axes, "hidden common ancestry")
    if not axes:
        return IndependenceReport(False, frozenset(), False, "P/C/A/I independence incomplete")
    return IndependenceReport(True, frozenset(), True, "independent")
