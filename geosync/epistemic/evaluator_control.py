"""Lineage-aware evaluator quorum control for ECP-AS.

This module does not judge scientific content. It controls whether a set of
external evaluator observations is sufficiently independent to authorize a
claim promotion. Scientific truth labels belong only to benchmark scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from enum import Enum
from itertools import combinations
from typing import Iterable

from .lineage import evaluate_oracle_independence
from .models import Claim, Oracle


class QuorumAction(str, Enum):
    PROMOTE = "PROMOTE"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class EvaluatorObservation:
    oracle: Oracle
    supports: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class QuorumDecision:
    action: QuorumAction
    support_count: int
    dissent_count: int
    admissible_count: int
    selected_oracle_ids: tuple[str, ...]
    excluded_oracle_ids: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def promoted(self) -> bool:
        return self.action is QuorumAction.PROMOTE


def _pairwise_independent_subset(
    observations: tuple[EvaluatorObservation, ...],
    *,
    allowed_shared: frozenset[str],
) -> tuple[EvaluatorObservation, ...]:
    """Return a deterministic maximum subset without pairwise lineage overlap.

    Oracle independence against the claim generator is necessary but not
    sufficient: two nominally external verifiers may still share a hidden
    declared upstream evaluator, dataset, credential, or actor.  For the small
    evaluator sets used by ECP-AS, exhaustive subset selection is clearer and
    easier to audit than a heuristic graph algorithm.
    """
    best: tuple[EvaluatorObservation, ...] = ()
    ordered = tuple(sorted(observations, key=lambda row: row.oracle.oracle_id))
    for size in range(1, len(ordered) + 1):
        for subset in combinations(ordered, size):
            valid = True
            for left, right in combinations(subset, 2):
                shared = (left.oracle.ancestors & right.oracle.ancestors) - allowed_shared
                if shared:
                    valid = False
                    break
            if valid:
                candidate = tuple(subset)
                if len(candidate) > len(best):
                    best = candidate
                elif len(candidate) == len(best):
                    cand_ids = tuple(row.oracle.oracle_id for row in candidate)
                    best_ids = tuple(row.oracle.oracle_id for row in best)
                    if cand_ids < best_ids:
                        best = candidate
    return best


def synthesize_quorum_oracle(
    claim: Claim,
    observations: Iterable[EvaluatorObservation],
    decision: QuorumDecision,
    *,
    oracle_id: str = "ecp-as:quorum",
) -> Oracle:
    """Create a proof-carrying aggregate oracle after a successful quorum decision.

    The digest binds the selected oracle ids, source digests, and support bits.
    The aggregate oracle can then be consumed by the existing AdmissionController
    without teaching that controller about evaluator voting semantics.
    """
    if not decision.promoted:
        raise ValueError("cannot synthesize authorization oracle from HOLD decision")
    by_id = {row.oracle.oracle_id: row for row in observations}
    selected = tuple(by_id[oid] for oid in decision.selected_oracle_ids)
    canonical = "|".join(
        f"{row.oracle.oracle_id}:{row.oracle.digest}:{int(row.supports)}" for row in selected
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    ancestors = frozenset().union(*(row.oracle.ancestors for row in selected))
    from .models import OracleIndependence

    return Oracle(
        oracle_id=oracle_id,
        claim_id=claim.claim_id,
        digest=digest,
        independence=OracleIndependence(True, True, True, True),
        ancestors=ancestors,
        admissible=True,
    )


class LineageQuorumPolicy:
    """Authorize only through a declared-independent external evaluator quorum."""

    name = "ecp_as_lineage_quorum"

    def __init__(
        self,
        *,
        min_admissible: int = 3,
        required_support: int = 2,
        allowed_shared: frozenset[str] = frozenset(),
    ) -> None:
        if min_admissible < 1:
            raise ValueError("min_admissible must be positive")
        if required_support < 1 or required_support > min_admissible:
            raise ValueError("required_support must be in [1, min_admissible]")
        self.min_admissible = min_admissible
        self.required_support = required_support
        self.allowed_shared = allowed_shared

    def decide(
        self,
        claim: Claim,
        observations: Iterable[EvaluatorObservation],
    ) -> QuorumDecision:
        rows = tuple(observations)
        admissible: list[EvaluatorObservation] = []
        excluded: list[str] = []
        blockers: list[str] = []

        for row in rows:
            if not row.oracle.ancestors:
                excluded.append(row.oracle.oracle_id)
                blockers.append(f"{row.oracle.oracle_id}: lineage not declared")
                continue
            report = evaluate_oracle_independence(claim, row.oracle, self.allowed_shared)
            if not report.admissible:
                excluded.append(row.oracle.oracle_id)
                blockers.append(f"{row.oracle.oracle_id}: {report.reason}")
                continue
            admissible.append(row)

        selected = _pairwise_independent_subset(
            tuple(admissible), allowed_shared=self.allowed_shared
        )
        selected_ids = {row.oracle.oracle_id for row in selected}
        for row in admissible:
            if row.oracle.oracle_id not in selected_ids:
                excluded.append(row.oracle.oracle_id)
                blockers.append(f"{row.oracle.oracle_id}: correlated declared lineage")

        support = sum(row.supports for row in selected)
        dissent = len(selected) - support
        if len(selected) < self.min_admissible:
            blockers.append(
                f"independent quorum unavailable: {len(selected)}/{self.min_admissible}"
            )
            action = QuorumAction.HOLD
        elif support < self.required_support:
            blockers.append(
                f"support quorum unmet: {support}/{self.required_support}"
            )
            action = QuorumAction.HOLD
        else:
            action = QuorumAction.PROMOTE

        return QuorumDecision(
            action=action,
            support_count=support,
            dissent_count=dissent,
            admissible_count=len(selected),
            selected_oracle_ids=tuple(row.oracle.oracle_id for row in selected),
            excluded_oracle_ids=tuple(sorted(set(excluded))),
            blockers=tuple(blockers),
        )
