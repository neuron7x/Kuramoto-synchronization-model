# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""WP-01 — PR Collision Governance Protocol.

Research question: how do we stop two open PRs from closing the *same* claim?

A "lane collision" is two open, non-draft PRs that edit the same
single-source-of-truth governance file, or that reference the same Task/P0/WP
lane token AND touch an overlapping file. Merging both produces governance
schizophrenia on a gate that is supposed to have one owner (exactly the
#1120 / #1121 Task-2 dependency-all-strict situation).

The detection core (:func:`detect_collisions`) is pure and offline-testable: it
takes a list of PR descriptors and returns the collisions. The live mode reads
open PRs via ``gh`` so the same logic can run as an operator scan or CI gate.

Run::

    python tools/governance/check_pr_lane_collision.py            # live, via gh
    python tools/governance/check_pr_lane_collision.py --input prs.json
    python tools/governance/check_pr_lane_collision.py --json

Exit code 0 iff no lane collision among open non-draft PRs; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from itertools import combinations
from typing import Any

# Single-source-of-truth files where two concurrent edits = governance drift.
CRITICAL_GLOBS: tuple[str, ...] = (
    "tools/security/*.py",
    "tools/governance/*.py",
    "tools/claims/*.py",
    "tools/release/*.py",
    "governance/*.yaml",
    "governance/*.yml",
    "schemas/**",
    "requirements*.txt",
    "constraints/*.txt",
    "pyproject.toml",
    ".claude/physics/INVARIANTS.yaml",
)

# Lane tokens: Task N, P0-N, P1-N, WP-NN — normalized lowercase, no spaces.
_LANE_TOKEN = re.compile(r"\b(task\s*\d+|p[012]-\d+|wp-?\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PullRequest:
    """Minimal PR descriptor the collision core operates on."""

    number: int
    title: str
    files: tuple[str, ...]
    is_draft: bool = False
    state: str = "OPEN"


@dataclass(frozen=True)
class Collision:
    a: int
    b: int
    shared_critical_files: tuple[str, ...]
    shared_lane_tokens: tuple[str, ...]

    def reason(self) -> str:
        parts: list[str] = []
        if self.shared_critical_files:
            parts.append(f"shared source-of-truth files: {', '.join(self.shared_critical_files)}")
        if self.shared_lane_tokens:
            parts.append(f"shared lane token(s): {', '.join(self.shared_lane_tokens)}")
        return "; ".join(parts)


def _is_critical(path: str) -> bool:
    return any(fnmatch(path, glob) for glob in CRITICAL_GLOBS)


def lane_tokens(title: str) -> set[str]:
    """Normalized lane tokens in a PR title (lowercased, spaces stripped)."""
    return {m.group(1).lower().replace(" ", "") for m in _LANE_TOKEN.finditer(title)}


def detect_collisions(prs: list[PullRequest]) -> list[Collision]:
    """Return every lane collision among open, non-draft PRs.

    Two PRs collide if they share a critical source-of-truth file, OR they share
    a lane token AND overlap on any changed file. A shared lane token alone (no
    file overlap) is NOT a collision — different work may reference one task.
    """
    active = [p for p in prs if p.state.upper() == "OPEN" and not p.is_draft]
    collisions: list[Collision] = []
    for a, b in combinations(active, 2):
        files_a, files_b = set(a.files), set(b.files)
        shared_files = files_a & files_b
        shared_critical = tuple(sorted(f for f in shared_files if _is_critical(f)))
        shared_tokens = tuple(sorted(lane_tokens(a.title) & lane_tokens(b.title)))
        collide = bool(shared_critical) or (bool(shared_tokens) and bool(shared_files))
        if collide:
            collisions.append(
                Collision(
                    a=a.number,
                    b=b.number,
                    shared_critical_files=shared_critical,
                    shared_lane_tokens=shared_tokens,
                )
            )
    return collisions


def _run_gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def load_open_prs_via_gh() -> list[PullRequest]:
    """Read open PRs and their changed files via the gh CLI (live mode)."""
    listing = json.loads(
        _run_gh(["pr", "list", "--state", "open", "--json", "number,title,isDraft,state"])
    )
    prs: list[PullRequest] = []
    for item in listing:
        number = int(item["number"])
        files_raw = json.loads(_run_gh(["pr", "view", str(number), "--json", "files"]))
        files = tuple(sorted(f["path"] for f in files_raw.get("files", [])))
        prs.append(
            PullRequest(
                number=number,
                title=str(item["title"]),
                files=files,
                is_draft=bool(item.get("isDraft", False)),
                state=str(item.get("state", "OPEN")),
            )
        )
    return prs


def _prs_from_dicts(data: list[dict[str, Any]]) -> list[PullRequest]:
    return [
        PullRequest(
            number=int(d["number"]),
            title=str(d.get("title", "")),
            files=tuple(d.get("files", [])),
            is_draft=bool(d.get("isDraft", d.get("is_draft", False))),
            state=str(d.get("state", "OPEN")),
        )
        for d in data
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file of PR descriptors (offline mode)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            prs = _prs_from_dicts(json.load(fh))
    else:
        try:
            prs = load_open_prs_via_gh()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"FAIL: cannot read open PRs via gh: {exc}", file=sys.stderr)
            return 2

    collisions = detect_collisions(prs)
    if args.json:
        print(
            json.dumps(
                {
                    "open_prs": len(prs),
                    "collisions": [
                        {
                            "a": c.a,
                            "b": c.b,
                            "shared_critical_files": list(c.shared_critical_files),
                            "shared_lane_tokens": list(c.shared_lane_tokens),
                        }
                        for c in collisions
                    ],
                    "passed": not collisions,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("=" * 64)
        print("PR Lane Collision Gate")
        print("=" * 64)
        print(
            f"Open non-draft PRs scanned: {sum(1 for p in prs if p.state.upper() == 'OPEN' and not p.is_draft)}"
        )
        if collisions:
            print(f"\nLANE COLLISIONS ({len(collisions)}):")
            for c in collisions:
                print(f"  [X] #{c.a} <-> #{c.b}: {c.reason()}")
            print("\nFAIL — close or merge one canonical PR per lane before proceeding.")
        else:
            print("\nNo lane collisions among open PRs.\nPASS")
    return 0 if not collisions else 1


if __name__ == "__main__":
    sys.exit(main())
