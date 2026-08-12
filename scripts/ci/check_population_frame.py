#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate for the flagship population / sampling frame (task RES-006).

FLAGSHIP-RQ-001 is an infrastructure / synthetic-only research question about
wheel-contract reproducibility over the repository build artifact. Its
population is therefore NOT markets or instruments; it is the population of
first-party modules / import sites in the pinned repo snapshot. This gate proves
that the canonical population frame at ``data/frames/flagship_population.json``:

  1. is structurally complete — every required frame field is present;
  2. carries an immutable, reproducible digest (sha256) over the pinned tree;
  3. states inclusion AND exclusion rules (a frame with neither is not a frame);
  4. makes NO external-validity claim — the population must generalize to the
     pinned snapshot ONLY. A frame that asserts generalization beyond the
     snapshot is FLAGGED and fails closed;
  5. records honest limitations (snapshot-only + synthetic-only boundary).

Optionally (``--verify-digest``, on by default when git + the pinned commit are
available) it RECOMPUTES the population digest from the pinned commit and proves
it equals the recorded value — closing reproducibility of the selection.

This is a POPULATION-FRAME gate. It does NOT validate dataset_manifest.v1 files;
that is scripts/ci/check_dataset_manifests.py (DAT-001). See
docs/POPULATION_FRAME_POLICY.md.

Exit codes::

    0  — frame complete, digest present (and, if checked, reproducible), no
         external-validity claim
    1  — FAIL (RED): missing required field / missing inclusion or exclusion /
         missing or malformed digest / an external-generalization claim / a
         digest that does not reproduce
    2  — manifest missing or unparseable (cannot establish the frame; fail-closed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "frames" / "flagship_population.json"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Required top-level fields that make a population frame a frame.
REQUIRED_FIELDS = (
    "manifest_version",
    "id",
    "rq_id",
    "unit_of_analysis",
    "target_population",
    "generalizes_beyond_snapshot",
    "pinned_snapshot",
    "frame",
    "inclusion_rules",
    "exclusion_rules",
    "coverage",
    "missingness",
    "population_digest",
    "limitations",
)

# Substrings that betray an external-validity / beyond-snapshot generalization
# claim in free text. Presence (outside an explicit disclaimer) is FLAGGED.
_GENERALIZATION_MARKERS = (
    "generalizes to other repositories",
    "generalizes to other repos",
    "generalizes beyond this snapshot",
    "generalizes beyond the snapshot",
    "external validity holds",
    "applies to other commits",
    "applies to any repository",
    "representative of other repositories",
    "out-of-sample edge",
    "generalizes to the market",
    "generalizes to markets",
)


def _fail(problems: list[str], msg: str) -> None:
    problems.append(msg)


def _is_nonempty_rulelist(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(x, str) and x.strip() for x in value)


def compute_frame_digest(commit: str, namespaces: set[str], root: Path) -> str | None:
    """Recompute the population digest from the pinned commit.

    Mirrors data/frames/flagship_population.json population_digest.construction:
    sha256 over sorted 'path blobsha\\n' lines of frame members at the pinned
    tree. Returns None when git or the commit is unavailable (cannot verify).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", commit],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    vendor_markers = ("/vendor/", "/vendored/", "/third_party/", "/_vendor/")
    gen_suffixes = ("_pb2.py", "_pb2_grpc.py")
    gen_markers = ("/generated/", "/_generated/")

    lines: list[str] = []
    for raw in out.splitlines():
        meta, _, path = raw.partition("\t")
        parts = meta.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        sha = parts[2]
        if not path.endswith(".py"):
            continue
        top = path.split("/", 1)[0]
        if top not in namespaces:
            continue
        probe = "/" + path
        if any(m in probe for m in vendor_markers):
            continue
        if path.endswith(gen_suffixes) or any(m in probe for m in gen_markers):
            continue
        lines.append(f"{path} {sha}\n")

    lines.sort()
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def check_frame(doc: dict[str, Any], root: Path, verify_digest: bool) -> list[str]:
    problems: list[str] = []

    # 1. required fields present.
    for field in REQUIRED_FIELDS:
        if field not in doc:
            _fail(problems, f"missing required field: {field!r}")

    # 3. inclusion AND exclusion rules must both be present and non-empty.
    if not _is_nonempty_rulelist(doc.get("inclusion_rules")):
        _fail(problems, "inclusion_rules missing or empty — an unspecified frame is not a frame")
    if not _is_nonempty_rulelist(doc.get("exclusion_rules")):
        _fail(problems, "exclusion_rules missing or empty — inclusion without exclusion is undefined")

    # 2. immutable, well-formed digest.
    pd = doc.get("population_digest")
    recorded_digest: str | None = None
    if not isinstance(pd, dict):
        _fail(problems, "population_digest missing or not an object")
    else:
        if pd.get("algorithm") != "sha256":
            _fail(problems, "population_digest.algorithm must be 'sha256'")
        value = pd.get("value")
        if not isinstance(value, str) or not SHA256_RE.match(value):
            _fail(problems, "population_digest.value missing or not a 64-hex sha256")
        else:
            recorded_digest = value

    # pinned snapshot must carry a concrete commit sha.
    snap = doc.get("pinned_snapshot")
    commit: str | None = None
    if not isinstance(snap, dict):
        _fail(problems, "pinned_snapshot missing or not an object")
    else:
        commit = snap.get("commit")
        if not isinstance(commit, str) or not re.match(r"^[0-9a-f]{7,40}$", commit):
            _fail(problems, "pinned_snapshot.commit missing or not a git sha")
            commit = None

    # 4. NO external-validity / beyond-snapshot generalization claim.
    gen = doc.get("generalizes_beyond_snapshot")
    if gen is not False:
        _fail(
            problems,
            "FLAGGED: generalizes_beyond_snapshot must be false (explicit). "
            f"got {gen!r} — the frame may claim external validity only via a NEW study.",
        )
    ext = doc.get("external_validity_claim")
    if ext not in (None, False, "", "none", "None"):
        _fail(
            problems,
            f"FLAGGED: external_validity_claim must be null/absent; got {ext!r}.",
        )
    # Scan free text (limitations, target_population, rationale) for smuggled claims.
    scan_blobs: list[str] = []
    tp = doc.get("target_population")
    if isinstance(tp, str):
        scan_blobs.append(tp)
    for lim in doc.get("limitations") or []:
        if isinstance(lim, str):
            scan_blobs.append(lim)
    rationale = doc.get("interpretation_rationale")
    if isinstance(rationale, str):
        scan_blobs.append(rationale)
    haystack = "  ".join(scan_blobs).lower()
    for marker in _GENERALIZATION_MARKERS:
        if marker in haystack:
            _fail(
                problems,
                f"FLAGGED: free text asserts external generalization ({marker!r}); "
                "the population must generalize to the pinned snapshot only.",
            )

    # 5. honest limitations, including the snapshot-only boundary.
    lims = doc.get("limitations")
    if not _is_nonempty_rulelist(lims):
        _fail(problems, "limitations missing or empty — population limitations must be explicit")
    else:
        joined = " ".join(lims).lower()
        if "snapshot" not in joined:
            _fail(problems, "limitations must state the snapshot-only boundary")

    # 6 (optional). reproduce the digest from the pinned commit.
    if verify_digest and commit and recorded_digest and not problems:
        frame = doc.get("frame") or {}
        namespaces = set(frame.get("namespaces") or [])
        if not namespaces:
            _fail(problems, "frame.namespaces empty — cannot reproduce digest")
        else:
            recomputed = compute_frame_digest(commit, namespaces, root)
            if recomputed is None:
                print(
                    "  info: pinned commit not resolvable in this checkout — "
                    "digest reproducibility not verified (structure OK).",
                    file=sys.stderr,
                )
            elif recomputed != recorded_digest:
                _fail(
                    problems,
                    "population_digest.value does not reproduce from pinned commit "
                    f"{commit}: recorded={recorded_digest} recomputed={recomputed}",
                )
            else:
                print(f"  ok: digest reproduces from pinned commit {commit[:12]}")

    return problems


def run(manifest: Path, root: Path, verify_digest: bool) -> int:
    if not manifest.exists():
        print(f"population frame manifest not found: {manifest}", file=sys.stderr)
        return 2
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{manifest.name}: invalid JSON ({exc})", file=sys.stderr)
        return 2
    if not isinstance(doc, dict):
        print(f"{manifest.name}: top-level must be an object", file=sys.stderr)
        return 2

    problems = check_frame(doc, root, verify_digest)
    if problems:
        print(
            f"\nPopulation frame gate FAILED (RED): {len(problems)} problem(s).",
            file=sys.stderr,
        )
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(
        f"Population frame gate PASSED: {manifest.name} — "
        f"frame size {doc.get('frame', {}).get('size')}, "
        f"snapshot-only, digest {doc['population_digest']['value'][:12]}…"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the flagship population / sampling frame (RES-006)."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Population frame manifest (default: data/frames/flagship_population.json).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repo root used to resolve the pinned commit (default: repo root).",
    )
    parser.add_argument(
        "--no-verify-digest",
        dest="verify_digest",
        action="store_false",
        help="Skip recomputing the digest from the pinned commit (structure only).",
    )
    args = parser.parse_args(argv)
    return run(args.manifest, args.root, args.verify_digest)


if __name__ == "__main__":
    raise SystemExit(main())
