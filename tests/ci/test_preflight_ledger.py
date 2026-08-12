import json
from pathlib import Path
from typing import Any

import pytest

from tools.ci import preflight_ledger


def _report(status: str = "FAIL") -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        {
            "id": "ruff",
            "name": "Ruff lint",
            "critical": True,
            "status": "FAIL" if status != "PASS" else "PASS",
            "command": ["ruff", "check", "."],
            "exit_code": 1 if status != "PASS" else 0,
            "duration_seconds": 0.2,
            "stdout_log": "artifacts/pr_preflight/logs/ruff.stdout.log",
            "stderr_log": "artifacts/pr_preflight/logs/ruff.stderr.log",
            "failure_reason": "exit code 1" if status != "PASS" else "",
        },
        {
            "id": "coverage_artifact",
            "name": "Coverage artifact observation",
            "critical": False,
            "status": "SKIPPED_OPTIONAL",
            "command": [],
            "exit_code": None,
            "duration_seconds": 0.0,
            "stdout_log": "artifacts/pr_preflight/logs/coverage.stdout.log",
            "stderr_log": "artifacts/pr_preflight/logs/coverage.stderr.log",
            "failure_reason": "coverage.xml is absent",
        },
    ]
    return {
        "schema_version": 1,
        "status": status,
        "root": "/repo",
        "started_at": "2026-06-13T00:00:00Z",
        "finished_at": "2026-06-13T00:00:01Z",
        "duration_seconds": 1.0,
        "checks": checks,
        "summary": {
            "passed": 1 if status == "PASS" else 0,
            "failed": 0 if status == "PASS" else 1,
            "skipped_optional": 1,
            "blocked": 0,
            "timeouts": 0,
        },
        "failure_count": 0 if status == "PASS" else 1,
        "next_action": "No critical failures." if status == "PASS" else "Fix ruff: exit code 1",
        "first_file_to_open": "artifacts/pr_preflight/preflight_report.json",
    }


def _write_report(tmp_path: Path, report: dict[str, Any]) -> Path:
    report_path = tmp_path / "preflight_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


def test_ledger_appends_failure_entry(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path, _report())
    ledger_path = tmp_path / "inference_ledger.jsonl"

    entry = preflight_ledger.append_ledger(report_path, ledger_path)

    assert entry["event_type"] == "pr_preflight_run"
    assert entry["status"] == "FAIL"
    assert entry["critical_failure_ids"] == ["ruff"]
    assert entry["skipped_optional_ids"] == ["coverage_artifact"]
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == entry


def test_ledger_appends_pass_entry_without_critical_failures(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path, _report(status="PASS"))
    ledger_path = tmp_path / "inference_ledger.jsonl"

    entry = preflight_ledger.append_ledger(report_path, ledger_path)

    assert entry["status"] == "PASS"
    assert entry["failure_count"] == 0
    assert entry["critical_failure_ids"] == []


def test_ledger_rejects_missing_report_key(tmp_path: Path) -> None:
    report = _report()
    report.pop("checks")
    report_path = _write_report(tmp_path, report)

    with pytest.raises(ValueError, match="preflight report missing keys"):
        preflight_ledger.append_ledger(report_path, tmp_path / "ledger.jsonl")


def test_ledger_rejects_bad_check_status(tmp_path: Path) -> None:
    report = _report()
    report["checks"][0]["status"] = "UNKNOWN"
    report_path = _write_report(tmp_path, report)

    with pytest.raises(ValueError, match="invalid check status"):
        preflight_ledger.append_ledger(report_path, tmp_path / "ledger.jsonl")


def test_ledger_cli_writes_default_path(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path, _report(status="PASS"))

    exit_code = preflight_ledger.main(["--report", str(report_path)])

    assert exit_code == 0
    assert (tmp_path / "inference_ledger.jsonl").exists()
