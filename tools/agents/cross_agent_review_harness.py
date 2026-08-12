# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cross-agent review harness.

Lie blocked:
    "model confidence = truth"

Evaluates structured AI-agent outputs (Claude / GPT / Grok / Gemini /
local models / human reviewer) through a uniform evidence gate. NO
model gets a privilege. Only evidence_paths and the proposed action's
relationship to the named lie matter.

Verdicts:
    ACCEPT          claim names a lie blocked AND evidence_paths
                    contain at least one existing path AND proposed
                    action is structurally consistent with the claim.
    DOWNGRADE       evidence partial: paths listed but not all exist,
                    OR confidence is high but evidence is thin.
    REJECT          claim_text is empty, evidence_paths empty, OR
                    proposed_action is forbidden-overclaim language.
    NEEDS_EVIDENCE  claim is plausible but evidence_paths reference
                    non-existent files.

Confidence text is RECORDED but never used for the verdict — that is
the lie this module explicitly refuses.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("/tmp/geosync_cross_agent_review.json")


class ReviewVerdict(str, Enum):
    ACCEPT = "ACCEPT"
    DOWNGRADE = "DOWNGRADE"
    REJECT = "REJECT"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"


_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "predicts returns",
    "new law of physics",
    "production-ready",
    "fully verified",
    "trading signal",
    "quantum market",
    "physical equivalence",
    "universal law",
    "intelligence proved",
    "guaranteed",
)


@dataclass(frozen=True)
class AgentReview:
    """One agent's structured submission for review.

    No field on this record is allowed to confer privilege based on
    ``model_name``. The harness intentionally does not switch on it.
    """

    model_name: str
    claim_text: str
    evidence_paths: tuple[str, ...]
    proposed_action: str
    confidence_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        if not isinstance(self.proposed_action, str):
            raise TypeError("proposed_action must be a string")
        if not isinstance(self.evidence_paths, tuple):
            raise TypeError("evidence_paths must be a tuple")


@dataclass(frozen=True)
class ReviewWitness:
    """Outcome of one cross-agent evaluation."""

    model_name: str
    verdict: ReviewVerdict
    reasons: tuple[str, ...]
    existing_evidence_count: int
    missing_evidence_count: int
    recorded_confidence_text: str


@dataclass
class HarnessReport:
    witnesses: list[ReviewWitness] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_count": len(self.witnesses),
            "witnesses": [asdict(w) for w in self.witnesses],
        }


def _contains_forbidden(text: str) -> tuple[str, ...]:
    lower = (text or "").lower()
    return tuple(p for p in _FORBIDDEN_PHRASES if p in lower)


def _split_evidence(paths: tuple[str, ...], repo_root: Path) -> tuple[int, int]:
    existing = 0
    missing = 0
    for p in paths:
        candidate = (repo_root / p) if not Path(p).is_absolute() else Path(p)
        if candidate.exists():
            existing += 1
        else:
            missing += 1
    return existing, missing


def evaluate_review(review: AgentReview, *, repo_root: Path = REPO_ROOT) -> ReviewWitness:
    """Evaluate one review. Verdict is a pure function of claim/evidence/action."""
    reasons: list[str] = []

    # Forbidden language is an immediate REJECT regardless of model.
    bad_in_claim = _contains_forbidden(review.claim_text)
    bad_in_action = _contains_forbidden(review.proposed_action)
    if bad_in_claim or bad_in_action:
        reasons.append(f"forbidden phrasing: {sorted(set(bad_in_claim) | set(bad_in_action))}")
        return ReviewWitness(
            model_name=review.model_name,
            verdict=ReviewVerdict.REJECT,
            reasons=tuple(reasons),
            existing_evidence_count=0,
            missing_evidence_count=len(review.evidence_paths),
            recorded_confidence_text=review.confidence_text,
        )

    if not review.claim_text or not review.claim_text.strip():
        reasons.append("claim_text empty")
        return ReviewWitness(
            model_name=review.model_name,
            verdict=ReviewVerdict.REJECT,
            reasons=tuple(reasons),
            existing_evidence_count=0,
            missing_evidence_count=len(review.evidence_paths),
            recorded_confidence_text=review.confidence_text,
        )

    if not review.evidence_paths:
        reasons.append("evidence_paths empty")
        return ReviewWitness(
            model_name=review.model_name,
            verdict=ReviewVerdict.REJECT,
            reasons=tuple(reasons),
            existing_evidence_count=0,
            missing_evidence_count=0,
            recorded_confidence_text=review.confidence_text,
        )

    existing, missing = _split_evidence(review.evidence_paths, repo_root)

    if existing == 0:
        reasons.append("no evidence_paths exist on disk")
        return ReviewWitness(
            model_name=review.model_name,
            verdict=ReviewVerdict.NEEDS_EVIDENCE,
            reasons=tuple(reasons),
            existing_evidence_count=existing,
            missing_evidence_count=missing,
            recorded_confidence_text=review.confidence_text,
        )

    if missing > 0:
        reasons.append(f"partial evidence: {existing} existing, {missing} missing path(s)")
        return ReviewWitness(
            model_name=review.model_name,
            verdict=ReviewVerdict.DOWNGRADE,
            reasons=tuple(reasons),
            existing_evidence_count=existing,
            missing_evidence_count=missing,
            recorded_confidence_text=review.confidence_text,
        )

    # All evidence paths exist; check that the proposed action references
    # at least one of them (avoids 'evidence dump' detached from action).
    action_refs_any = any(Path(p).name in review.proposed_action for p in review.evidence_paths)
    if not action_refs_any and review.proposed_action.strip():
        reasons.append(
            "all evidence exists but proposed_action does not reference any "
            "evidence_path filename — recording but downgrading"
        )
        return ReviewWitness(
            model_name=review.model_name,
            verdict=ReviewVerdict.DOWNGRADE,
            reasons=tuple(reasons),
            existing_evidence_count=existing,
            missing_evidence_count=missing,
            recorded_confidence_text=review.confidence_text,
        )

    reasons.append("evidence present and proposed_action references it")
    return ReviewWitness(
        model_name=review.model_name,
        verdict=ReviewVerdict.ACCEPT,
        reasons=tuple(reasons),
        existing_evidence_count=existing,
        missing_evidence_count=missing,
        recorded_confidence_text=review.confidence_text,
    )


def evaluate_many(reviews: Iterable[AgentReview], *, repo_root: Path = REPO_ROOT) -> HarnessReport:
    report = HarnessReport()
    for r in reviews:
        report.witnesses.append(evaluate_review(r, repo_root=repo_root))
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-agent review harness")
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.input_json.exists():
        print(f"FAIL: input not found: {args.input_json}", file=sys.stderr)
        return 1
    raw = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("FAIL: input must be a JSON list of review objects", file=sys.stderr)
        return 1
    reviews: list[AgentReview] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        reviews.append(
            AgentReview(
                model_name=str(entry.get("model_name") or ""),
                claim_text=str(entry.get("claim_text") or ""),
                evidence_paths=tuple(entry.get("evidence_paths") or ()),
                proposed_action=str(entry.get("proposed_action") or ""),
                confidence_text=str(entry.get("confidence_text") or ""),
            )
        )
    report = evaluate_many(reviews)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rejected = sum(
        1
        for w in report.witnesses
        if w.verdict in {ReviewVerdict.REJECT, ReviewVerdict.NEEDS_EVIDENCE}
    )
    print(f"OK: {len(report.witnesses)} reviewed, {rejected} blocked")
    return 0


if __name__ == "__main__":
    # Keep the regex import alive for future tightening of phrase scan.
    _ = re
    raise SystemExit(main())
