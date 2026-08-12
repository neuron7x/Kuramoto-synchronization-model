#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reproducible MFN integration capsule — build and verify.

This is the first *real* hash-pinned artifact graph in the repository. Until it
existed, ``scripts/ci/prove_repo_integrity.sh`` honestly reported
``MANIFEST_PROOF: NOT_PROVEN`` because a vacuous pass over zero tracked artifacts
is not proof of integrity.

The capsule is the byte-deterministic output of the dependency-light MFN
gateway (``geosync.mfn.cli``) under a pinned seed and ``SOURCE_DATE_EPOCH``. It
is **not** an empirical evidence artifact: the MFN bundle self-labels
``claim_tier: INSTRUMENTED``, ``decision: OBSERVE``, ``falsification_status:
BLOCKED``. What it proves is *integrity and reproducibility*: a committed
artifact whose SHA-256 in ``manifest.json`` matches the file on disk, and which
regenerates bit-for-bit from its declared command.

Two modes::

    python scripts/reproduce/mfn_capsule.py --build    # (re)generate + write manifest
    python scripts/reproduce/mfn_capsule.py --verify    # prove on-disk == regenerated

``--verify`` is the CI contract: it regenerates the bundle into a temp dir and
fails closed if any committed file's digest drifts, or if the manifest digests
do not match the committed files. Stdlib-only by design so it runs in the
dependency-light MFN lane.

Exit codes::

    0  — capsule is reproducible and every manifest digest matches
    1  — drift detected (non-reproducible bundle or stale manifest)
    2  — usage error
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# _REPO_ROOT locates the real checkout for running the generator and reading
# git provenance; it is never reassigned. ROOT resolves artifact paths and may
# be monkeypatched onto a sandbox copy in negative tests.
_REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = _REPO_ROOT
CAPSULE_DIR = ROOT / "artifacts" / "reproducible_capsules" / "mfn_integration_seed7_p256"
BUNDLE_DIR = CAPSULE_DIR / "bundle"
MANIFEST_PATH = CAPSULE_DIR / "manifest.json"
SUMS_NAME = "SHA256SUMS"

# Pinned reproducibility parameters. SOURCE_DATE_EPOCH matches the value the
# MFN release gate uses (.github/workflows/mfn-release-gate.yml) so the capsule
# and that gate agree on the byte-exact bundle.
SEED = 7
POINTS = 256
SOURCE_DATE_EPOCH = "1700000000"
GENERATOR = (
    "SOURCE_DATE_EPOCH=1700000000 python -m geosync.mfn.cli "
    "--out <dir> --seed 7 --points 256 run"
)
VERIFY_COMMAND = "python scripts/reproduce/mfn_capsule.py --verify"

# Fixed identity fields — see schemas/reproducible_capsule.schema.json.
SCHEMA_VERSION = "geosync.reproducible_capsule.v1"
CAPSULE_ID = "mfn_integration_seed7_p256"
ARTIFACT_ROLE = "instrumentation_capsule"
EVIDENCE_CLASS = "REPRODUCIBLE_INFRASTRUCTURE_PROOF"
CLAIM_BOUNDARY = (
    "This capsule proves infrastructure reproducibility and integrity only. It is "
    "the byte-deterministic output of the dependency-light MFN gateway and is never "
    "empirical market evidence. The bundle self-labels INSTRUMENTED / OBSERVE / "
    "BLOCKED and makes no falsifiable scientific claim (see PRODUCT_CATEGORY.md)."
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_REL_PATH_RE = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/-]+$")

# Fields verify() requires before it trusts a manifest. Kept in sync with the
# JSON Schema's `required`, but enforced here with the stdlib so --verify stays
# dependency-light (the MFN gateway is stdlib-only by contract).
_REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "schema_version",
    "capsule_id",
    "artifact_role",
    "evidence_class",
    "is_empirical_evidence",
    "generator",
    "git_sha",
    "source_date_epoch",
    "created_at_utc",
    "verify_command",
    "artifacts",
    "sha256_manifest",
    "claim_boundary",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    """Repository git SHA the capsule is generated against (provenance)."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _created_at_utc() -> str:
    """Deterministic ISO-8601 UTC stamp derived from SOURCE_DATE_EPOCH."""
    stamp = _dt.datetime.fromtimestamp(int(SOURCE_DATE_EPOCH), tz=_dt.timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_bundle(out_dir: Path) -> None:
    """Run the MFN gateway deterministically into *out_dir*."""
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    env["PYTHONPATH"] = f"{_REPO_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "geosync.mfn.cli",
            "--out",
            str(out_dir),
            "--seed",
            str(SEED),
            "--points",
            str(POINTS),
            "run",
        ],
        cwd=_REPO_ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _bundle_files(bundle_dir: Path) -> list[Path]:
    return sorted(p for p in bundle_dir.iterdir() if p.is_file())


def build() -> int:
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    BUNDLE_DIR.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "bundle"
        _generate_bundle(staging)
        shutil.copytree(staging, BUNDLE_DIR)

    artifacts = []
    for path in _bundle_files(BUNDLE_DIR):
        artifacts.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )

    sums_path = BUNDLE_DIR / SUMS_NAME
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "capsule_id": CAPSULE_ID,
        "artifact_role": ARTIFACT_ROLE,
        "evidence_class": EVIDENCE_CLASS,
        "is_empirical_evidence": False,
        "generator": GENERATOR,
        "git_sha": _git_sha(),
        "source_date_epoch": int(SOURCE_DATE_EPOCH),
        "created_at_utc": _created_at_utc(),
        "verify_command": VERIFY_COMMAND,
        "artifacts": artifacts,
        "sha256_manifest": _sha256(sums_path),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"capsule built: {len(artifacts)} artifacts -> {MANIFEST_PATH.relative_to(ROOT)}")
    return 0


def _validate_manifest_structure(manifest: Any) -> list[str]:
    """Stdlib structural validation mirroring the JSON Schema's hard invariants.

    Fail-closed: a manifest that is missing provenance, claims empirical
    evidence, or carries malformed digests/paths is rejected before any
    reproduction work is trusted. Full JSON-Schema validation additionally runs
    in tests/CI; this keeps --verify dependency-light.
    """
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]

    for field in _REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    if manifest["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if manifest["artifact_role"] != ARTIFACT_ROLE:
        errors.append(f"artifact_role must be {ARTIFACT_ROLE!r}")
    if manifest["evidence_class"] != EVIDENCE_CLASS:
        errors.append(f"evidence_class must be {EVIDENCE_CLASS!r}")
    if manifest["is_empirical_evidence"] is not False:
        errors.append("is_empirical_evidence must be false (capsule is never evidence)")
    if not isinstance(manifest["generator"], str) or not manifest["generator"].strip():
        errors.append("generator must be a non-empty string")
    if not isinstance(manifest["git_sha"], str) or not _SHA1_RE.match(manifest["git_sha"]):
        errors.append("git_sha must be a 40-hex SHA-1 string")
    if not isinstance(manifest["source_date_epoch"], int) or isinstance(
        manifest["source_date_epoch"], bool
    ):
        errors.append("source_date_epoch must be an integer")
    if not isinstance(manifest["verify_command"], str) or not manifest["verify_command"].strip():
        errors.append("verify_command must be a non-empty string")
    if not isinstance(manifest["sha256_manifest"], str) or not _SHA256_RE.match(
        manifest["sha256_manifest"]
    ):
        errors.append("sha256_manifest must be a 64-hex SHA-256 string")
    if not isinstance(manifest["claim_boundary"], str) or not manifest["claim_boundary"].strip():
        errors.append("claim_boundary must be a non-empty string")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        return errors
    for i, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            errors.append(f"artifacts[{i}] must be an object")
            continue
        rel = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("bytes")
        if not isinstance(rel, str) or not _REL_PATH_RE.match(rel):
            errors.append(f"artifacts[{i}].path must be a safe repo-relative path")
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            errors.append(f"artifacts[{i}].sha256 must be a 64-hex SHA-256 string")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append(f"artifacts[{i}].bytes must be a non-negative integer")
    return errors


def verify() -> int:
    failures: list[str] = []

    # 0. Manifest must exist and be parseable JSON.
    if not MANIFEST_PATH.exists():
        print(f"missing manifest: {MANIFEST_PATH.relative_to(ROOT)}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1

    # 1. Manifest structure: required provenance, fixed evidence class, honest
    #    is_empirical_evidence, well-formed digests/paths. Fail closed before
    #    trusting any digest the manifest declares.
    structure_errors = _validate_manifest_structure(manifest)
    if structure_errors:
        print("MFN capsule verification FAILED (manifest structure):", file=sys.stderr)
        for err in structure_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    artifacts = manifest["artifacts"]

    # 2. On-disk committed files match their declared digests.
    declared_bundle_names: set[str] = set()
    for entry in artifacts:
        rel, expected = entry["path"], entry["sha256"]
        declared_bundle_names.add(Path(rel).name)
        target = ROOT / rel
        if not target.exists():
            failures.append(f"declared artifact missing on disk: {rel}")
            continue
        actual = _sha256(target)
        if actual != expected:
            failures.append(f"manifest digest stale for {rel}: {expected} != {actual}")

    # 3. No unlisted (untracked) file may hide in the bundle directory.
    if BUNDLE_DIR.exists():
        on_disk = {p.name for p in _bundle_files(BUNDLE_DIR)}
        for extra in sorted(on_disk - declared_bundle_names):
            failures.append(f"untracked bundle file not in manifest: bundle/{extra}")

    # 4. The committed bundle regenerates bit-for-bit from its declared command.
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "bundle"
        _generate_bundle(fresh)
        committed = {p.name: p for p in _bundle_files(BUNDLE_DIR)} if BUNDLE_DIR.exists() else {}
        regenerated = {p.name: p for p in _bundle_files(fresh)}
        if committed.keys() != regenerated.keys():
            failures.append(
                f"bundle file set drifted: committed={sorted(committed)} "
                f"regenerated={sorted(regenerated)}"
            )
        for name in sorted(committed.keys() & regenerated.keys()):
            if _sha256(committed[name]) != _sha256(regenerated[name]):
                failures.append(f"non-reproducible bundle file: bundle/{name}")

    if failures:
        print("MFN capsule verification FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(
        f"MFN capsule verification PASSED: {len(artifacts)} artifacts reproduced "
        "and digests match."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="(re)generate capsule + manifest")
    group.add_argument("--verify", action="store_true", help="prove on-disk == regenerated")
    args = parser.parse_args(argv)
    if args.build:
        return build()
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
