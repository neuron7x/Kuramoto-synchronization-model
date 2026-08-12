#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regenerate MANIFEST.sha256 — the source-integrity cold-verify manifest.

The release gate's ``D.manifest`` probe cold-verifies that every entry in
``MANIFEST.sha256`` matches the working tree byte-for-byte. The manifest is a
supply-chain integrity proof: it certifies the cryptographic fingerprint of
every *source/config* file under version control.

Scope policy (explicit and reproducible, so the manifest is not a hand-rolled
snapshot that silently rots):

* Cover every git-tracked file …
* … EXCEPT ``MANIFEST.sha256`` itself (a file cannot hash its own hash), and
* … EXCEPT the ``artifacts/`` tree, which holds machine-generated evidence
  that the gate regenerates on every ``--deep`` run (e.g. the clean-clone
  probe records a temp install path). Pinning volatile machine output would
  make the integrity manifest self-defeating — it would go RED on the very
  next gate run. Artifact integrity is instead carried by each artifact's own
  ``artifact_sha256`` self-hash (see ``scripts/ci/proof_common.py``).

Run::

    python scripts/ci/generate_manifest.py            # write MANIFEST.sha256
    python scripts/ci/generate_manifest.py --check     # verify, exit 1 on drift

Regenerating is a deliberate act (the manifest declares "this is the tree at
this commit"); commit the result alongside the change that moved the tree.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "MANIFEST.sha256"
MANIFEST_REL = "MANIFEST.sha256"
EXCLUDE_PREFIXES: tuple[str, ...] = ("artifacts/",)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tracked_files(root: Path = ROOT) -> list[str]:
    proc = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _in_scope(rel: str) -> bool:
    if rel == MANIFEST_REL:
        return False
    return not any(rel.startswith(p) for p in EXCLUDE_PREFIXES)


def build_manifest(root: Path = ROOT) -> list[str]:
    """Return sorted ``<sha256>  ./<rel>`` lines for every in-scope tracked file."""
    lines: list[str] = []
    for rel in _tracked_files(root):
        if not _in_scope(rel):
            continue
        target = root / rel
        if not target.is_file():  # deleted-but-staged / symlink to nowhere
            continue
        lines.append(f"{_sha256(target)}  ./{rel}")
    return sorted(lines)


def _rel_of(line: str) -> str:
    parts = line.split(None, 1)
    return parts[1] if len(parts) == 2 else line


def cold_verify(root: Path = ROOT) -> tuple[bool, str]:
    """Authoritative cold-verify: manifest file-set MUST equal the in-scope
    git-tracked file-set AND every per-file hash must match byte-for-byte.

    This is a *symmetric set comparison* over the freshly-rebuilt manifest
    (``build_manifest`` walks ``git ls-files``), so it fails closed on all
    three tamper classes — not just a mismatched hash on a still-listed file:

    * a file whose recorded hash no longer matches its bytes  (mismatch),
    * a tracked in-scope file with NO line in the manifest    (uncovered),
    * a manifest line with no matching tracked file           (stale/dropped).

    The single source of truth for both ``check_root_manifest.py`` (via
    ``check``) and the release gate's ``D.manifest`` probe — the two
    cold-verify surfaces must never diverge.
    """
    manifest = root / MANIFEST_REL
    if not manifest.exists():
        return False, "MANIFEST.sha256 absent"
    want = manifest.read_text(encoding="utf-8").strip().splitlines()
    have = build_manifest(root)
    if want == have:
        return True, f"MANIFEST.sha256 cold-verify clean ({len(have)} entries)"
    want_paths = {_rel_of(w) for w in want}
    have_paths = {_rel_of(h) for h in have}
    added = set(have) - set(want)  # lines the tree has that the manifest lacks
    removed = set(want) - set(have)  # lines the manifest has that the tree lacks
    added_paths = {_rel_of(x) for x in added}
    removed_paths = {_rel_of(x) for x in removed}
    mismatch = sorted(added_paths & removed_paths)  # listed but wrong hash
    uncovered = sorted(have_paths - want_paths)  # tracked file absent from manifest
    stale = sorted(want_paths - have_paths)  # manifest line with no tracked file
    example = (mismatch or uncovered or stale or [""])[0]
    detail = (
        f"MANIFEST.sha256 cold-verify FAILED: {len(mismatch)} mismatch, "
        f"{len(uncovered)} uncovered (tracked but unlisted), "
        f"{len(stale)} stale/dropped (listed but untracked); e.g. {example}"
    )
    return False, detail


def _dirty_in_scope(root: Path = ROOT) -> list[str]:
    """In-scope tracked files that differ between the working tree and HEAD.

    Covers modified, staged-new (appears as an addition vs HEAD), and deleted
    tracked files. Returns [] when the repo has no commits yet (nothing to
    compare against) or when git is unavailable — the guard must never itself
    become a false failure on a legitimately clean CI checkout.
    """
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        return []
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted({f for f in proc.stdout.splitlines() if f.strip() and _in_scope(f)})


def write(root: Path = ROOT, allow_dirty: bool = False) -> int:
    if not allow_dirty:
        dirty = _dirty_in_scope(root)
        if dirty:
            print(
                "REFUSING to regenerate MANIFEST.sha256: "
                f"{len(dirty)} in-scope tracked file(s) differ between the working "
                f"tree and HEAD (e.g. {dirty[0]}). The manifest hashes working-tree "
                "bytes while the file-set comes from the git index, so regenerating "
                "on a dirty tree certifies content that diverges from the committed "
                "tree — a partial commit then reads GREEN locally but RED on a fresh "
                "clone. Commit the source change first, then regenerate; pass "
                "--allow-dirty only for a deliberate working-tree snapshot."
            )
            return 2
    lines = build_manifest(root)
    manifest = root / MANIFEST_REL
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_REL} with {len(lines)} entries.")
    return 0


def check(root: Path = ROOT) -> int:
    ok, msg = cold_verify(root)
    print(msg if ok else msg + " (drift)")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="regenerate even when tracked files diverge from HEAD (deliberate snapshot)",
    )
    args = parser.parse_args(argv)
    return check() if args.check else write(allow_dirty=args.allow_dirty)


if __name__ == "__main__":
    raise SystemExit(main())
