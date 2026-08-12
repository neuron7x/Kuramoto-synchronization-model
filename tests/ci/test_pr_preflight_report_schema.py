# SPDX-License-Identifier: MIT
"""Declarative report-contract tests for the PR preflight runner.

Reconciled from PR #948's report-schema idea, adapted to the *current* merged
engine: a real report built from the engine's own code must validate against
schemas/pr_preflight_report.schema.json, and the schema's status enums must stay
in lockstep with the engine's status constants so the declarative contract can
never silently drift from the code-level validate_report_contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.ci import pr_preflight as p

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "pr_preflight_report.schema.json"


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _sample_report(root: Path) -> dict[str, Any]:
    specs = [
        (p.CheckSpec(id="ruff", name="Ruff lint", command=["ruff", "check", "."]), "PASS"),
        (
            p.CheckSpec(
                id="detect_secrets",
                name="Detect secrets (baseline hook)",
                command=[],
                optional_if_missing=True,
            ),
            "SKIPPED_OPTIONAL",
        ),
        (p.CheckSpec(id="quick_tests", name="Quick pytest suite", command=["pytest"]), "TIMEOUT"),
    ]
    checks: list[dict[str, Any]] = []
    for spec, status in specs:
        check = p._base_result(
            spec, root, root / spec.stdout_log, root / spec.stderr_log, spec.critical
        )
        check["status"] = status
        check["tool_available"] = True
        checks.append(check)
    report = p.build_report(
        root, root / "artifacts" / "pr_preflight", checks, started_at=p._utc_now()
    )
    report["duration_seconds"] = 0.0
    return report


def test_report_schema_is_a_valid_metaschema() -> None:
    Draft202012Validator.check_schema(_schema())


def test_report_schema_status_enums_match_engine_constants() -> None:
    schema = _schema()
    final_enum = set(schema["properties"]["status"]["enum"])
    check_enum = set(schema["properties"]["checks"]["items"]["properties"]["status"]["enum"])
    assert final_enum == set(p.ALLOWED_FINAL_STATUSES)
    assert check_enum == set(p.ALLOWED_CHECK_STATUSES)


def test_engine_report_validates_against_schema(tmp_path: Path) -> None:
    Draft202012Validator(_schema()).validate(_sample_report(tmp_path))


def test_schema_rejects_report_with_unknown_status(tmp_path: Path) -> None:
    report = _sample_report(tmp_path)
    report["status"] = "ELITE"
    assert not Draft202012Validator(_schema()).is_valid(report)


def test_schema_rejects_check_missing_required_field(tmp_path: Path) -> None:
    report = _sample_report(tmp_path)
    del report["checks"][0]["tool_available"]
    assert not Draft202012Validator(_schema()).is_valid(report)
