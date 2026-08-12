#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify SHA-256 integrity for contract manifests with artifact digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Distinct from G-ROOT-MANIFEST (check_root_manifest.py). This gate ONLY covers
# artifact manifest.json digests — it never opens the root MANIFEST.sha256. See
# docs/RELEASE_GATES.md. A PASS here is not root-manifest integrity.
GATE_ID = "G-ARTIFACT-MANIFESTS"


def _is_tracked(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _discover_manifest_paths() -> list[Path]:
    manifests: list[Path] = []
    for path in ROOT.rglob("manifest.json"):
        if ".git/" in path.as_posix():
            continue
        if _is_tracked(path):
            manifests.append(path)
    return sorted(manifests)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-artifacts",
        type=int,
        default=0,
        help="Fail if fewer than N artifact digests were verified. Proof mode: a "
        "vacuous pass over 0 artifacts is not proof of integrity.",
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Shorthand for --min-artifacts 1.",
    )
    args = parser.parse_args(argv)
    min_artifacts = max(args.min_artifacts, 1 if args.require_artifacts else 0)

    failures: list[str] = []
    checked = 0

    for manifest in _discover_manifest_paths():
        if not manifest.exists():
            failures.append(f"missing manifest: {manifest.relative_to(ROOT).as_posix()}")
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        # Evidence-freshness manifests use the artifact/artifact_sha256 schema and
        # are verified by scripts/ci/check_artifact_freshness.py, not this contract
        # hash gate. Skip them so their entries are not misread as path-missing.
        if str(payload.get("schema", "")).startswith("evidence_artifact_freshness"):
            continue
        artifacts = payload.get("artifacts", [])
        if not artifacts:
            continue
        for artifact in artifacts:
            rel = artifact.get("path")
            expected = artifact.get("sha256")
            if not isinstance(rel, str) or not rel:
                failures.append(f"{manifest.name}: artifact entry missing valid path")
                continue
            if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                failures.append(f"{manifest.name}: invalid sha256 for {rel}")
                continue
            target = ROOT / rel
            if not target.exists():
                failures.append(f"{manifest.name}: missing artifact {rel}")
                continue
            actual = _sha256(target)
            checked += 1
            if actual != expected:
                failures.append(
                    f"{manifest.name}: checksum mismatch for {rel} (expected {expected}, got {actual})"
                )

    if failures:
        print("Manifest hash verification failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    if checked < min_artifacts:
        print(
            f"Manifest hash verification NOT PROVEN: {checked} artifact(s) verified, "
            f"--min-artifacts={min_artifacts} required. A vacuous pass over zero "
            "tracked manifest artifacts is not proof of integrity."
        )
        return 1

    print(f"Manifest hash verification passed ({checked} artifacts).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
