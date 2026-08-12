#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-evidence preservation gate for RIP/TOMBSTONES.md.

GeoSync doctrine: *no negative-evidence path means no truth-seeking*. A
dead hypothesis is only honestly dead if its falsified artifact stays
in the tree, sha-anchored, where anyone can re-read why it failed. A
tombstone that points at a deleted artifact is a silent retraction —
the failure record evaporates while the headstone still claims it
exists.

The ``check_research_artifact_truth`` gate proves the *forward*
direction (a PASS artifact may not carry the fingerprints of no data).
This gate proves the *preservation* direction: every entry in
``RIP/TOMBSTONES.md`` must

  1. carry a SHA anchor (a 40-hex merged-commit sha — the entry is
     pinned to history, not free-floating prose), and
  2. reference at least one in-repo artifact path that still EXISTS.

A missing artifact, a missing sha, or an entry with no locatable
artifact path fails the build. The negative record cannot be silently
deleted while its tombstone survives.

Run::

    python scripts/ci/check_tombstone_preservation.py

Exit codes::

    0  — every tombstone is sha-anchored and its negative artifact(s) exist
    1  — at least one tombstone lost its sha anchor or its artifact
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOMBSTONES_PATH = ROOT / "RIP" / "TOMBSTONES.md"

# Entry header: a level-2 markdown heading ("## CALIB-GRID-001 — ...").
_ENTRY_HEADER = re.compile(r"^##\s+(?P<name>\S.*?)\s*$")
# A 40-hex git sha (full). Anchors the entry to a merged commit.
_SHA40 = re.compile(r"\b[0-9a-f]{40}\b")
# A backtick-quoted token that looks like a repo-relative file path:
# contains a "/" and ends in a file extension, no whitespace.
_BACKTICK_PATH = re.compile(r"`([^`\s]*/[^`\s]*\.[A-Za-z0-9_]+)`")
# Marks the artifact line(s) within an entry.
_ARTIFACT_MARKER = "**ARTIFACT**"


@dataclass(frozen=True)
class Tombstone:
    name: str
    start_line: int
    body: str
    artifact_paths: tuple[str, ...]
    has_sha: bool


@dataclass
class _Acc:
    name: str
    start_line: int
    lines: list[str] = field(default_factory=list)


def _parse_tombstones(text: str) -> list[Tombstone]:
    """Split TOMBSTONES.md into entries and extract sha + artifact paths.

    The preamble before the first ``##`` header is ignored — it is the
    document's own description, not a tombstone.
    """
    accs: list[_Acc] = []
    current: _Acc | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        header = _ENTRY_HEADER.match(raw)
        if header:
            current = _Acc(name=header.group("name"), start_line=lineno)
            accs.append(current)
            continue
        if current is not None:
            current.lines.append(raw)

    tombstones: list[Tombstone] = []
    for acc in accs:
        body = "\n".join(acc.lines)
        has_sha = bool(_SHA40.search(body))
        # Collect artifact paths from the lines tied to the ARTIFACT marker.
        # The path may sit on the marker line or wrap to following lines, so
        # we scan from the marker until the next bold-key bullet.
        artifact_paths: list[str] = []
        in_artifact = False
        for line in acc.lines:
            stripped = line.strip()
            if _ARTIFACT_MARKER in line:
                in_artifact = True
            elif in_artifact and stripped.startswith("- **"):
                in_artifact = False
            if in_artifact:
                artifact_paths.extend(_BACKTICK_PATH.findall(line))
        tombstones.append(
            Tombstone(
                name=acc.name,
                start_line=acc.start_line,
                body=body,
                artifact_paths=tuple(dict.fromkeys(artifact_paths)),  # de-dup, keep order
                has_sha=has_sha,
            )
        )
    return tombstones


def _validate(tombstones: list[Tombstone], root: Path) -> list[str]:
    failures: list[str] = []
    for t in tombstones:
        loc = f"RIP/TOMBSTONES.md:{t.start_line} [{t.name}]"
        if not t.has_sha:
            failures.append(
                f"{loc}: no 40-hex SHA anchor — entry is free-floating, not pinned to history"
            )
        if not t.artifact_paths:
            failures.append(
                f"{loc}: no locatable artifact path under **ARTIFACT** — "
                f"a dead hypothesis must point at its preserved negative artifact"
            )
            continue
        for rel in t.artifact_paths:
            if not (root / rel).exists():
                failures.append(
                    f"{loc}: negative artifact missing: {rel} — "
                    f"silent retraction (the failure record was deleted while the tombstone survives)"
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tombstones", type=Path, default=TOMBSTONES_PATH)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if not args.tombstones.is_file():
        print(f"FAIL: tombstone ledger not found: {args.tombstones}", file=sys.stderr)
        return 1

    text = args.tombstones.read_text(encoding="utf-8")
    tombstones = _parse_tombstones(text)
    if not tombstones:
        print(
            "FAIL: no tombstone entries parsed — the negative-evidence ledger "
            "is empty or its '## <NAME>' structure changed.",
            file=sys.stderr,
        )
        return 1

    failures = _validate(tombstones, args.root)
    if failures:
        print(
            f"FAIL: {len(failures)} negative-evidence preservation violation(s) "
            f"across {len(tombstones)} tombstone(s):",
            file=sys.stderr,
        )
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    total_artifacts = sum(len(t.artifact_paths) for t in tombstones)
    print(
        f"PASS: {len(tombstones)} tombstone(s) sha-anchored; "
        f"{total_artifacts} negative artifact(s) preserved on disk."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
