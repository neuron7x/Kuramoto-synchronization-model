"""Claim ledger validator — gates CLAIMS.yaml against six-condition validity.

Run via:

    python .claude/claims/validate_claims.py
    python .claude/claims/validate_claims.py --ledger path/to/claims.yaml

Exit code is non-zero when any claim in tier ACTIVE/PARTIAL fails its
contract. Used in pre-commit and pr-gate.yml to fail closed when a claim
regresses below evidence threshold.

The validator is intentionally stdlib + PyYAML only; no project imports,
so it can run in a fresh CI environment without the project installed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO_ROOT / ".claude" / "claims" / "CLAIMS.yaml"


class ClaimClass(str, Enum):
    SECURITY = "SECURITY"
    SCIENTIFIC = "SCIENTIFIC"
    FINANCIAL = "FINANCIAL"
    RELIABILITY = "RELIABILITY"
    REPRODUCIBILITY = "REPRODUCIBILITY"
    PERFORMANCE = "PERFORMANCE"
    ARCHITECTURE = "ARCHITECTURE"
    GOVERNANCE = "GOVERNANCE"


class ClaimTier(str, Enum):
    FACT = "FACT"
    EXTRAPOLATION = "EXTRAPOLATION"
    SPECULATION = "SPECULATION"


class ClaimStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


VALID_EVIDENCE_TYPES = frozenset(
    {
        "FILE_DECLARATION",
        "LOCKFILE_PIN",
        "RESOLVER_OUTPUT",
        "SCANNER_OUTPUT",
        "RUNTIME_IMPORT_SMOKE",
        "UNIT_TEST",
        "INTEGRATION_TEST",
        "MUTATION_TEST",
        "CI_STATUS",
        "MANUAL_INSPECTION",
        "EXTERNAL_ADVISORY",
        "BENCHMARK",
        "DATASET_RESULT",
    }
)

REQUIRED_FIELDS = (
    "claim_id",
    "statement",
    "class",
    "tier",
    "evidence_paths",
    "test_paths",
    "falsifier",
    "owner_surface",
    "last_verified_command",
    "status",
)


@dataclass(frozen=True)
class ValidationError:
    claim_id: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.claim_id}: {self.detail}"


def _missing_fields(claim: dict[str, Any]) -> list[str]:
    return [f for f in REQUIRED_FIELDS if f not in claim]


def _evidence_types(claim: dict[str, Any]) -> set[str]:
    return {
        str(ev.get("type", "")) for ev in claim.get("evidence_paths") or [] if isinstance(ev, dict)
    }


def _evidence_paths_exist(claim: dict[str, Any], repo_root: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    cid = str(claim.get("claim_id", "<unknown>"))
    for entry in claim.get("evidence_paths") or []:
        if not isinstance(entry, dict):
            errors.append(ValidationError(cid, "EVIDENCE_PATH_SHAPE", f"non-dict entry: {entry!r}"))
            continue
        path = entry.get("path")
        if not path:
            errors.append(
                ValidationError(cid, "EVIDENCE_PATH_MISSING", "evidence entry has no 'path'")
            )
            continue
        target = repo_root / str(path)
        if not target.exists():
            errors.append(
                ValidationError(
                    cid,
                    "EVIDENCE_PATH_NOT_FOUND",
                    f"evidence path does not exist: {path}",
                )
            )
        ev_type = entry.get("type")
        if ev_type not in VALID_EVIDENCE_TYPES:
            errors.append(
                ValidationError(
                    cid,
                    "EVIDENCE_TYPE_UNKNOWN",
                    f"unknown evidence type: {ev_type!r}",
                )
            )
    for entry in claim.get("test_paths") or []:
        target = repo_root / str(entry)
        if not target.exists():
            errors.append(
                ValidationError(
                    cid,
                    "TEST_PATH_NOT_FOUND",
                    f"test path does not exist: {entry}",
                )
            )
    return errors


def _validate_claim(claim: dict[str, Any], repo_root: Path) -> list[ValidationError]:
    errors: list[ValidationError] = []
    cid = str(claim.get("claim_id", "<unknown>"))

    missing = _missing_fields(claim)
    if missing:
        errors.append(ValidationError(cid, "MISSING_FIELD", f"missing fields: {missing}"))
        return errors

    cls = claim["class"]
    tier = claim["tier"]
    status = claim["status"]
    evidence_paths = claim.get("evidence_paths") or []
    test_paths = claim.get("test_paths") or []
    falsifier = (claim.get("falsifier") or "").strip()
    owner_surface = (claim.get("owner_surface") or "").strip()
    non_testable_reason = (claim.get("non_testable_reason") or "").strip()

    if cls not in {c.value for c in ClaimClass}:
        errors.append(ValidationError(cid, "BAD_CLASS", f"unknown class: {cls!r}"))
    if tier not in {t.value for t in ClaimTier}:
        errors.append(ValidationError(cid, "BAD_TIER", f"unknown tier: {tier!r}"))
    if status not in {s.value for s in ClaimStatus}:
        errors.append(ValidationError(cid, "BAD_STATUS", f"unknown status: {status!r}"))

    # RETIRED and REJECTED entries are not gated; they exist for audit trail.
    if status in {ClaimStatus.RETIRED.value, ClaimStatus.REJECTED.value}:
        # Still verify referenced files do not silently disappear.
        errors.extend(_evidence_paths_exist(claim, repo_root))
        if (
            status == ClaimStatus.REJECTED.value
            and not (claim.get("rejection_reason") or "").strip()
        ):
            errors.append(
                ValidationError(
                    cid,
                    "REJECTED_NO_REASON",
                    "REJECTED claim must include rejection_reason",
                )
            )
        return errors

    if not owner_surface:
        errors.append(ValidationError(cid, "NO_OWNER_SURFACE", "claim has no owner_surface"))

    if tier == ClaimTier.FACT.value and not evidence_paths:
        errors.append(
            ValidationError(
                cid,
                "FACT_NO_EVIDENCE",
                "FACT tier requires at least one evidence_path",
            )
        )

    if tier == ClaimTier.FACT.value and not test_paths and not non_testable_reason:
        errors.append(
            ValidationError(
                cid,
                "FACT_NO_TEST",
                "FACT tier requires test_paths OR an explicit non_testable_reason",
            )
        )

    if not falsifier:
        errors.append(ValidationError(cid, "NO_FALSIFIER", "claim has no falsifier"))

    ev_types = _evidence_types(claim)

    if cls == ClaimClass.SECURITY.value:
        # Active SECURITY claims must rest on at least one of:
        #   SCANNER_OUTPUT, EXTERNAL_ADVISORY, LOCKFILE_PIN, FILE_DECLARATION
        # MANUAL_INSPECTION alone is insufficient — exposes the F03 trap.
        sec_evidence = {
            "SCANNER_OUTPUT",
            "EXTERNAL_ADVISORY",
            "LOCKFILE_PIN",
            "FILE_DECLARATION",
            "RESOLVER_OUTPUT",
        }
        if tier == ClaimTier.FACT.value and not ev_types & sec_evidence:
            errors.append(
                ValidationError(
                    cid,
                    "SECURITY_FACT_INSUFFICIENT_EVIDENCE",
                    "SECURITY/FACT requires SCANNER_OUTPUT / EXTERNAL_ADVISORY / "
                    "LOCKFILE_PIN / FILE_DECLARATION / RESOLVER_OUTPUT evidence",
                )
            )

    if cls == ClaimClass.SCIENTIFIC.value:
        if not falsifier:
            errors.append(
                ValidationError(
                    cid,
                    "SCIENTIFIC_NO_FALSIFIER",
                    "SCIENTIFIC claim must include a falsifier",
                )
            )

    if cls == ClaimClass.PERFORMANCE.value:
        perf_evidence = {"BENCHMARK", "DATASET_RESULT", "RESOLVER_OUTPUT"}
        if tier == ClaimTier.FACT.value and not ev_types & perf_evidence:
            errors.append(
                ValidationError(
                    cid,
                    "PERFORMANCE_FACT_NO_BENCHMARK",
                    "PERFORMANCE/FACT requires BENCHMARK or DATASET_RESULT evidence",
                )
            )

    errors.extend(_evidence_paths_exist(claim, repo_root))
    return errors


def _validate_unique_ids(claims: Sequence[dict[str, Any]]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    seen: set[str] = set()
    for claim in claims:
        cid = str(claim.get("claim_id", ""))
        if not cid:
            errors.append(ValidationError("<unknown>", "MISSING_CLAIM_ID", "claim has no claim_id"))
            continue
        if cid in seen:
            errors.append(
                ValidationError(cid, "DUPLICATE_CLAIM_ID", "claim_id appears multiple times")
            )
        seen.add(cid)
    return errors


def validate_ledger(ledger_path: Path, repo_root: Path | None = None) -> list[ValidationError]:
    """Validate a CLAIMS.yaml file. Returns a list of errors (empty == valid)."""
    repo_root = repo_root or REPO_ROOT
    if not ledger_path.exists():
        return [ValidationError("<ledger>", "LEDGER_NOT_FOUND", f"ledger not found: {ledger_path}")]
    raw = ledger_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        return [ValidationError("<ledger>", "YAML_PARSE_ERROR", str(exc))]
    if not isinstance(data, dict):
        return [ValidationError("<ledger>", "LEDGER_SHAPE", "top-level must be a mapping")]
    if data.get("schema_version") != 1:
        return [
            ValidationError(
                "<ledger>",
                "SCHEMA_VERSION",
                f"unsupported schema_version: {data.get('schema_version')!r}",
            )
        ]
    claims = data.get("claims") or []
    if not isinstance(claims, list):
        return [ValidationError("<ledger>", "CLAIMS_SHAPE", "`claims` must be a list")]

    errors: list[ValidationError] = []
    errors.extend(_validate_unique_ids(claims))
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append(
                ValidationError(
                    "<unknown>", "CLAIM_SHAPE", f"claim entry must be a mapping: {claim!r}"
                )
            )
            continue
        errors.extend(_validate_claim(claim, repo_root))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the GeoSync claim ledger")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
        help="path to CLAIMS.yaml (default: .claude/claims/CLAIMS.yaml)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root used to resolve evidence paths",
    )
    args = parser.parse_args(argv)
    errors = validate_ledger(args.ledger, args.repo_root)
    if errors:
        print(f"FAIL: claim ledger has {len(errors)} validation error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK: claim ledger validated ({args.ledger})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
