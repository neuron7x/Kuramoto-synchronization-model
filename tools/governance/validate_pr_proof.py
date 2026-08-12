# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Proof-carrying PR-manifest validator.

Lie blocked:
    "PR description = proof"

A PR description is text; a proof is a structured record that names the
lie blocked, the test surface that catches it, the falsifier mutation
that re-introduces the lie, the restore evidence, and the closure
status. This validator enforces the shape of those records under
``.claude/pr_proofs/PR<N>.yaml``.

The validator is stdlib + PyYAML only. No project imports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROOFS_DIR = REPO_ROOT / ".claude" / "pr_proofs"
DEFAULT_OUTPUT = Path("/tmp/geosync_pr_proof_validation.json")

REQUIRED_LIST_FIELDS: tuple[str, ...] = (
    "files_changed",
    "tests_run",
    "falsifier_expected_failure",
    "evidence_paths",
)
REQUIRED_STRING_FIELDS: tuple[str, ...] = (
    "lie_blocked",
    "falsifier_command",
    "restore_command",
    "remaining_uncertainty",
    "closure_status",
)
VALID_CLOSURE = frozenset({"CLOSED", "PARTIAL", "BLOCKED"})


@dataclass(frozen=True)
class ProofError:
    where: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.detail}"


@dataclass
class ProofReport:
    proof_count: int = 0
    valid: bool = True
    errors: list[ProofError] = field(default_factory=list)
    warnings: list[ProofError] = field(default_factory=list)
    proof_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proof_count": self.proof_count,
            "valid": self.valid,
            "errors": [str(e) for e in self.errors],
            "warnings": [str(w) for w in self.warnings],
            "proof_files": sorted(self.proof_files),
        }


def _check_pr_number(pid: str, pr: Any) -> list[ProofError]:
    if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
        return [ProofError(pid, "BAD_PR_NUMBER", f"pr_number must be a positive int (got {pr!r})")]
    return []


def _check_string(pid: str, key: str, value: Any) -> list[ProofError]:
    if not isinstance(value, str) or not value.strip():
        return [ProofError(pid, "EMPTY_STRING", f"{key} must be a non-empty string")]
    return []


def _check_non_empty_list(pid: str, key: str, value: Any) -> list[ProofError]:
    if not isinstance(value, list) or len(value) == 0:
        return [ProofError(pid, "EMPTY_LIST", f"{key} must be a non-empty list")]
    for i, entry in enumerate(value):
        if not isinstance(entry, str) or not entry.strip():
            return [
                ProofError(
                    pid,
                    "BAD_LIST_ENTRY",
                    f"{key}[{i}] must be a non-empty string (got {entry!r})",
                )
            ]
    return []


def _check_closure(pid: str, status: Any, payload: dict[str, Any]) -> list[ProofError]:
    errors: list[ProofError] = []
    if status not in VALID_CLOSURE:
        errors.append(
            ProofError(
                pid,
                "BAD_CLOSURE_STATUS",
                f"closure_status must be one of {sorted(VALID_CLOSURE)} (got {status!r})",
            )
        )
        return errors
    if status == "CLOSED":
        for key in (
            "falsifier_command",
            "falsifier_expected_failure",
            "restore_command",
            "evidence_paths",
        ):
            value = payload.get(key)
            if not value:
                errors.append(
                    ProofError(
                        pid,
                        "CLOSED_MISSING_EVIDENCE",
                        f"closure_status=CLOSED requires {key} to be non-empty",
                    )
                )
    return errors


def validate_proof_payload(payload: dict[str, Any], where: str) -> list[ProofError]:
    """Validate a single proof record. ``where`` is used as the locator."""
    errors: list[ProofError] = []
    if not isinstance(payload, dict):
        return [ProofError(where, "NOT_A_MAPPING", "proof must be a YAML mapping")]
    pid = str(payload.get("pr_number") or where)

    errors.extend(_check_pr_number(pid, payload.get("pr_number")))
    for key in REQUIRED_STRING_FIELDS:
        if key not in payload:
            errors.append(ProofError(pid, "MISSING_KEY", f"required key absent: {key}"))
            continue
        errors.extend(_check_string(pid, key, payload[key]))
    for key in REQUIRED_LIST_FIELDS:
        if key not in payload:
            errors.append(ProofError(pid, "MISSING_KEY", f"required key absent: {key}"))
            continue
        errors.extend(_check_non_empty_list(pid, key, payload[key]))
    errors.extend(_check_closure(pid, payload.get("closure_status"), payload))
    return errors


def validate_proofs_dir(proofs_dir: Path) -> ProofReport:
    """Validate every proof file in ``proofs_dir``. Empty dir is valid."""
    report = ProofReport()
    if not proofs_dir.exists():
        return report
    for path in sorted(proofs_dir.glob("PR*.yaml")):
        report.proof_count += 1
        report.proof_files.append(str(path.relative_to(proofs_dir.parent.parent)))
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            report.errors.append(ProofError(str(path), "YAML_PARSE_ERROR", str(exc)))
            continue
        report.errors.extend(validate_proof_payload(data, str(path)))
    report.valid = not report.errors
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PR-proof manifests")
    parser.add_argument(
        "--proofs-dir",
        type=Path,
        default=DEFAULT_PROOFS_DIR,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_proofs_dir(args.proofs_dir)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    if not report.valid:
        print(
            f"FAIL: PR proofs have {len(report.errors)} validation error(s):",
            file=sys.stderr,
        )
        for e in report.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: {report.proof_count} PR proof(s) validated cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
