#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

EVIDENCE_PATH = Path("reports/test_audit/evidence_index.json")
REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_FIELDS = {
    "claim_id",
    "claim_text",
    "domain",
    "claim_status",
    "command",
    "artifact_path",
    "verdict",
    "release_decision",
}
ALLOWED_STATUSES = {"proven", "partial", "goal", "remove", "quarantine"}
GOAL_BAD_RELEASE = {
    "achieved",
    "accepted_as_proven",
    "release_evidence",
    "unrestricted_release",
    "allow",
}
PARTIAL_BAD_RELEASE = {"proven", "accepted_as_proven", "unrestricted_release", "allow"}
QUARANTINE_ALLOWED_RELEASE = {
    "blocked",
    "blocked_as_release_evidence",
    "not_admissible",
    "quarantine",
}
REMOVE_ALLOWED_RELEASE = {"remove", "blocked"}
FAILED_BASELINE_ALLOWED_RELEASE_DECISIONS = {
    "blocked",
    "blocked_as_release_evidence",
    "not_admissible",
    "quarantine",
    "remove",
}


def _clean_artifact_path(raw: str) -> str:
    return raw.strip().strip("`")


def _split_artifact_paths(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [_clean_artifact_path(part) for part in raw.split(",") if part.strip()]


def _resolve_audit_root(evidence_path: Path, audit_root: Path | None) -> Path:
    if audit_root is not None:
        return audit_root
    if evidence_path.resolve() == EVIDENCE_PATH.resolve():
        return Path("reports/test_audit")
    return evidence_path.parent


def _resolve_artifact_path(artifact: str, evidence_path: Path, audit_root: Path) -> Path:
    path = Path(_clean_artifact_path(artifact))
    if path.is_absolute():
        return path

    candidates = [
        audit_root / path,
        evidence_path.parent / path,
        REPO_ROOT / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return audit_root / path


def _failed_baseline_dirs(audit_root: Path) -> set[Path]:
    failed: set[Path] = set()
    for ex in audit_root.glob("baseline_run_*/exit_code.txt"):
        try:
            code = ex.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if code and code != "0":
            failed.add(ex.parent.resolve())
    return failed


def _allows_failed_baseline_artifact(claim: dict[str, Any]) -> bool:
    """Allow failed-baseline artifacts only for explicitly non-release decisions."""
    release_decision = str(claim.get("release_decision", "")).strip().lower()
    return release_decision in FAILED_BASELINE_ALLOWED_RELEASE_DECISIONS


def _artifact_in_failed_baseline(artifact_path: Path, failed_dirs: set[Path]) -> bool:
    ap = artifact_path.resolve()
    for d in failed_dirs:
        if d in ap.parents or ap == d:
            return True
    return False


def _verify_manifest(audit_root: Path, allowed_dirs: set[Path] | None) -> list[str]:
    if allowed_dirs is not None and not allowed_dirs:
        return []

    manifests: list[Path] = []
    if allowed_dirs is None:
        manifests = sorted(audit_root.glob("baseline_run_*/artifact_manifest.sha256"))
    else:
        for baseline_dir in sorted(allowed_dirs):
            manifest = baseline_dir / "artifact_manifest.sha256"
            if manifest.exists():
                manifests.append(manifest)

    errors: list[str] = []
    for manifest in manifests:
        baseline_dir = manifest.parent
        try:
            lines = manifest.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            errors.append(f"Unable to read manifest {manifest}: {exc}")
            continue

        for line in lines:
            entry = line.strip()
            if not entry:
                continue
            chunks = entry.split(maxsplit=1)
            if len(chunks) != 2:
                errors.append(f"Malformed manifest entry in {manifest}: {entry}")
                continue

            expected_hash, rel_path = chunks
            target = baseline_dir / rel_path.strip()
            if not target.exists():
                errors.append(f"manifest missing file: {target.as_posix()}")
                continue

            actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                errors.append(f"manifest hash mismatch: {target.as_posix()}")

    return errors


def _referenced_baseline_dirs(
    claims: list[dict[str, Any]], audit_root: Path, evidence_path: Path
) -> set[Path]:
    referenced: set[Path] = set()
    root = audit_root.resolve()

    for claim in claims:
        for artifact in _split_artifact_paths(str(claim.get("artifact_path", ""))):
            artifact_path = _resolve_artifact_path(artifact, evidence_path, audit_root)
            try:
                rel = artifact_path.resolve().relative_to(root)
            except ValueError:
                continue
            parts = rel.parts
            if parts and parts[0].startswith("baseline_run_"):
                referenced.add(root / parts[0])

    return referenced


def validate(
    evidence_path: Path = EVIDENCE_PATH,
    *,
    audit_root: Path | None = None,
    manifest_scope: str = "all",
) -> list[str]:
    if not evidence_path.exists():
        return [f"Evidence index not found: {evidence_path}"]

    errors: list[str] = []
    try:
        doc = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as exc:
        return [f"Invalid evidence index JSON: {exc}"]
    if doc.get("schema_version") != "1.1":
        errors.append("schema_version must be 1.1")

    claims = doc.get("claims")
    if not isinstance(claims, list):
        return ["claims must be a list"]

    root = _resolve_audit_root(evidence_path, audit_root)
    failed_dirs = _failed_baseline_dirs(root)

    for c in claims:
        if not isinstance(c, dict):
            errors.append(f"<non-dict-claim>: invalid claim entry type {type(c).__name__}")
            continue

        missing = [f for f in REQUIRED_FIELDS if f not in c]
        if missing:
            errors.append(f"{c.get('claim_id','<missing-id>')}: missing fields {missing}")
            continue

        cid = str(c["claim_id"])
        st = str(c["claim_status"])
        rd = str(c["release_decision"]).strip().lower()

        if st not in ALLOWED_STATUSES:
            errors.append(f"{cid}: invalid status {st}")
            continue

        if st == "proven":
            for f in ("command", "artifact_path", "last_verified_sha", "timestamp_utc"):
                if not str(c.get(f, "")).strip():
                    errors.append(f"{cid}: proven missing {f}")

            for raw_artifact in _split_artifact_paths(str(c.get("artifact_path", ""))):
                artifact_path = _resolve_artifact_path(raw_artifact, evidence_path, root)
                if not artifact_path.exists():
                    errors.append(f"{cid}: artifact missing {raw_artifact}")
                    continue
                if _artifact_in_failed_baseline(
                    artifact_path, failed_dirs
                ) and not _allows_failed_baseline_artifact(c):
                    errors.append(
                        f"{cid}: proven uses failed baseline artifact {artifact_path} "
                        f"without explicit non-release decision"
                    )

        if st == "goal" and rd in GOAL_BAD_RELEASE:
            errors.append(f"{cid}: goal has invalid release_decision={rd}")
        if st == "partial" and rd in PARTIAL_BAD_RELEASE:
            errors.append(f"{cid}: partial has invalid release_decision={rd}")
        if st == "quarantine" and rd not in QUARANTINE_ALLOWED_RELEASE:
            errors.append(f"{cid}: quarantine has invalid release_decision={rd}")
        if st == "remove" and rd not in REMOVE_ALLOWED_RELEASE:
            errors.append(f"{cid}: remove has invalid release_decision={rd}")

    if manifest_scope == "referenced":
        manifest_dirs = _referenced_baseline_dirs(claims, root, evidence_path)
    elif manifest_scope == "all":
        manifest_dirs = None
    elif manifest_scope == "none":
        manifest_dirs = set()
    else:
        return [f"Invalid manifest_scope: {manifest_scope}"]

    errors.extend(_verify_manifest(root, manifest_dirs))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate claims have evidence.")
    parser.add_argument("--evidence-index", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--audit-root", type=Path, default=None)
    parser.add_argument(
        "--manifest-scope",
        choices=("referenced", "all", "none"),
        default="all",
    )
    args = parser.parse_args(argv)

    errors = validate(
        args.evidence_index,
        audit_root=args.audit_root,
        manifest_scope=args.manifest_scope,
    )
    if errors:
        print("CLAIM EVIDENCE VALIDATION FAILED")
        for e in errors:
            print(f" - {e}")
        return 1

    print("Claim evidence validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
