#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Byte-reproducible source-archive gate for GeoSync (REL-010).

Runs ``scripts/release/build_source_archive.sh`` **twice** with a FIXED
``SOURCE_DATE_EPOCH`` and asserts fail-closed that:

1. the two independent builds produce a BYTE-IDENTICAL archive (identical
   sha256);
2. the archive contains ONLY release-approved files — its member list equals
   ``git ls-files`` for the archived ref (tracked content only, no untracked or
   ignored cruft);
3. the pinned prefix ``geosync-<version>/`` is present on every member.

On success it writes a real, machine-generated receipt to
``artifacts/release/reproducible_build_report.json`` containing the two digests,
``match=true``, the file count, and the ``SOURCE_DATE_EPOCH`` used. Every /tmp
archive it creates is removed; a hundreds-of-MB tarball is NEVER left behind and
is NEVER written into the repository.

Exit codes:
    0  all assertions pass; receipt written
    2  contract/assertion failure (digest mismatch, untracked member, bad prefix)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "release" / "build_source_archive.sh"
REPORT_PATH = ROOT / "artifacts" / "release" / "reproducible_build_report.json"


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _canonical_epoch(ref: str) -> int:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "show", "-s", "--format=%at", ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return int(out)


def _git_tracked(ref: str) -> set[str]:
    """Return the flattened file set of the *tree* at *ref*, unquoted UTF-8.

    We compare against the commit's tree (``ls-tree -r``), not the index: the
    builder archives the commit object, whose content is exactly this flattened
    tree — the precise oracle for what ``git archive`` emits. For a clean HEAD
    worktree this equals ``git ls-files``.
    """
    raw = subprocess.run(
        ["git", "-C", str(ROOT), "-c", "core.quotepath=false",
         "ls-tree", "-r", "--name-only", "-z", ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return {p for p in raw.split("\0") if p}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_once(out_dir: Path, epoch: int, ref: str) -> Path:
    """Invoke the deterministic builder; return the archive path it wrote."""
    proc = subprocess.run(
        [str(BUILD_SCRIPT), str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": _env_path(),
            "SOURCE_DATE_EPOCH": str(epoch),
            "GEOSYNC_REF": ref,
        },
        cwd=str(ROOT),
    )
    archive: Path | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("ARCHIVE="):
            archive = Path(line.split("=", 1)[1])
    if archive is None or not archive.exists():
        raise SystemExit(f"builder produced no archive; stdout={proc.stdout!r}")
    return archive


def _env_path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")


def _archive_members(archive: Path, prefix: str) -> set[str]:
    """Return tracked-file member paths (prefix stripped, dirs dropped)."""
    members: set[str] = set()
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            if m.isdir():
                continue
            name = m.name
            if not name.startswith(prefix):
                raise SystemExit(
                    f"archive member {name!r} lacks pinned prefix {prefix!r}"
                )
            members.add(name[len(prefix):])
    return members


def main() -> int:
    ap = argparse.ArgumentParser(description="REL-010 reproducible-archive gate")
    ap.add_argument("--ref", default="HEAD", help="git ref to archive (default HEAD)")
    ap.add_argument(
        "--epoch",
        type=int,
        default=None,
        help="fixed SOURCE_DATE_EPOCH (default: author date of --ref)",
    )
    args = ap.parse_args()

    ref = args.ref
    version = _version()
    prefix = f"geosync-{version}/"
    epoch = args.epoch if args.epoch is not None else _canonical_epoch(ref)

    with tempfile.TemporaryDirectory(prefix="rel010-a-") as d1, \
            tempfile.TemporaryDirectory(prefix="rel010-b-") as d2:
        a1 = _build_once(Path(d1), epoch, ref)
        a2 = _build_once(Path(d2), epoch, ref)
        sha1 = _sha256(a1)
        sha2 = _sha256(a2)
        members = _archive_members(a1, prefix)

    tracked = _git_tracked(ref)
    extra = sorted(members - tracked)  # in archive but NOT tracked -> cruft
    missing = sorted(tracked - members)  # tracked but absent from archive

    match = sha1 == sha2
    tracked_only = not extra and not missing

    report = {
        "task": "REL-010",
        # Deterministic: a reproducible-build report must itself reproduce. Tie the
        # stamp to SOURCE_DATE_EPOCH (the build's fixed source date), not wall-clock
        # now(), so two regens at the same source state are byte-identical.
        "generated_utc": _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).isoformat(),
        "ref": ref,
        "resolved_commit": subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", ref],
            check=True, capture_output=True, text=True,
        ).stdout.strip(),
        "version": version,
        "prefix": prefix,
        "source_date_epoch": epoch,
        "build_1_sha256": sha1,
        "build_2_sha256": sha2,
        "match": match,
        "archive_file_count": len(members),
        "git_tracked_count": len(tracked),
        "tracked_only": tracked_only,
        "untracked_members": extra,
        "missing_members": missing,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")

    ok = match and tracked_only
    status = "PASS" if ok else "FAIL"
    print(f"[REL-010] {status}: match={match} tracked_only={tracked_only} "
          f"files={len(members)} epoch={epoch}")
    print(f"[REL-010]   build_1 sha256={sha1}")
    print(f"[REL-010]   build_2 sha256={sha2}")
    if extra:
        print(f"[REL-010]   UNTRACKED members ({len(extra)}): {extra[:5]}", file=sys.stderr)
    if missing:
        print(f"[REL-010]   MISSING members ({len(missing)}): {missing[:5]}", file=sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
