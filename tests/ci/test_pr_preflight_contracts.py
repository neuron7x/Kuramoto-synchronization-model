import json
import re
from pathlib import Path

import pytest

from tools.ci import pr_preflight

# Manifest-driven governance contract (MEDIUM-5): the required sections are NOT
# hardcoded here — they are derived from docs/REPOSITORY_SYSTEM.contract.json
# (number-agnostic heading regexes). Section ordinals may change; the semantic
# contract may not. One canonical manifest, two tests derive from it.
_REPO_SYSTEM_CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "REPOSITORY_SYSTEM.contract.json").read_text(
        encoding="utf-8"
    )
)


def _valid_report() -> dict:
    checks = [
        {
            "id": "lint",
            "name": "Lint",
            "critical": True,
            "status": "PASS",
            "command": ["tool", "check"],
            "exit_code": 0,
            "duration_seconds": 0.1,
            "stdout_log": "artifacts/pr_preflight/logs/lint.stdout.log",
            "stderr_log": "artifacts/pr_preflight/logs/lint.stderr.log",
            "failure_reason": "",
        },
        {
            "id": "optional_observation",
            "name": "Optional observation",
            "critical": False,
            "status": "SKIPPED_OPTIONAL",
            "command": [],
            "exit_code": None,
            "duration_seconds": 0.0,
            "stdout_log": "artifacts/pr_preflight/logs/optional.stdout.log",
            "stderr_log": "artifacts/pr_preflight/logs/optional.stderr.log",
            "failure_reason": "optional observation skipped",
        },
    ]
    return {
        "schema_version": 1,
        "status": "PASS",
        "root": "/repo",
        "started_at": "2026-06-13T00:00:00Z",
        "finished_at": "2026-06-13T00:00:01Z",
        "duration_seconds": 1.0,
        "checks": checks,
        "summary": pr_preflight.summarize(checks),
        "failure_count": 0,
        "next_action": "No critical failures.",
        "first_file_to_open": "artifacts/pr_preflight/preflight_report.json",
    }


def test_report_contract_accepts_valid_report():
    pr_preflight.validate_report_contract(_valid_report())


def test_report_contract_rejects_missing_required_key():
    report = _valid_report()
    report.pop("checks")

    with pytest.raises(ValueError, match="report missing keys"):
        pr_preflight.validate_report_contract(report)


def test_report_contract_rejects_bad_final_status():
    report = _valid_report()
    report["status"] = "BAD_STATUS"

    with pytest.raises(ValueError, match="invalid final status"):
        pr_preflight.validate_report_contract(report)


def test_report_contract_rejects_bad_check_status():
    report = _valid_report()
    report["checks"][0]["status"] = "BAD_STATUS"

    with pytest.raises(ValueError, match="invalid check status"):
        pr_preflight.validate_report_contract(report)


def test_report_contract_rejects_empty_stdout_log():
    report = _valid_report()
    report["checks"][0]["stdout_log"] = ""

    with pytest.raises(ValueError, match="stdout_log missing"):
        pr_preflight.validate_report_contract(report)


def test_report_contract_rejects_summary_drift():
    report = _valid_report()
    report["summary"]["passed"] = 999

    with pytest.raises(ValueError, match="summary does not match"):
        pr_preflight.validate_report_contract(report)


def test_report_contract_rejects_failure_count_drift():
    report = _valid_report()
    report["failure_count"] = 99

    with pytest.raises(ValueError, match="failure_count mismatch"):
        pr_preflight.validate_report_contract(report)


def test_report_contract_rejects_critical_optional_skip():
    report = _valid_report()
    report["checks"][0]["status"] = "SKIPPED_OPTIONAL"
    report["summary"] = pr_preflight.summarize(report["checks"])
    report["failure_count"] = 1

    with pytest.raises(ValueError, match="critical check skipped optional"):
        pr_preflight.validate_report_contract(report)


def test_repository_system_map_retains_canonical_sections():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "docs" / "REPOSITORY_SYSTEM.md").read_text(encoding="utf-8")

    for section in _REPO_SYSTEM_CONTRACT["required_sections"]:
        assert re.search(section["heading_regex"], text, re.MULTILINE), (
            f"REPOSITORY_SYSTEM.md missing required governance section: {section['id']}"
        )
    assert "docs/PR_PREFLIGHT_RUNBOOK.md" in text
