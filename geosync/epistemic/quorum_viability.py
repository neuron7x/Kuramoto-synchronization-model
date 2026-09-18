"""Exact solver-independent viability classification for three-evaluator quorums.

The Iteration 005/006 result established worst-case non-certifiability from
marginal evaluator rates alone.  For n=3, k in {2, 3}, the Fréchet extrema have
closed forms.  This module therefore distinguishes three logically different
states without trusting an LP solver:

* CERTIFIED: every compatible dependence structure meets the risk budget;
* IMPOSSIBLE: no compatible dependence structure can meet the risk budget;
* UNRESOLVED: dependence evidence is necessary to decide.

All arithmetic is exact fractions parsed from the published decimal rates.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
from typing import Iterable


class ViabilityStatus(str, Enum):
    CERTIFIED = "CERTIFIED"
    UNRESOLVED = "UNRESOLVED"
    IMPOSSIBLE = "IMPOSSIBLE"


@dataclass(frozen=True, slots=True)
class ExactEvaluatorMarginal:
    evaluator_id: str
    model: str
    mode: str
    fp_rate: Fraction
    fn_rate: Fraction
    source_ref: str = ""

    @property
    def tp_rate(self) -> Fraction:
        return Fraction(1) - self.fn_rate


@dataclass(frozen=True, slots=True)
class ExactQuorumInterval:
    evaluator_ids: tuple[str, str, str]
    required_support: int
    unsafe_min: Fraction
    unsafe_max: Fraction
    false_block_min: Fraction
    false_block_max: Fraction

    def as_dict(self) -> dict[str, object]:
        return {
            "evaluator_ids": list(self.evaluator_ids),
            "required_support": self.required_support,
            "unsafe_min": _fraction_dict(self.unsafe_min),
            "unsafe_max": _fraction_dict(self.unsafe_max),
            "false_block_min": _fraction_dict(self.false_block_min),
            "false_block_max": _fraction_dict(self.false_block_max),
        }


@dataclass(frozen=True, slots=True)
class ViabilityVerdict:
    status: ViabilityStatus
    bounds: ExactQuorumInterval
    max_unsafe: Fraction
    max_false_block: Fraction
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "bounds": self.bounds.as_dict(),
            "max_unsafe": _fraction_dict(self.max_unsafe),
            "max_false_block": _fraction_dict(self.max_false_block),
            "reason": self.reason,
        }


def _fraction_dict(value: Fraction) -> dict[str, object]:
    return {"fraction": str(value), "decimal": float(value)}


def _as_fraction(value: Decimal | str | int | Fraction) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        return Fraction(value)
    return Fraction(value)


def load_exact_marginals(path: str | Path) -> tuple[ExactEvaluatorMarginal, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"), parse_float=Decimal)
    rows = []
    source_ref = raw.get("source", {}).get("project_url", "")
    for item in raw["evaluators"]:
        fp = _as_fraction(item["fp_rate"])
        fn = _as_fraction(item["fn_rate"])
        if not (0 <= fp <= 1 and 0 <= fn <= 1):
            raise ValueError("FP/FN rates must be probabilities")
        model = str(item["model"])
        mode = str(item["mode"])
        rows.append(
            ExactEvaluatorMarginal(
                evaluator_id=f"{model}::{mode}",
                model=model,
                mode=mode,
                fp_rate=fp,
                fn_rate=fn,
                source_ref=source_ref,
            )
        )
    return tuple(rows)


def exact_kof3_event_bounds(
    marginals: tuple[Fraction, Fraction, Fraction],
    *,
    required_support: int,
) -> tuple[Fraction, Fraction]:
    """Exact Fréchet bounds for P(sum Xi >= k), n=3, from marginals only."""
    if required_support not in (2, 3):
        raise ValueError("exact closed form supports only 2-of-3 or 3-of-3")
    p1, p2, p3 = marginals
    if any(p < 0 or p > 1 for p in marginals):
        raise ValueError("marginals must lie in [0, 1]")
    total = p1 + p2 + p3
    if required_support == 3:
        lower = max(Fraction(0), total - 2)
        upper = min(p1, p2, p3)
        return lower, upper

    # Majority event Q={X1+X2+X3>=2}.
    # Lower constraints: Q contains every pairwise intersection and
    # E[S] <= 1 + 2 P(Q).  Upper constraints: Q implies at least one member
    # of every pair is active and E[S] >= 2 P(Q).
    lower = max(
        Fraction(0),
        p1 + p2 - 1,
        p1 + p3 - 1,
        p2 + p3 - 1,
        (total - 1) / 2,
    )
    upper = min(
        Fraction(1),
        total / 2,
        p1 + p2,
        p1 + p3,
        p2 + p3,
    )
    return lower, upper


def exact_quorum_interval(
    evaluators: Iterable[ExactEvaluatorMarginal],
    *,
    required_support: int,
) -> ExactQuorumInterval:
    rows = tuple(evaluators)
    if len(rows) != 3:
        raise ValueError("exact triplet viability requires exactly three evaluators")
    unsafe_min, unsafe_max = exact_kof3_event_bounds(
        tuple(row.fp_rate for row in rows),
        required_support=required_support,
    )
    promote_min, promote_max = exact_kof3_event_bounds(
        tuple(row.tp_rate for row in rows),
        required_support=required_support,
    )
    return ExactQuorumInterval(
        evaluator_ids=tuple(row.evaluator_id for row in rows),
        required_support=required_support,
        unsafe_min=unsafe_min,
        unsafe_max=unsafe_max,
        false_block_min=Fraction(1) - promote_max,
        false_block_max=Fraction(1) - promote_min,
    )


def classify_viability(
    bounds: ExactQuorumInterval,
    *,
    max_unsafe: Fraction | str = Fraction(1, 10),
    max_false_block: Fraction | str = Fraction(1, 5),
) -> ViabilityVerdict:
    unsafe_budget = _as_fraction(max_unsafe)
    block_budget = _as_fraction(max_false_block)
    if bounds.unsafe_max <= unsafe_budget and bounds.false_block_max <= block_budget:
        return ViabilityVerdict(
            ViabilityStatus.CERTIFIED,
            bounds,
            unsafe_budget,
            block_budget,
            "all dependence structures compatible with the marginals satisfy the configured budgets",
        )
    impossible_reasons = []
    if bounds.unsafe_min > unsafe_budget:
        impossible_reasons.append(
            f"unsafe_min={bounds.unsafe_min}>{unsafe_budget}"
        )
    if bounds.false_block_min > block_budget:
        impossible_reasons.append(
            f"false_block_min={bounds.false_block_min}>{block_budget}"
        )
    if impossible_reasons:
        return ViabilityVerdict(
            ViabilityStatus.IMPOSSIBLE,
            bounds,
            unsafe_budget,
            block_budget,
            "no compatible dependence structure can satisfy the configured budgets: "
            + ", ".join(impossible_reasons),
        )
    return ViabilityVerdict(
        ViabilityStatus.UNRESOLVED,
        bounds,
        unsafe_budget,
        block_budget,
        "some compatible dependence structures pass and others fail; joint observations are required",
    )


def scan_distinct_model_triplets(
    evaluators: Iterable[ExactEvaluatorMarginal],
    *,
    max_unsafe: Fraction | str = Fraction(1, 10),
    max_false_block: Fraction | str = Fraction(1, 5),
) -> tuple[ViabilityVerdict, ...]:
    rows = tuple(evaluators)
    verdicts: list[ViabilityVerdict] = []
    for subset in combinations(rows, 3):
        if len({row.model for row in subset}) != 3:
            continue
        for support in (2, 3):
            verdicts.append(
                classify_viability(
                    exact_quorum_interval(subset, required_support=support),
                    max_unsafe=max_unsafe,
                    max_false_block=max_false_block,
                )
            )
    return tuple(verdicts)
