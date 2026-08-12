# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""PR-level reality budget.

Lie blocked:
    "large PR is acceptable because tests pass"

Given a PR's structural metrics, classifies it into one of:

    WITHIN_BUDGET           PR size is proportional to falsifier /
                            evidence growth and at least one named
                            lie is blocked
    NEEDS_SPLIT             PR is large but no named lie is blocked,
                            OR new_loc grows fast without proportional
                            new_tests / falsifiers_added
    CEREMONY_RISK           docs / claims grow without
                            falsifiers_added / new_tests
    ACCEPTABLE_EXCEPTION    explicitly tagged exception (e.g. dep bump)
                            with documented justification

Inputs are structural (counts and one boolean exception flag). The
gate does NOT inspect commit messages. The gate is deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = Path("/tmp/geosync_reality_budget.json")


class BudgetVerdict(str, Enum):
    WITHIN_BUDGET = "WITHIN_BUDGET"
    NEEDS_SPLIT = "NEEDS_SPLIT"
    CEREMONY_RISK = "CEREMONY_RISK"
    ACCEPTABLE_EXCEPTION = "ACCEPTABLE_EXCEPTION"


@dataclass(frozen=True)
class BudgetInput:
    """Structural metrics for one PR.

    All counts must be non-negative ints. ``known_lies_blocked`` is a
    tuple of strings; non-empty means at least one named lie is
    blocked. ``acceptable_exception_reason`` is a non-empty string
    iff the PR is a documented exception (e.g. mass dep-bump).
    """

    files_changed: int
    new_loc: int
    new_tests: int
    new_validators: int
    new_docs: int
    new_claims: int
    falsifiers_added: int
    known_lies_blocked: tuple[str, ...]
    acceptable_exception_reason: str = ""

    def __post_init__(self) -> None:
        for name in (
            "files_changed",
            "new_loc",
            "new_tests",
            "new_validators",
            "new_docs",
            "new_claims",
            "falsifiers_added",
        ):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(f"{name} must be a non-negative int")
            if v < 0:
                raise ValueError(f"{name} must be >= 0 (got {v!r})")
        if not isinstance(self.known_lies_blocked, tuple):
            raise TypeError("known_lies_blocked must be a tuple of strings")
        for i, s in enumerate(self.known_lies_blocked):
            if not isinstance(s, str) or not s.strip():
                raise ValueError(f"known_lies_blocked[{i}] must be a non-empty string")
        if not isinstance(self.acceptable_exception_reason, str):
            raise TypeError("acceptable_exception_reason must be a string")


@dataclass(frozen=True)
class BudgetWitness:
    verdict: BudgetVerdict
    reasons: tuple[str, ...]
    metrics: BudgetInput


@dataclass
class BudgetReport:
    witness: BudgetWitness | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.witness.verdict.value if self.witness is not None else None,
            "reasons": list(self.witness.reasons) if self.witness is not None else [],
            "metrics": asdict(self.witness.metrics) if self.witness is not None else None,
            "errors": list(self.errors),
        }


# Thresholds: chosen against observed PR sizes in the 2026-04-27 cycle.
_LARGE_PR_LOC = 500
_LARGE_PR_FILES = 10
_TEST_RATIO_FLOOR = 0.25  # new_tests / new_loc must be ≥ 25% to pass


def evaluate(metrics: BudgetInput) -> BudgetWitness:
    """Pure budget classifier."""
    reasons: list[str] = []

    if metrics.acceptable_exception_reason.strip():
        reasons.append(
            f"acceptable_exception_reason recorded: {metrics.acceptable_exception_reason}"
        )
        return BudgetWitness(
            verdict=BudgetVerdict.ACCEPTABLE_EXCEPTION,
            reasons=tuple(reasons),
            metrics=metrics,
        )

    is_large = metrics.new_loc >= _LARGE_PR_LOC or metrics.files_changed >= _LARGE_PR_FILES

    if is_large and not metrics.known_lies_blocked:
        reasons.append(
            f"large PR (loc={metrics.new_loc}, files={metrics.files_changed}) "
            f"but no named lie blocked"
        )
        return BudgetWitness(
            verdict=BudgetVerdict.NEEDS_SPLIT,
            reasons=tuple(reasons),
            metrics=metrics,
        )

    if is_large and metrics.new_loc > 0:
        ratio = metrics.new_tests / metrics.new_loc
        if ratio < _TEST_RATIO_FLOOR:
            reasons.append(
                f"large PR with insufficient test growth: tests/loc = "
                f"{ratio:.3f} < floor {_TEST_RATIO_FLOOR}"
            )
            return BudgetWitness(
                verdict=BudgetVerdict.NEEDS_SPLIT,
                reasons=tuple(reasons),
                metrics=metrics,
            )
        if metrics.falsifiers_added == 0:
            reasons.append("large PR with no falsifiers_added")
            return BudgetWitness(
                verdict=BudgetVerdict.NEEDS_SPLIT,
                reasons=tuple(reasons),
                metrics=metrics,
            )

    if (
        metrics.new_docs > metrics.new_tests
        and metrics.new_docs > 0
        and metrics.falsifiers_added == 0
    ):
        reasons.append(
            f"docs grow ({metrics.new_docs}) faster than tests "
            f"({metrics.new_tests}) and no falsifier added"
        )
        return BudgetWitness(
            verdict=BudgetVerdict.CEREMONY_RISK,
            reasons=tuple(reasons),
            metrics=metrics,
        )

    if metrics.new_validators > max(1, metrics.new_claims):
        reasons.append(
            f"new_validators ({metrics.new_validators}) exceed new_claims "
            f"({metrics.new_claims}) — over-validation risk"
        )
        return BudgetWitness(
            verdict=BudgetVerdict.CEREMONY_RISK,
            reasons=tuple(reasons),
            metrics=metrics,
        )

    reasons.append("size and growth proportional to falsifier / evidence")
    return BudgetWitness(
        verdict=BudgetVerdict.WITHIN_BUDGET,
        reasons=tuple(reasons),
        metrics=metrics,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR-level reality budget")
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.input_json.exists():
        print(f"FAIL: input not found: {args.input_json}", file=sys.stderr)
        return 1
    raw = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        print("FAIL: input must be a JSON object", file=sys.stderr)
        return 1
    metrics = BudgetInput(
        files_changed=int(raw.get("files_changed", 0)),
        new_loc=int(raw.get("new_loc", 0)),
        new_tests=int(raw.get("new_tests", 0)),
        new_validators=int(raw.get("new_validators", 0)),
        new_docs=int(raw.get("new_docs", 0)),
        new_claims=int(raw.get("new_claims", 0)),
        falsifiers_added=int(raw.get("falsifiers_added", 0)),
        known_lies_blocked=tuple(raw.get("known_lies_blocked") or ()),
        acceptable_exception_reason=str(raw.get("acceptable_exception_reason") or ""),
    )
    witness = evaluate(metrics)
    report = BudgetReport(witness=witness)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OK: verdict={witness.verdict.value}")
    return (
        0
        if witness.verdict in {BudgetVerdict.WITHIN_BUDGET, BudgetVerdict.ACCEPTABLE_EXCEPTION}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
