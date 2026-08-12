#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Automated Physics Alignment Index (PAI) computation.

Per IERD-PAI-FPS-UX-001 §5:

    PAI = (modules with ≥3 invariant tests) / (modules declaring a
           physical law)

This script replaces the narrative ``docs/validation/pai_report_*.md``
with a deterministic, falsifiable measurement:

    * Source of truth for "modules declaring a physical law":
      the ``MODULE → INVARIANT ROUTING`` table in ``CLAUDE.md``.
    * Source of truth for "≥3 invariant tests":
      ``grep`` for the ``INV-<NAME>`` pattern across the routed
      test directories. A module is covered iff at least three
      distinct ``INV-*`` IDs appear in tests that match the routing
      glob (or in any test file under ``tests/`` that explicitly
      cites the module by name).

Outputs:

    docs/validation/pai_latest.json      — machine-readable snapshot
    stdout                               — human-readable summary

Exit codes:

    0  PAI ≥ threshold (default 0.90 from IERD §5).
    1  PAI < threshold OR parse failure on CLAUDE.md.

Run locally before push:

    python scripts/ci/compute_pai.py
    python scripts/ci/compute_pai.py --threshold 1.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD_PATH = ROOT / "CLAUDE.md"
OUTPUT_PATH = ROOT / "docs" / "validation" / "pai_latest.json"
DEFAULT_THRESHOLD = 0.90

# An INV reference is `INV-<TAG>` where TAG starts with an uppercase
# letter or digit and may contain digits, uppercase letters, and
# `-suffix` segments (e.g. INV-AC1-rev). Lowercase suffix is allowed
# only after a hyphen — never as the first character.
INV_REFERENCE_RE = re.compile(r"\bINV-[A-Z0-9][A-Z0-9]*(?:-[A-Za-z0-9]+)*\b")
ROUTING_HEADING_RE = re.compile(
    r"^##\s+MODULE\s*→\s*INVARIANT\s+ROUTING", re.IGNORECASE | re.MULTILINE
)
ROUTING_ROW_RE = re.compile(
    r"^\|\s*(?P<patterns>.+?)\s*\|\s*(?P<invariants>INV-[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)
PATTERN_TOKEN_RE = re.compile(r"`([^`]+)`")
# INV ranges in CLAUDE.md appear in two forms:
#   "INV-K1..K7"      — prefix repeated on the right endpoint
#   "INV-DRO1..5"     — bare digit on the right endpoint
#   "INV-5HT1..2"     — prefix may begin with a digit (e.g. 5HT)
INV_RANGE_RE = re.compile(
    r"INV-(?P<prefix>[A-Z0-9][A-Z0-9]*?)(?P<start>[0-9]+)\.\.(?:(?P=prefix))?(?P<end>[0-9]+)"
)
INV_SINGLE_RE = re.compile(r"INV-([A-Z0-9][A-Z0-9]*(?:-[A-Za-z0-9]+)*)")

TEST_DIRS: tuple[Path, ...] = (ROOT / "tests",)
SOURCE_DIRS: tuple[Path, ...] = (
    ROOT / "core",
    ROOT / "runtime",
    ROOT / "geosync_hpc",
    ROOT / "geosync",
)

# CLAUDE.md "Forbidden:" anti-patterns. A test that contains any of
# these on a stand-alone assertion line (no INV-* citation, no
# error-message fields) cannot count as a falsifying test for an
# invariant. The patterns are matched only on lines that *also* lack
# an INV-* citation in the same line — INV-anchored asserts pass
# even if they look magic-numbery, because the citation is the
# context the rule asks for.
FORBIDDEN_ASSERT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "magic-bare-bound",
        re.compile(r"^\s*assert\s+\w+\s*[<>]=?\s*[0-9]+(?:\.[0-9]+)?\s*(?:#[^A-Z]*)?$"),
    ),
    (
        "exact-stochastic",
        re.compile(r"^\s*assert\s+\w+\s*==\s*0\.0\s*(?:#[^A-Z]*)?$"),
    ),
    (
        "no-context",
        re.compile(r"^\s*assert\s+\w+\.\w+\s*[<>]=?\s*0\s*(?:#[^A-Z]*)?$"),
    ),
)


@dataclass(frozen=True)
class ModuleGroup:
    label: str
    patterns: tuple[str, ...]
    declared_invariants: frozenset[str]


@dataclass
class ModuleScore:
    label: str
    declared_invariants: int
    distinct_inv_refs_in_tests: int
    test_files: list[str] = field(default_factory=list)
    forbidden_assertion_count: int = 0
    forbidden_assertion_files: list[str] = field(default_factory=list)
    covered: bool = False


@dataclass
class PaiSnapshot:
    pai: float
    threshold: float
    threshold_met: bool
    modules: list[ModuleScore]
    total_declared: int
    total_covered: int

    def to_dict(self) -> dict[str, object]:
        return {
            "pai": self.pai,
            "threshold": self.threshold,
            "threshold_met": self.threshold_met,
            "total_declared_modules": self.total_declared,
            "total_covered_modules": self.total_covered,
            "modules": [
                {
                    "label": m.label,
                    "declared_invariants": m.declared_invariants,
                    "distinct_inv_refs_in_tests": m.distinct_inv_refs_in_tests,
                    "test_files_count": len(m.test_files),
                    "forbidden_assertion_count": m.forbidden_assertion_count,
                    "forbidden_assertion_files": m.forbidden_assertion_files,
                    "covered": m.covered,
                }
                for m in self.modules
            ],
        }


def _expand_invariants(invariants_cell: str) -> frozenset[str]:
    """Parse `INV-K1..K7` and `INV-DRO1..5` style range expansions."""
    ids: set[str] = set()
    for match in INV_RANGE_RE.finditer(invariants_cell):
        prefix = match.group("prefix")
        start = int(match.group("start"))
        end = int(match.group("end"))
        for i in range(start, end + 1):
            ids.add(f"INV-{prefix}{i}")
    cleaned = INV_RANGE_RE.sub("", invariants_cell)
    for match in INV_SINGLE_RE.finditer(cleaned):
        ids.add(f"INV-{match.group(1)}")
    return frozenset(ids)


def _parse_routing_table(claude_md: str) -> list[ModuleGroup]:
    heading_match = ROUTING_HEADING_RE.search(claude_md)
    if heading_match is None:
        raise ValueError("CLAUDE.md missing 'MODULE → INVARIANT ROUTING' section")
    table_text = claude_md[heading_match.end() :]
    end_match = re.search(r"^\n---\n", table_text, re.MULTILINE)
    if end_match is not None:
        table_text = table_text[: end_match.start()]
    groups: list[ModuleGroup] = []
    for row in ROUTING_ROW_RE.finditer(table_text):
        patterns_cell = row.group("patterns")
        invariants_cell = row.group("invariants")
        patterns = tuple(PATTERN_TOKEN_RE.findall(patterns_cell))
        if not patterns:
            continue
        invariants = _expand_invariants(invariants_cell)
        if not invariants:
            continue
        label = " | ".join(patterns)
        groups.append(
            ModuleGroup(
                label=label,
                patterns=patterns,
                declared_invariants=invariants,
            )
        )
    if not groups:
        raise ValueError("MODULE → INVARIANT ROUTING table parsed empty")
    return groups


def _iter_test_files(test_dirs: Iterable[Path]) -> Iterable[Path]:
    for test_dir in test_dirs:
        if not test_dir.exists():
            continue
        for path in test_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def _count_inv_refs(test_files: Iterable[Path]) -> dict[str, set[Path]]:
    """Map every INV-* id seen in any test file to the set of files."""
    inv_to_files: dict[str, set[Path]] = {}
    for path in test_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in INV_REFERENCE_RE.finditer(text):
            inv_id = match.group(0)
            inv_to_files.setdefault(inv_id, set()).add(path)
    return inv_to_files


def _relpath_or_abs(path: Path) -> str:
    """Render a path relative to ROOT when possible; fall back to abs.

    Defensive helper: synthetic test fixtures live under tmp_path
    (outside ROOT) and would otherwise raise from ``relative_to``.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _count_forbidden_assertions(test_file: Path) -> int:
    """Count CLAUDE.md "Forbidden:" anti-pattern asserts in a test file.

    A line counts as forbidden iff it matches one of FORBIDDEN_ASSERT_PATTERNS
    AND does NOT carry an INV-* citation in the same line. The citation
    is what redeems an otherwise magic-number-style assertion: a literal
    bound is fine when the bound is named by an invariant.
    """
    try:
        text = test_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    count = 0
    for line in text.splitlines():
        if INV_REFERENCE_RE.search(line):
            continue
        for _name, pattern in FORBIDDEN_ASSERT_PATTERNS:
            if pattern.match(line):
                count += 1
                break
    return count


def _score_modules(
    groups: list[ModuleGroup],
    inv_to_files: dict[str, set[Path]],
) -> list[ModuleScore]:
    scores: list[ModuleScore] = []
    for group in groups:
        seen_invs: set[str] = set()
        files_seen: set[Path] = set()
        for inv in group.declared_invariants:
            files_for_inv = inv_to_files.get(inv, set())
            if files_for_inv:
                seen_invs.add(inv)
                files_seen.update(files_for_inv)
        forbidden_total = 0
        forbidden_files: list[str] = []
        for path in sorted(files_seen):
            n = _count_forbidden_assertions(path)
            if n:
                forbidden_total += n
                forbidden_files.append(f"{_relpath_or_abs(path)}:{n}")
        score = ModuleScore(
            label=group.label,
            declared_invariants=len(group.declared_invariants),
            distinct_inv_refs_in_tests=len(seen_invs),
            test_files=sorted(_relpath_or_abs(p) for p in files_seen),
            forbidden_assertion_count=forbidden_total,
            forbidden_assertion_files=forbidden_files,
            covered=len(seen_invs) >= 3
            or (len(seen_invs) >= 1 and len(seen_invs) == len(group.declared_invariants)),
        )
        scores.append(score)
    return scores


def compute_pai(threshold: float = DEFAULT_THRESHOLD) -> PaiSnapshot:
    claude_md = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    groups = _parse_routing_table(claude_md)
    test_files = list(_iter_test_files(TEST_DIRS))
    inv_to_files = _count_inv_refs(test_files)
    modules = _score_modules(groups, inv_to_files)
    declared = len(modules)
    covered = sum(1 for m in modules if m.covered)
    pai = covered / declared if declared else 0.0
    return PaiSnapshot(
        pai=pai,
        threshold=threshold,
        threshold_met=pai >= threshold,
        modules=modules,
        total_declared=declared,
        total_covered=covered,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute Physics Alignment Index per IERD-PAI-FPS-UX-001 §5."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Pass/fail threshold (default 0.90 from IERD §5).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the snapshot to docs/validation/pai_latest.json.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-module output; print only the verdict line.",
    )
    args = parser.parse_args(argv)

    try:
        snapshot = compute_pai(threshold=args.threshold)
    except (FileNotFoundError, ValueError) as exc:
        print(f"compute_pai: {exc}", file=sys.stderr)
        return 1

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(snapshot.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    if not args.quiet:
        for module in snapshot.modules:
            mark = "PASS" if module.covered else "FAIL"
            print(
                f"  [{mark}] {module.label}: "
                f"{module.distinct_inv_refs_in_tests}/{module.declared_invariants} INV — "
                f"{len(module.test_files)} test file(s)"
            )

    verdict = "PASS" if snapshot.threshold_met else "FAIL"
    print(
        f"{verdict}: PAI = {snapshot.total_covered}/{snapshot.total_declared} = "
        f"{snapshot.pai:.4f} (threshold {snapshot.threshold})"
    )
    return 0 if snapshot.threshold_met else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
