#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VALIDATED = {"EXTERNAL_VERIFIED", "CI_VERIFIED", "TOOL_VERIFIED", "HUMAN_REVIEWED"}
SOURCE_FOR = {
    "EXTERNAL_VERIFIED": {"tool_log", "parser_output", "benchmark_output", "python_runner"},
    "CI_VERIFIED": {"ci_log"},
    "TOOL_VERIFIED": {"tool_log", "python_runner", "parser_output"},
    "HUMAN_REVIEWED": {"human_review"},
}


def _load(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid_json:{exc.lineno}:{exc.colno}"]
    except OSError as exc:
        return None, [f"read_error:{exc}"]
    if not isinstance(data, dict):
        return None, ["root_must_be_object"]
    return data, []


def check_policy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    contract_type = data.get("contract_type")
    inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    evidence = data.get("evidence_status") if isinstance(data.get("evidence_status"), dict) else {}
    verdict = data.get("final_verdict") if isinstance(data.get("final_verdict"), dict) else {}

    external = evidence.get("external_evidence_available")
    source = evidence.get("evidence_source")
    evidence_status = evidence.get("status")
    final_status = verdict.get("status")
    tests_executed = evidence.get("tests_executed")
    score = evidence.get("score")

    if evidence_status != final_status:
        errors.append("status_mismatch")

    if external is False:
        if source != "unavailable":
            errors.append("source_without_external_evidence")
        if tests_executed:
            errors.append("executed_tests_without_external_evidence")

    if contract_type == "blocked_contract":
        missing = inputs.get("missing") if isinstance(inputs, dict) else None
        if not isinstance(missing, list) or not missing:
            errors.append("blocked_contract_missing_inputs_required")
        if evidence_status != "BLOCKED" or final_status != "BLOCKED":
            errors.append("blocked_contract_status_required")
        if source != "unavailable":
            errors.append("blocked_contract_source_must_be_unavailable")
        if tests_executed:
            errors.append("blocked_contract_must_not_claim_executed_tests")
        if score is not None:
            errors.append("blocked_contract_score_must_be_null")

    if final_status in VALIDATED:
        if external is not True:
            errors.append("validated_status_requires_external_evidence")
        if not tests_executed:
            errors.append("validated_status_requires_tests_executed")
        allowed = SOURCE_FOR.get(str(final_status), set())
        if source not in allowed:
            errors.append("validated_status_source_mismatch")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check JSON contract evidence policy")
    parser.add_argument("path", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    data, errors = _load(args.path)
    if data is not None:
        errors.extend(check_policy(data))

    result = {
        "schema_version": "json_contract_evidence_policy.v1",
        "input": str(args.path),
        "status": "OK" if not errors else "ERROR",
        "errors": errors,
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
