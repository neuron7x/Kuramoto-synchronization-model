#!/usr/bin/env python3
"""Run the Rust accelerator validation contract as executable evidence.

The contract manifest defines what must be true before the Rust accelerator can
be considered merge-ready. This runner turns those declarative acceptance
criteria into a bounded execution plan with machine-readable evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "rust" / "geosync-accel" / "validation_contract.json"
CONTRACT_VALIDATOR = ROOT / "scripts" / "ci" / "check_pr_gate_contract.py"


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    command: str
    pass_condition: str


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for evidence logs."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def collect_tool_versions() -> dict[str, dict[str, object]]:
    versions: dict[str, dict[str, object]] = {}
    commands = {
        "python": [sys.executable, "--version"],
        "rustc": ["rustc", "--version"],
        "cargo": ["cargo", "--version"],
        "clippy": ["cargo", "clippy", "--version"],
    }
    for name, command in commands.items():
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            versions[name] = {"available": False, "error": str(exc)}
            continue
        output = (completed.stdout or completed.stderr).strip()
        versions[name] = {
            "available": completed.returncode == 0,
            "command": command,
            "exit_code": completed.returncode,
            "output": output,
            "output_sha256": sha256_text(output),
        }
    return versions


def load_contract_validator() -> ModuleType:
    """Load the repository contract validator without requiring package setup."""

    spec = importlib.util.spec_from_file_location("check_pr_gate_contract", CONTRACT_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load validator module from {CONTRACT_VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_validated_contract(path: Path) -> dict[str, object]:
    """Read JSON and fail closed if the repository validator reports drift."""

    try:
        contract_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"unable to read validation contract {path}: {exc}") from exc

    validator = load_contract_validator()
    violations = validator.validate_rust_accel_contract_manifest(contract_text)
    if violations:
        formatted = "; ".join(violation.format() for violation in violations)
        raise RuntimeError(f"validation contract is not executable: {formatted}")

    data = json.loads(contract_text)
    if not isinstance(data, dict):
        raise RuntimeError("validation contract root must be a JSON object")
    return data


def acceptance_criteria(contract: dict[str, object]) -> tuple[AcceptanceCriterion, ...]:
    """Extract acceptance criteria after manifest validation."""

    criteria = contract.get("acceptance_criteria", [])
    if not isinstance(criteria, list):
        raise RuntimeError("acceptance_criteria must be a list")

    extracted: list[AcceptanceCriterion] = []
    for item in criteria:
        if not isinstance(item, dict):
            raise RuntimeError("acceptance criteria entries must be objects")
        extracted.append(
            AcceptanceCriterion(
                id=str(item["id"]),
                command=str(item["command"]),
                pass_condition=str(item["pass_condition"]),
            )
        )
    return tuple(extracted)


def select_criteria(
    criteria: Sequence[AcceptanceCriterion],
    selected_ids: Sequence[str],
) -> tuple[AcceptanceCriterion, ...]:
    if not selected_ids:
        return tuple(criteria)
    by_id = {criterion.id: criterion for criterion in criteria}
    missing = tuple(criterion_id for criterion_id in selected_ids if criterion_id not in by_id)
    if missing:
        raise RuntimeError(f"unknown acceptance criterion id(s): {', '.join(missing)}")
    return tuple(by_id[criterion_id] for criterion_id in selected_ids)


def run_criterion(criterion: AcceptanceCriterion, *, dry_run: bool) -> dict[str, object]:
    """Run one criterion and return a structured evidence record."""

    started_at = utc_now()
    monotonic_start = time.monotonic()
    if dry_run:
        return {
            "id": criterion.id,
            "command": criterion.command,
            "pass_condition": criterion.pass_condition,
            "status": "DRY_RUN",
            "exit_code": 0,
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_sec": round(time.monotonic() - monotonic_start, 6),
            "stdout": "",
            "stderr": "",
            "stdout_sha256": sha256_text(""),
            "stderr_sha256": sha256_text(""),
        }

    completed = subprocess.run(
        criterion.command,
        cwd=ROOT,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "id": criterion.id,
        "command": criterion.command,
        "pass_condition": criterion.pass_condition,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_sec": round(time.monotonic() - monotonic_start, 6),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": sha256_text(completed.stdout),
        "stderr_sha256": sha256_text(completed.stderr),
    }


def build_report(
    contract_path: Path,
    selected_ids: Sequence[str],
    *,
    dry_run: bool,
) -> dict[str, object]:
    contract = read_validated_contract(contract_path)
    selected = select_criteria(acceptance_criteria(contract), selected_ids)
    started_at = utc_now()
    monotonic_start = time.monotonic()
    results = [run_criterion(criterion, dry_run=dry_run) for criterion in selected]
    status = "PASS" if all(result["exit_code"] == 0 for result in results) else "FAIL"
    if dry_run:
        status = "DRY_RUN"
    return {
        "artifact_id": contract.get("artifact_id"),
        "schema_version": contract.get("schema_version"),
        "status": status,
        "dry_run": dry_run,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_sec": round(time.monotonic() - monotonic_start, 6),
        "tool_versions": collect_tool_versions(),
        "criteria": results,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="Validation contract manifest to execute",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ID",
        help="Run only one acceptance criterion id; repeatable",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the execution plan without running commands",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Evidence output format",
    )
    return parser.parse_args(argv)


def emit_report(report: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(
        "rust-accel validation contract "
        f"status={report['status']} dry_run={str(report['dry_run']).lower()}"
    )
    criteria = report.get("criteria", [])
    if not isinstance(criteria, list):
        raise RuntimeError("report criteria must be a list")
    for criterion in criteria:
        assert isinstance(criterion, dict)
        print(
            f"- {criterion['id']}: status={criterion['status']} "
            f"exit_code={criterion['exit_code']} command={criterion['command']}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = build_report(args.contract, args.only, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    emit_report(report, args.format)
    return 0 if report["status"] in {"PASS", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
