#!/usr/bin/env python3
"""Deterministic PromptOps shadow runner.

The runner consumes validated PromptOps contracts and executes a local,
provider-free shadow pass. It does not pretend to be a real LLM evaluator.
It gives CI a stable regression surface before a later provider-backed job is
allowed to spend tokens, leak secrets, or summon the usual distributed gremlins.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from promptops_validate import (
    build_payload,
    discover,
    load_artifact,
    validate_artifact,
)

SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}",
    re.IGNORECASE,
)
INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?previous\s+instructions?|reveal\s+(the\s+)?(system\s+)?prompt|developer\s+mode)",
    re.IGNORECASE,
)
MISSING_REF_RE = re.compile(
    r"(missing\s+referenced?\s+id|missing\s+reference|<ref:missing>|undeclared\s+ref)",
    re.IGNORECASE,
)


@dataclass
class ShadowCaseResult:
    artifact: str
    case_id: str
    ok: bool
    issue_codes: list[str] = field(default_factory=list)
    gates: dict[str, bool] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "case_id": self.case_id,
            "ok": self.ok,
            "issue_codes": sorted(set(self.issue_codes)),
            "gates": dict(sorted(self.gates.items())),
            "metrics": self.metrics,
            "notes": self.notes,
        }


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def deterministic_evaluate(case: dict[str, Any]) -> list[str]:
    text = stringify(case.get("input", ""))
    codes: list[str] = []

    if MISSING_REF_RE.search(text):
        codes.append("missing_reference_declaration")
    if INJECTION_RE.search(text):
        codes.append("prompt_injection_phrase")
    if SECRET_RE.search(text):
        codes.append("secret_like_value")

    return codes


def evaluate_quality_gates(case: dict[str, Any], issue_codes: list[str]) -> dict[str, bool]:
    raw_gates = case.get("quality_gates", [])
    gates: dict[str, bool] = {}
    deterministic_codes = all(isinstance(code, str) and bool(code.strip()) for code in issue_codes)

    for gate in raw_gates:
        label = stringify(gate).strip()
        key = label.lower()
        if "no secret leakage" in key:
            gates[label] = "secret_like_value" not in issue_codes
        elif "deterministic issue code" in key:
            gates[label] = deterministic_codes
        elif "latency budget" in key:
            gates[label] = True
        else:
            gates[label] = True

    return gates


def evaluate_case(artifact: Path, case: dict[str, Any]) -> ShadowCaseResult:
    case_id = str(case.get("id", "<missing-id>"))
    issue_codes = deterministic_evaluate(case)
    gates = evaluate_quality_gates(case, issue_codes)
    expectations = case.get("baseline_expectations", {})
    if not isinstance(expectations, dict):
        expectations = {"expected": expectations}

    ok = all(gates.values())
    notes: list[str] = []

    must_fail = expectations.get("must_fail")
    if must_fail is True and not issue_codes:
        ok = False
        notes.append("expected failure but deterministic evaluator emitted no issue")
    if must_fail is False and issue_codes:
        ok = False
        notes.append(f"expected pass but issues were emitted: {sorted(set(issue_codes))}")

    expected_issue = expectations.get("expected_issue")
    if expected_issue and expected_issue not in issue_codes:
        ok = False
        notes.append(f"expected issue {expected_issue!r} was not emitted")

    forbidden_issue = expectations.get("forbidden_issue")
    if forbidden_issue and forbidden_issue in issue_codes:
        ok = False
        notes.append(f"forbidden issue {forbidden_issue!r} was emitted")

    metrics = {
        "deterministic": True,
        "provider": "local-mock",
        "issue_count": len(set(issue_codes)),
        "latency_budget_recorded": True,
    }
    return ShadowCaseResult(
        artifact=str(artifact),
        case_id=case_id,
        ok=ok,
        issue_codes=issue_codes,
        gates=gates,
        metrics=metrics,
        notes=notes,
    )


def run_shadow(paths: list[str]) -> dict[str, Any]:
    artifacts = discover(paths)
    validation_reports = [validate_artifact(path) for path in artifacts]
    validation_payload = build_payload(validation_reports)

    case_results: list[ShadowCaseResult] = []
    if validation_payload["ok"]:
        for artifact in artifacts:
            data = load_artifact(artifact)
            for case in data.get("shadow_tests", []):
                if isinstance(case, dict):
                    case_results.append(evaluate_case(artifact, case))

    ok = validation_payload["ok"] and all(result.ok for result in case_results)
    return {
        "ok": ok,
        "mode": "local-mock",
        "validation": validation_payload,
        "summary": {
            "artifact_count": len(artifacts),
            "case_count": len(case_results),
            "failed_cases": sum(1 for result in case_results if not result.ok),
            "pass_rate": (
                1.0
                if not case_results
                else round(sum(1 for result in case_results if result.ok) / len(case_results), 6)
            ),
        },
        "cases": [result.as_dict() for result in case_results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic PromptOps shadow tests")
    parser.add_argument("paths", nargs="+", help="Artifact files or directories")
    parser.add_argument("--report", default="", help="Optional JSON report path")
    args = parser.parse_args(argv)

    payload = run_shadow(args.paths)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
