#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Structured local PR preflight runner.

This module keeps the user-facing shell command stable while moving the actual
preflight policy into deterministic Python code that preserves evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
SKIPPED_OPTIONAL = "SKIPPED_OPTIONAL"
BLOCKED = "BLOCKED"
TIMEOUT = "TIMEOUT"

FINAL_PASS = "PASS"
FINAL_FAIL = "FAIL"
FINAL_BLOCKED = "BLOCKED"

ALLOWED_CHECK_STATUSES = {PASS, FAIL, SKIPPED_OPTIONAL, BLOCKED, TIMEOUT}
ALLOWED_FINAL_STATUSES = {FINAL_PASS, FINAL_FAIL, FINAL_BLOCKED}
REQUIRED_REPORT_KEYS = {
    "schema_version",
    "status",
    "root",
    "started_at",
    "finished_at",
    "duration_seconds",
    "checks",
    "summary",
    "failure_count",
    "next_action",
    "first_file_to_open",
}
REQUIRED_CHECK_KEYS = {
    "id",
    "name",
    "critical",
    "status",
    "command",
    "exit_code",
    "duration_seconds",
    "stdout_log",
    "stderr_log",
    "failure_reason",
}
REQUIRED_SUMMARY_KEYS = {"passed", "failed", "skipped_optional", "blocked", "timeouts"}


@dataclass(frozen=True)
class CheckSpec:
    id: str
    name: str
    command: list[str]
    critical: bool = True
    optional_if_missing: bool = False
    cwd: str = "."
    timeout_seconds: int = 300
    success_exit_codes: list[int] = field(default_factory=lambda: [0])
    stdout_log: str = ""
    stderr_log: str = ""
    skip_reason: str = ""

    def __post_init__(self) -> None:
        if not self.stdout_log:
            object.__setattr__(self, "stdout_log", f"logs/{self.id}.stdout.log")
        if not self.stderr_log:
            object.__setattr__(self, "stderr_log", f"logs/{self.id}.stderr.log")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _python_executable() -> str:
    return os.environ.get("PR_PREFLIGHT_PYTHON", sys.executable)


def _requirements_install_command(root: Path, python_executable: str) -> list[str]:
    requirements = [
        name for name in ("requirements.txt", "requirements-dev.txt") if (root / name).exists()
    ]
    if requirements:
        command = [python_executable, "-m", "pip", "install"]
        if (root / "constraints" / "security.txt").exists():
            command.extend(["-c", "constraints/security.txt"])
        for requirement in requirements:
            command.extend(["-r", requirement])
        return command
    if (root / "pyproject.toml").exists():
        return [python_executable, "-m", "pip", "install", "-e", ".[dev]"]
    return []


# Mirror the secrets gate in .github/workflows/pr-gate.yml: the CI step runs
# ``detect-secrets-hook --baseline .github/detect-secrets.baseline`` (which exits
# non-zero on a secret that is NOT already in the baseline) — NOT ``scan`` (which
# only creates/updates a baseline and exits 0, giving a false-green locally).
_SECRETS_BASELINE = ".github/detect-secrets.baseline"
_SECRETS_EXCLUDE = (
    r"^(INVENTORY\.json|\.github/detect-secrets\.baseline|"
    r"figures/disha_ba_correlation/repro_capsule/.*|"
    r"artifacts/runs/synthetic_plumbing_v1/.*|artifacts/reproducible_capsules/.*)$"
)
_SECRETS_SURFACES = ("core", "backtest", "execution", "src", "application")


def _detect_secrets_command(root: Path) -> list[str]:
    """Build the fail-closed detect-secrets-hook command for the local preflight.

    Scans git-tracked files under the security-relevant surfaces against the
    canonical baseline, mirroring the CI gate's hook + baseline + exclude. An
    empty command (no git/no tracked surface files) makes the check skip cleanly
    rather than silently pass on a stale ``scan``. The baseline must exist or the
    hook would treat every existing secret as new.
    """

    if not (root / _SECRETS_BASELINE).exists():
        return []
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--", *_SECRETS_SURFACES],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    files = [name for name in completed.stdout.split("\0") if name]
    if not files:
        return []
    return [
        "detect-secrets-hook",
        "--baseline",
        _SECRETS_BASELINE,
        "--exclude-files",
        _SECRETS_EXCLUDE,
        *files,
    ]


def build_check_registry(root: Path, skip_install: bool = False) -> list[CheckSpec]:
    python_executable = _python_executable()
    if skip_install:
        install_checks = [
            CheckSpec(
                id="pip_bootstrap",
                name="Pip bootstrap",
                command=[],
                critical=False,
                skip_reason="skipped by --skip-install",
            ),
            CheckSpec(
                id="project_dependencies",
                name="Project dependencies",
                command=[],
                critical=False,
                skip_reason="skipped by --skip-install",
            ),
        ]
    else:
        dependency_command = _requirements_install_command(root, python_executable)
        install_checks = [
            CheckSpec(
                id="pip_bootstrap",
                name="Pip bootstrap",
                command=[
                    python_executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip",
                    "setuptools",
                    "wheel",
                    "-q",
                ],
                critical=True,
                timeout_seconds=300,
            ),
            CheckSpec(
                id="project_dependencies",
                name="Project dependencies",
                command=dependency_command,
                critical=bool(dependency_command),
                skip_reason="no requirements or pyproject dependency manifest found",
                timeout_seconds=900,
            ),
        ]

    return [
        *install_checks,
        CheckSpec(
            id="ruff",
            name="Ruff lint",
            command=["ruff", "check", "."],
            critical=True,
            timeout_seconds=300,
        ),
        CheckSpec(
            id="black",
            name="Black format check",
            command=["black", "--check", ".", "--quiet"],
            critical=True,
            timeout_seconds=300,
        ),
        CheckSpec(
            id="mypy",
            name="Mypy type check",
            command=["mypy", "--no-error-summary", "."],
            critical=True,
            timeout_seconds=300,
        ),
        CheckSpec(
            id="detect_secrets",
            name="Detect secrets (baseline hook)",
            command=_detect_secrets_command(root),
            critical=True,
            optional_if_missing=True,
            skip_reason="no git-tracked surface files or missing detect-secrets baseline",
            timeout_seconds=300,
        ),
        CheckSpec(
            id="quick_tests",
            name="Quick pytest suite",
            command=[
                "pytest",
                "tests/",
                "-m",
                "not slow and not flaky and not integration",
                "--maxfail=3",
                "-q",
                "--tb=no",
            ],
            critical=True,
            timeout_seconds=600,
        ),
        CheckSpec(
            id="coverage_artifact",
            name="Coverage artifact observation",
            command=[],
            critical=False,
            timeout_seconds=1,
            skip_reason="coverage.xml is absent",
        ),
    ]


def _tool_available(command: list[str]) -> tuple[bool, str]:
    if not command:
        return True, ""
    executable = command[0]
    if os.sep in executable or (os.altsep and os.altsep in executable):
        return Path(executable).exists(), executable
    resolved = shutil.which(executable)
    return resolved is not None, resolved or executable


def _log_path(report_dir: Path, relative_log_path: str) -> Path:
    return report_dir / relative_log_path


def _base_result(
    spec: CheckSpec,
    root: Path,
    stdout_log: Path,
    stderr_log: Path,
    critical: bool,
) -> dict[str, Any]:
    return {
        "id": spec.id,
        "name": spec.name,
        "critical": critical,
        "status": BLOCKED,
        "command": list(spec.command),
        "exit_code": None,
        "duration_seconds": 0.0,
        "stdout_log": _display_path(stdout_log, root),
        "stderr_log": _display_path(stderr_log, root),
        "failure_reason": "",
        "tool_available": False,
        "cwd": spec.cwd,
        "timeout_seconds": spec.timeout_seconds,
        "success_exit_codes": list(spec.success_exit_codes),
        "optional_if_missing": spec.optional_if_missing,
    }


def _empty_check_result(
    spec: CheckSpec,
    root: Path,
    stdout_log: Path,
    stderr_log: Path,
    status: str,
    critical: bool,
    failure_reason: str,
    tool_available: bool,
    duration_seconds: float = 0.0,
) -> dict[str, Any]:
    _write_text(stdout_log, "")
    _write_text(stderr_log, "")
    result = _base_result(spec, root, stdout_log, stderr_log, critical)
    result.update(
        {
            "status": status,
            "duration_seconds": round(duration_seconds, 6),
            "failure_reason": failure_reason,
            "tool_available": tool_available,
        }
    )
    return result


def run_check(spec: CheckSpec, root: Path, report_dir: Path) -> dict[str, Any]:
    stdout_log = _log_path(report_dir, spec.stdout_log)
    stderr_log = _log_path(report_dir, spec.stderr_log)
    started = time.monotonic()

    if spec.id == "coverage_artifact":
        coverage_path = root / "coverage.xml"
        stdout = f"coverage_xml={coverage_path.exists()}\n"
        _write_text(stdout_log, stdout)
        _write_text(stderr_log, "")
        status = PASS if coverage_path.exists() else SKIPPED_OPTIONAL
        reason = "" if coverage_path.exists() else spec.skip_reason
        result = _base_result(spec, root, stdout_log, stderr_log, critical=False)
        result.update(
            {
                "status": status,
                "exit_code": 0 if coverage_path.exists() else None,
                "duration_seconds": round(time.monotonic() - started, 6),
                "failure_reason": reason,
                "tool_available": True,
            }
        )
        return result

    if not spec.command:
        return _empty_check_result(
            spec=spec,
            root=root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            status=SKIPPED_OPTIONAL,
            critical=False,
            failure_reason=spec.skip_reason or "check disabled by configuration",
            tool_available=True,
            duration_seconds=time.monotonic() - started,
        )

    critical = spec.critical
    cwd = (root / spec.cwd).resolve()
    if not cwd.exists():
        return _empty_check_result(
            spec=spec,
            root=root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            status=BLOCKED,
            critical=critical,
            failure_reason=f"cwd does not exist: {cwd}",
            tool_available=True,
            duration_seconds=time.monotonic() - started,
        )

    available, executable = _tool_available(spec.command)
    if not available and spec.optional_if_missing:
        return _empty_check_result(
            spec=spec,
            root=root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            status=SKIPPED_OPTIONAL,
            critical=False,
            failure_reason=f"optional executable missing: {executable}",
            tool_available=False,
            duration_seconds=time.monotonic() - started,
        )
    if not available:
        return _empty_check_result(
            spec=spec,
            root=root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            status=BLOCKED,
            critical=critical,
            failure_reason=f"required executable missing: {executable}",
            tool_available=False,
            duration_seconds=time.monotonic() - started,
        )

    try:
        completed = subprocess.run(
            spec.command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
        stdout = _coerce_text(completed.stdout)
        stderr = _coerce_text(completed.stderr)
        _write_text(stdout_log, stdout)
        _write_text(stderr_log, stderr)
        exit_code = completed.returncode
        status = PASS if exit_code in spec.success_exit_codes else FAIL
        reason = ""
        if status == FAIL:
            reason = f"exit code {exit_code} not in success codes {spec.success_exit_codes}"
        result = _base_result(spec, root, stdout_log, stderr_log, critical)
        result.update(
            {
                "status": status,
                "exit_code": exit_code,
                "duration_seconds": round(time.monotonic() - started, 6),
                "failure_reason": reason,
                "tool_available": True,
            }
        )
        return result
    except subprocess.TimeoutExpired as exc:
        _write_text(stdout_log, _coerce_text(exc.stdout))
        _write_text(stderr_log, _coerce_text(exc.stderr))
        result = _base_result(spec, root, stdout_log, stderr_log, critical)
        result.update(
            {
                "status": TIMEOUT,
                "duration_seconds": round(time.monotonic() - started, 6),
                "failure_reason": f"timed out after {spec.timeout_seconds} seconds",
                "tool_available": True,
            }
        )
        return result
    except OSError as exc:
        _write_text(stdout_log, "")
        _write_text(stderr_log, str(exc))
        result = _base_result(spec, root, stdout_log, stderr_log, critical)
        result.update(
            {
                "status": BLOCKED,
                "duration_seconds": round(time.monotonic() - started, 6),
                "failure_reason": f"could not execute command: {exc}",
                "tool_available": True,
            }
        )
        return result


def summarize(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed": sum(1 for check in checks if check["status"] == PASS),
        "failed": sum(1 for check in checks if check["status"] == FAIL),
        "skipped_optional": sum(1 for check in checks if check["status"] == SKIPPED_OPTIONAL),
        "blocked": sum(1 for check in checks if check["status"] == BLOCKED),
        "timeouts": sum(1 for check in checks if check["status"] == TIMEOUT),
    }


def final_status(checks: list[dict[str, Any]]) -> str:
    critical_checks = [check for check in checks if check["critical"]]
    if any(check["status"] == BLOCKED for check in critical_checks):
        return FINAL_BLOCKED
    if any(check["status"] != PASS for check in critical_checks):
        return FINAL_FAIL
    return FINAL_PASS


def first_failure(checks: list[dict[str, Any]]) -> str:
    for check in checks:
        if check["critical"] and check["status"] != PASS:
            reason = check["failure_reason"] or check["status"]
            return f"Fix {check['id']}: {reason}"
    return "No critical failures."


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_report_contract(report: dict[str, Any]) -> None:
    missing_report_keys = sorted(REQUIRED_REPORT_KEYS - set(report))
    _require(not missing_report_keys, f"report missing keys: {missing_report_keys}")
    _require(report["schema_version"] == 1, "schema_version must be 1")
    _require(report["status"] in ALLOWED_FINAL_STATUSES, "invalid final status")
    _require(isinstance(report["checks"], list), "checks must be a list")

    checks = report["checks"]
    for index, check in enumerate(checks):
        missing_check_keys = sorted(REQUIRED_CHECK_KEYS - set(check))
        _require(not missing_check_keys, f"check {index} missing keys: {missing_check_keys}")
        _require(
            check["status"] in ALLOWED_CHECK_STATUSES,
            f"invalid check status: {check['status']}",
        )
        _require(isinstance(check["critical"], bool), f"check {check['id']} critical must be bool")
        _require(isinstance(check["command"], list), f"check {check['id']} command must be list")
        _require(
            isinstance(check["duration_seconds"], int | float),
            f"check {check['id']} duration_seconds must be numeric",
        )
        _require(isinstance(check["stdout_log"], str) and check["stdout_log"], "stdout_log missing")
        _require(isinstance(check["stderr_log"], str) and check["stderr_log"], "stderr_log missing")
        _require(
            not (check["critical"] and check["status"] == SKIPPED_OPTIONAL),
            f"critical check skipped optional: {check['id']}",
        )

    summary = report["summary"]
    _require(isinstance(summary, dict), "summary must be a dict")
    missing_summary_keys = sorted(REQUIRED_SUMMARY_KEYS - set(summary))
    _require(not missing_summary_keys, f"summary missing keys: {missing_summary_keys}")
    _require(summary == summarize(checks), "summary does not match check statuses")

    expected_failure_count = sum(
        1 for check in checks if check["critical"] and check["status"] != PASS
    )
    _require(report["failure_count"] == expected_failure_count, "failure_count mismatch")
    _require(
        isinstance(report["first_file_to_open"], str)
        and report["first_file_to_open"].endswith("preflight_report.json"),
        "first_file_to_open must point to preflight_report.json",
    )


def build_report(
    root: Path,
    report_dir: Path,
    checks: list[dict[str, Any]],
    started_at: str,
) -> dict[str, Any]:
    finished_at = _utc_now()
    summary = summarize(checks)
    status = final_status(checks)
    failure_count = sum(1 for check in checks if check["critical"] and check["status"] != PASS)
    report_path = report_dir / "preflight_report.json"
    return {
        "schema_version": 1,
        "status": status,
        "root": str(root.resolve()),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": 0.0,
        "checks": checks,
        "summary": summary,
        "failure_count": failure_count,
        "next_action": first_failure(checks),
        "first_file_to_open": _display_path(report_path, root),
    }


def _invalid_root_check(root: Path, report_dir: Path) -> dict[str, Any]:
    """Build a single fail-closed BLOCKED check for a non-directory root.

    A non-directory root cannot host any real check, so the engine refuses to
    run the registry and emits one critical ``invalid_root`` BLOCKED check. This
    keeps the report contract intact while guaranteeing the run can never report
    PASS on an invalid root.
    """

    spec = CheckSpec(
        id="invalid_root",
        name="Repository root validation",
        command=[],
        critical=True,
    )
    return _empty_check_result(
        spec=spec,
        root=root,
        stdout_log=_log_path(report_dir, spec.stdout_log),
        stderr_log=_log_path(report_dir, spec.stderr_log),
        status=BLOCKED,
        critical=True,
        failure_reason=f"root is not a directory: {root}",
        tool_available=False,
    )


def run_preflight(root: Path, report_dir: Path, skip_install: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    started_at = _utc_now()
    root = root.resolve()
    report_dir = report_dir.resolve()
    if not root.is_dir():
        checks = [_invalid_root_check(root, report_dir)]
        report = build_report(root, report_dir, checks, started_at)
        report["duration_seconds"] = round(time.monotonic() - started, 6)
        validate_report_contract(report)
        _write_text(
            report_dir / "preflight_report.json", json.dumps(report, indent=2, sort_keys=True)
        )
        return report
    checks = [
        run_check(spec, root, report_dir) for spec in build_check_registry(root, skip_install)
    ]
    report = build_report(root, report_dir, checks, started_at)
    report["duration_seconds"] = round(time.monotonic() - started, 6)
    validate_report_contract(report)
    _write_text(report_dir / "preflight_report.json", json.dumps(report, indent=2, sort_keys=True))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the structured GeoSync PR preflight gate.")
    parser.add_argument(
        "--root", default=".", help="Repository root. Defaults to current directory."
    )
    parser.add_argument(
        "--report-dir",
        default="artifacts/pr_preflight",
        help="Directory for JSON report and per-check logs.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip pip bootstrap and dependency installation checks.",
    )
    parser.add_argument("--json", action="store_true", help="Print full report JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    report_dir_arg = Path(args.report_dir)
    report_dir = report_dir_arg if report_dir_arg.is_absolute() else root / report_dir_arg
    try:
        report = run_preflight(root=root, report_dir=report_dir, skip_install=args.skip_install)
    except OSError as exc:
        # Fail closed on a report-write failure (report dir is a file / unwritable):
        # print the reason to stderr and exit nonzero — never a silent PASS.
        print(f"PR_PREFLIGHT_ERROR=could not write evidence report: {exc}", file=sys.stderr)
        return 1
    report_json = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        print(report_json)
    else:
        print(f"PR_PREFLIGHT_STATUS={report['status']}")
        print(f"FIRST_FILE_TO_OPEN={report['first_file_to_open']}")
        print(f"FAILURE_COUNT={report['failure_count']}")
    return 0 if report["status"] == FINAL_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
