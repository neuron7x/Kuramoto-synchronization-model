"""Distributionally robust quorum-risk bounds for ECP-AS.

Marginal evaluator error rates do not identify joint error dependence.  This
module computes exact extremal quorum risk over every joint Bernoulli
distribution compatible with supplied marginals.  A quorum therefore cannot be
certified merely because several evaluator names or model families differ.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations, product
import math
from typing import Iterable

import numpy as np
from scipy.optimize import linprog

from .evaluator_control import LineageQuorumPolicy, QuorumAction, QuorumDecision
from .models import Claim


@dataclass(frozen=True, slots=True)
class EvaluatorMarginal:
    evaluator_id: str
    model: str
    mode: str
    fp_rate: float
    fn_rate: float
    source_ref: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.fp_rate <= 1.0 and 0.0 <= self.fn_rate <= 1.0):
            raise ValueError("FP/FN rates must lie in [0, 1]")

    @property
    def tp_rate(self) -> float:
        return 1.0 - self.fn_rate


@dataclass(frozen=True, slots=True)
class QuorumRiskBounds:
    evaluator_ids: tuple[str, ...]
    required_support: int
    unsafe_min: float
    unsafe_max: float
    false_block_min: float
    false_block_max: float
    unsafe_independence: float
    false_block_independence: float

    @property
    def worst_balanced_error(self) -> float:
        return (self.unsafe_max + self.false_block_max) / 2.0

    @property
    def minimax_error(self) -> float:
        return max(self.unsafe_max, self.false_block_max)

    def as_dict(self) -> dict[str, object]:
        return {
            "evaluator_ids": list(self.evaluator_ids),
            "required_support": self.required_support,
            "unsafe_min": self.unsafe_min,
            "unsafe_max": self.unsafe_max,
            "false_block_min": self.false_block_min,
            "false_block_max": self.false_block_max,
            "unsafe_independence": self.unsafe_independence,
            "false_block_independence": self.false_block_independence,
            "worst_balanced_error": self.worst_balanced_error,
            "minimax_error": self.minimax_error,
        }


@dataclass(frozen=True, slots=True)
class RobustQuorumCertificate:
    bounds: QuorumRiskBounds
    max_unsafe: float
    max_false_block: float
    certified: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "bounds": self.bounds.as_dict(),
            "max_unsafe": self.max_unsafe,
            "max_false_block": self.max_false_block,
            "certified": self.certified,
            "reason": self.reason,
        }


def _states(n: int) -> np.ndarray:
    if n < 1:
        raise ValueError("at least one evaluator is required")
    if n > 12:
        raise ValueError("exact dependence bounds are limited to n<=12")
    return np.asarray(tuple(product((0, 1), repeat=n)), dtype=float)


def _extremal_event_probability(
    marginals: tuple[float, ...],
    event: np.ndarray,
) -> tuple[float, float]:
    n = len(marginals)
    states = _states(n)
    if event.shape != (len(states),):
        raise ValueError("event mask shape mismatch")

    a_eq = [np.ones(len(states), dtype=float)]
    b_eq = [1.0]
    for index, marginal in enumerate(marginals):
        if not 0.0 <= marginal <= 1.0:
            raise ValueError("marginals must lie in [0, 1]")
        a_eq.append(states[:, index])
        b_eq.append(float(marginal))

    kwargs = {
        "A_eq": np.asarray(a_eq),
        "b_eq": np.asarray(b_eq),
        "bounds": [(0.0, None)] * len(states),
        "method": "highs",
    }
    minimum = linprog(event, **kwargs)
    maximum = linprog(-event, **kwargs)
    if not minimum.success or not maximum.success:
        raise RuntimeError("joint-distribution LP is infeasible")
    return float(minimum.fun), float(-maximum.fun)


def _independent_probability(
    marginals: tuple[float, ...],
    *,
    event_predicate,
) -> float:
    total = 0.0
    for bits in product((0, 1), repeat=len(marginals)):
        probability = 1.0
        for bit, marginal in zip(bits, marginals, strict=True):
            probability *= marginal if bit else 1.0 - marginal
        if event_predicate(bits):
            total += probability
    return total


def quorum_risk_bounds(
    evaluators: Iterable[EvaluatorMarginal],
    *,
    required_support: int,
) -> QuorumRiskBounds:
    rows = tuple(evaluators)
    if required_support < 1 or required_support > len(rows):
        raise ValueError("required_support must be in [1, n]")

    states = _states(len(rows))
    support_counts = states.sum(axis=1)
    promote = (support_counts >= required_support).astype(float)
    block = (support_counts < required_support).astype(float)

    false_positive_marginals = tuple(row.fp_rate for row in rows)
    true_positive_marginals = tuple(row.tp_rate for row in rows)
    unsafe_min, unsafe_max = _extremal_event_probability(
        false_positive_marginals, promote
    )
    false_block_min, false_block_max = _extremal_event_probability(
        true_positive_marginals, block
    )

    unsafe_independence = _independent_probability(
        false_positive_marginals,
        event_predicate=lambda bits: sum(bits) >= required_support,
    )
    false_block_independence = _independent_probability(
        true_positive_marginals,
        event_predicate=lambda bits: sum(bits) < required_support,
    )

    return QuorumRiskBounds(
        evaluator_ids=tuple(row.evaluator_id for row in rows),
        required_support=required_support,
        unsafe_min=unsafe_min,
        unsafe_max=unsafe_max,
        false_block_min=false_block_min,
        false_block_max=false_block_max,
        unsafe_independence=unsafe_independence,
        false_block_independence=false_block_independence,
    )


def certify_quorum(
    evaluators: Iterable[EvaluatorMarginal],
    *,
    required_support: int,
    max_unsafe: float,
    max_false_block: float,
) -> RobustQuorumCertificate:
    if not 0.0 <= max_unsafe <= 1.0 or not 0.0 <= max_false_block <= 1.0:
        raise ValueError("risk thresholds must lie in [0, 1]")
    bounds = quorum_risk_bounds(evaluators, required_support=required_support)
    certified = (
        bounds.unsafe_max <= max_unsafe
        and bounds.false_block_max <= max_false_block
    )
    if certified:
        reason = "worst-case dependence bounds satisfy configured risk limits"
    else:
        failures = []
        if bounds.unsafe_max > max_unsafe:
            failures.append(
                f"unsafe_max={bounds.unsafe_max:.6f}>{max_unsafe:.6f}"
            )
        if bounds.false_block_max > max_false_block:
            failures.append(
                f"false_block_max={bounds.false_block_max:.6f}>{max_false_block:.6f}"
            )
        reason = "marginal-only dependence certificate insufficient: " + ", ".join(failures)
    return RobustQuorumCertificate(
        bounds=bounds,
        max_unsafe=max_unsafe,
        max_false_block=max_false_block,
        certified=certified,
        reason=reason,
    )


def search_triplet_quorums(
    evaluators: Iterable[EvaluatorMarginal],
    *,
    max_unsafe: float,
    max_false_block: float,
    distinct_models: bool = True,
) -> tuple[RobustQuorumCertificate, ...]:
    rows = tuple(evaluators)
    results: list[RobustQuorumCertificate] = []
    for subset in combinations(rows, 3):
        if distinct_models and len({row.model for row in subset}) != 3:
            continue
        for required_support in (2, 3):
            results.append(
                certify_quorum(
                    subset,
                    required_support=required_support,
                    max_unsafe=max_unsafe,
                    max_false_block=max_false_block,
                )
            )
    return tuple(
        sorted(
            results,
            key=lambda cert: (
                cert.bounds.minimax_error,
                cert.bounds.worst_balanced_error,
                cert.bounds.unsafe_max,
                cert.bounds.false_block_max,
                cert.bounds.evaluator_ids,
                cert.bounds.required_support,
            ),
        )
    )


class RiskCertifiedLineageQuorumPolicy:
    """Require both live lineage quorum and a precomputed robust risk certificate."""

    name = "risk_certified_lineage_quorum"

    def __init__(
        self,
        certificate: RobustQuorumCertificate,
        *,
        base_policy: LineageQuorumPolicy | None = None,
    ) -> None:
        self.certificate = certificate
        self.base_policy = base_policy or LineageQuorumPolicy()

    def decide(self, claim: Claim, observations) -> QuorumDecision:
        decision = self.base_policy.decide(claim, observations)
        if self.certificate.certified or not decision.promoted:
            return decision
        blocker = "distributionally robust risk certificate failed: " + self.certificate.reason
        return replace(
            decision,
            action=QuorumAction.HOLD,
            blockers=decision.blockers + (blocker,),
        )
