#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Clean-clone smoke test for the canonical GeoSync release bundle (REL-006).

Builds a canonical release bundle to /tmp via
``scripts/release/build_canonical_bundle.sh``, clones it into a throwaway temp
directory, and asserts fail-closed that:

1. a *plain* ``git clone`` (no manual ref selection) checks out the canonical
   release tree ``9060de4a097ea467f7ab5d52ecb660ba345f671b``;
2. ``git fsck --strict`` on the clone exits 0;
3. no *required* commit (the canonical commit itself) is reported dangling, and
   the total dangling count is 0.

On success it writes a real, machine-generated receipt to
``artifacts/release/bundle_clone_receipt.json`` and cleans up every /tmp
artifact it created (bundle + clone). A ~150 MB bundle is NEVER left behind and
is NEVER written into the repository.

Exit codes:
    0  all assertions pass; receipt written
    2  contract/assertion failure (tree mismatch, fsck fail, dangling object)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "release" / "build_canonical_bundle.sh"
RECEIPT_PATH = ROOT / "artifacts" / "release" / "bundle_clone_receipt.json"

CANONICAL_TAG = "geosync-canonical-8080e4b4"
EXPECTED_COMMIT = "8080e4b475efe054901804f25b37b80bd06203f4"
EXPECTED_TREE = "9060de4a097ea467f7ab5d52ecb660ba345f671b"

GATE_ID = "G-RELEASE-BUNDLE-CLONE"


class CheckError(RuntimeError):
    """A fail-closed contract violation."""


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _build_bundle(out_path: Path) -> list[str]:
    """Build the canonical bundle; return its named refs (heads + tags)."""
    proc = _run(["bash", str(BUILD_SCRIPT), str(out_path)])
    if proc.returncode != 0:
        raise CheckError(
            f"build_canonical_bundle.sh exited {proc.returncode}\n{proc.stderr}"
        )
    if not out_path.is_file():
        raise CheckError(f"bundle not produced at {out_path}")

    heads = _run(["git", "bundle", "list-heads", str(out_path)])
    if heads.returncode != 0:
        raise CheckError(f"git bundle list-heads failed:\n{heads.stderr}")
    refs = sorted(
        line.split()[1]
        for line in heads.stdout.splitlines()
        if len(line.split()) == 2 and line.split()[1].startswith("refs/")
    )
    return refs


def _clone_and_inspect(bundle: Path, workdir: Path) -> dict[str, object]:
    """Plain-clone the bundle and inspect the resulting HEAD/tree/fsck state."""
    clone_dir = workdir / "clone"
    clone = _run(["git", "clone", "--quiet", str(bundle), str(clone_dir)])
    if clone.returncode != 0:
        raise CheckError(f"git clone of bundle failed:\n{clone.stderr}")

    head_commit = _run(["git", "rev-parse", "HEAD"], cwd=clone_dir).stdout.strip()
    head_tree = _run(["git", "rev-parse", "HEAD^{tree}"], cwd=clone_dir).stdout.strip()
    head_branch = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone_dir
    ).stdout.strip()

    fsck = _run(["git", "fsck", "--strict"], cwd=clone_dir)
    fsck_output = (fsck.stdout + fsck.stderr).strip()
    dangling_lines = [
        ln for ln in fsck_output.splitlines() if ln.startswith("dangling")
    ]

    return {
        "head_branch": head_branch,
        "head_commit": head_commit,
        "head_tree": head_tree,
        "fsck_exit": fsck.returncode,
        "fsck_output": fsck_output,
        "dangling_lines": dangling_lines,
    }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def run_check(keep: bool = False) -> dict[str, object]:
    """Execute build -> clone -> fsck end to end and return the receipt dict."""
    if not BUILD_SCRIPT.is_file():
        raise CheckError(f"missing build script: {BUILD_SCRIPT}")

    workdir = Path(tempfile.mkdtemp(prefix="geosync-bundle-clone."))
    bundle = workdir / f"{CANONICAL_TAG}.bundle"
    try:
        refs = _build_bundle(bundle)
        inspect = _clone_and_inspect(bundle, workdir)

        # --- Fail-closed assertions ------------------------------------------
        _assert(
            refs == sorted(["refs/heads/main", f"refs/tags/{CANONICAL_TAG}"]),
            f"bundle refs are not exactly the canonical pair: {refs}",
        )
        _assert(
            inspect["head_commit"] == EXPECTED_COMMIT,
            f"clone HEAD commit {inspect['head_commit']!r} != {EXPECTED_COMMIT}",
        )
        _assert(
            inspect["head_tree"] == EXPECTED_TREE,
            f"clone HEAD tree {inspect['head_tree']!r} != canonical {EXPECTED_TREE}",
        )
        _assert(
            inspect["fsck_exit"] == 0,
            f"git fsck --strict exited {inspect['fsck_exit']}:\n"
            f"{inspect['fsck_output']}",
        )
        dangling_lines = inspect["dangling_lines"]
        assert isinstance(dangling_lines, list)
        _assert(
            len(dangling_lines) == 0,
            f"fsck reported {len(dangling_lines)} dangling object(s): "
            f"{dangling_lines}",
        )

        receipt = {
            "gate_id": GATE_ID,
            "task": "REL-006",
            "generated_utc": _dt.datetime.now(_dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "canonical_tag": CANONICAL_TAG,
            "canonical_commit": EXPECTED_COMMIT,
            "expected_tree": EXPECTED_TREE,
            "bundle": {
                "built_by": "scripts/release/build_canonical_bundle.sh",
                "refs_included": refs,
                "ref_count": len(refs),
                "note": "built to /tmp only; ~150MB binary never committed",
            },
            "clone": {
                "mode": "plain git clone (no manual ref selection)",
                "head_branch": inspect["head_branch"],
                "head_commit": inspect["head_commit"],
                "head_tree": inspect["head_tree"],
                "tree_matches_canonical": inspect["head_tree"] == EXPECTED_TREE,
            },
            "fsck": {
                "command": "git fsck --strict",
                "exit_code": inspect["fsck_exit"],
                "result": "PASS" if inspect["fsck_exit"] == 0 else "FAIL",
                "dangling_count": len(dangling_lines),
            },
            "verdict": "PASS",
        }
        return receipt
    finally:
        if not keep:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"[keep] left workdir at {workdir}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=RECEIPT_PATH,
        help="Where to write the JSON receipt (default: %(default)s).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do not delete the /tmp bundle+clone (debugging only).",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run assertions but do not write the receipt file.",
    )
    args = parser.parse_args(argv)

    try:
        receipt = run_check(keep=args.keep)
    except CheckError as exc:
        print(f"{GATE_ID}: FAIL: {exc}", file=sys.stderr)
        return 2

    if not args.no_write:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"{GATE_ID}: PASS — receipt written to {args.receipt}")
    else:
        print(f"{GATE_ID}: PASS — {json.dumps(receipt)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
