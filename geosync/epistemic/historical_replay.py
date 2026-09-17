"""Historical external-adjudication replay for ECP-AS Iteration 003.

The replay is not a population benchmark. It tests whether the control plane
maps externally grounded adjudication events to conservative, typed epistemic
state changes without treating every editorial action as falsification.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Protocol

from .adjudication import (
    AdjudicationAction,
    AdjudicationDecision,
    AdjudicationKind,
    AuthorityClass,
    DefectClass,
    ExternalAdjudicationEvent,
    ExternalAdjudicationPolicy,
    IndependenceLevel,
)
from .models import ClaimState


@dataclass(frozen=True, slots=True)
class HistoricalCase:
    case_id: str
    event: ExternalAdjudicationEvent
    current_state: ClaimState
    expected_action: AdjudicationAction
    policy_expected_state: ClaimState
    reason_summary: str


@dataclass(frozen=True, slots=True)
class HistoricalDecision:
    case_id: str
    action: AdjudicationAction
    predicted_state: ClaimState
    reason: str


@dataclass(frozen=True, slots=True)
class HistoricalMetrics:
    policy: str
    total: int
    transition_conformance: int
    correct_actions: int
    false_degradations: int
    missed_degradations: int
    false_falsifications: int

    @property
    def transition_conformance_rate(self) -> float:
        return self.transition_conformance / self.total if self.total else 0.0

    @property
    def action_accuracy(self) -> float:
        return self.correct_actions / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "total": self.total,
            "transition_conformance": self.transition_conformance,
            "transition_conformance_rate": self.transition_conformance_rate,
            "correct_actions": self.correct_actions,
            "action_accuracy": self.action_accuracy,
            "false_degradations": self.false_degradations,
            "missed_degradations": self.missed_degradations,
            "false_falsifications": self.false_falsifications,
        }


class HistoricalPolicy(Protocol):
    name: str

    def decide(self, case: HistoricalCase) -> HistoricalDecision: ...


class ECPASHistoricalPolicy:
    name = "ecp_as_external_adjudication"

    def __init__(self, policy: ExternalAdjudicationPolicy | None = None) -> None:
        self.policy = policy or ExternalAdjudicationPolicy()

    def decide(self, case: HistoricalCase) -> HistoricalDecision:
        decision = self.policy.evaluate(case.event)
        predicted = decision.target_state if decision.degrades else case.current_state
        return HistoricalDecision(case.case_id, decision.action, predicted, decision.reason)


class RetractionEqualsFalsificationBaseline:
    """Naive policy: every retraction falsifies, every correction preserves."""

    name = "retraction_equals_falsification"

    def decide(self, case: HistoricalCase) -> HistoricalDecision:
        if case.event.kind is AdjudicationKind.EDITORIAL_RETRACTION:
            return HistoricalDecision(
                case.case_id,
                AdjudicationAction.DEGRADE,
                ClaimState.FALSIFIED,
                "all retractions are treated as proposition falsification",
            )
        if case.event.kind is AdjudicationKind.INDEPENDENT_REPLICATION:
            return HistoricalDecision(
                case.case_id,
                AdjudicationAction.DEGRADE,
                ClaimState.CONFLICTED,
                "independent replication disagreement",
            )
        return HistoricalDecision(
            case.case_id,
            AdjudicationAction.PRESERVE,
            case.current_state,
            "non-retraction editorial action",
        )


class AllEditorialActionsDegradeBaseline:
    """Over-conservative baseline that degrades every external editorial action."""

    name = "all_editorial_actions_degrade"

    def decide(self, case: HistoricalCase) -> HistoricalDecision:
        if case.event.kind in {
            AdjudicationKind.EDITORIAL_RETRACTION,
            AdjudicationKind.EDITORIAL_CORRECTION,
            AdjudicationKind.EDITORIAL_ADDENDUM,
        }:
            return HistoricalDecision(
                case.case_id,
                AdjudicationAction.DEGRADE,
                ClaimState.INCONCLUSIVE,
                "all publisher actions are treated as scientific invalidation",
            )
        return HistoricalDecision(
            case.case_id,
            AdjudicationAction.DEGRADE,
            ClaimState.CONFLICTED,
            "external replication disagreement",
        )


def load_historical_cases(path: str | Path) -> tuple[HistoricalCase, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows: list[HistoricalCase] = []
    for item in raw["cases"]:
        event = ExternalAdjudicationEvent(
            event_id=item["case_id"],
            claim_id=item["claim_id"],
            kind=AdjudicationKind(item["kind"]),
            authority=AuthorityClass(item["authority"]),
            source_url=item["source_url"],
            source_title=item["source_title"],
            source_date=item["source_date"],
            source_digest=item["source_digest"],
            defects=frozenset(DefectClass(value) for value in item["defects"]),
            source_authenticity_verified=bool(item["source_authenticity_verified"]),
            independence_level=IndependenceLevel(item["independence_level"]),
            explicit_conclusions_unsupported=bool(item["explicit_conclusions_unsupported"]),
            note=item["reason_summary"],
        )
        rows.append(
            HistoricalCase(
                case_id=item["case_id"],
                event=event,
                current_state=ClaimState.REPLICATED,
                expected_action=AdjudicationAction(item["expected_action"]),
                policy_expected_state=ClaimState(item["policy_expected_state"]),
                reason_summary=item["reason_summary"],
            )
        )
    return tuple(rows)


def run_historical_policy(
    policy: HistoricalPolicy,
    cases: Iterable[HistoricalCase],
) -> tuple[HistoricalMetrics, tuple[HistoricalDecision, ...]]:
    rows = tuple(cases)
    decisions = tuple(policy.decide(case) for case in rows)
    exact = action_ok = false_degrade = missed = false_falsification = 0
    for case, decision in zip(rows, decisions, strict=True):
        if decision.predicted_state is case.policy_expected_state:
            exact += 1
        if decision.action is case.expected_action:
            action_ok += 1
        expected_degrade = case.expected_action is AdjudicationAction.DEGRADE
        actual_degrade = decision.action is AdjudicationAction.DEGRADE
        if actual_degrade and not expected_degrade:
            false_degrade += 1
        if expected_degrade and not actual_degrade:
            missed += 1
        if decision.predicted_state is ClaimState.FALSIFIED and case.policy_expected_state is not ClaimState.FALSIFIED:
            false_falsification += 1
    metrics = HistoricalMetrics(
        policy=policy.name,
        total=len(rows),
        transition_conformance=exact,
        correct_actions=action_ok,
        false_degradations=false_degrade,
        missed_degradations=missed,
        false_falsifications=false_falsification,
    )
    return metrics, decisions


def default_historical_policies() -> tuple[HistoricalPolicy, ...]:
    return (
        RetractionEqualsFalsificationBaseline(),
        AllEditorialActionsDegradeBaseline(),
        ECPASHistoricalPolicy(),
    )
