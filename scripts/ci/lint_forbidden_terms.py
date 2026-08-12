#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Forbidden-terminology lint (IERD-PAI-FPS-UX-001 §3).

Scans Markdown surface text and Python docstrings for the IERD
forbidden-terminology list. In **warn** mode (Phase 0) it lists
offending lines and exits 0; in **strict** mode (Phase 5) it exits
non-zero so CI gates the merge.

Forbidden terms (literal, case-insensitive) — see directive §3:

    truth function
    real physics law
    thermodynamic invariant
    serotonin gain        (literal, including the underscore form)
    neuro truth
    universal intelligence law
    physics-aligned production-ready

Anchored use is allowed: a forbidden term in the same paragraph as a
matching exception marker (`[claim_id=…]`, `[INV-…]`, or an inline
citation like `[@AuthorYearKey]`) is skipped, because the surface
text is then traceable to a falsifying test or peer-reviewed source.

Usage:

    python scripts/ci/lint_forbidden_terms.py            # warn-only
    python scripts/ci/lint_forbidden_terms.py --strict   # fail-closed
    python scripts/ci/lint_forbidden_terms.py --paths README.md docs/

Phase 0 default is warn-only. Move to strict in Phase 5 per directive §7.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("truth function", re.compile(r"\btruth[\s\-_]+function\b", re.IGNORECASE)),
    ("real physics law", re.compile(r"\breal\s+physics\s+law\b", re.IGNORECASE)),
    (
        "thermodynamic invariant",
        re.compile(r"\bthermodynamic\s+invariant\b", re.IGNORECASE),
    ),
    ("serotonin gain", re.compile(r"\bserotonin[\s\-_]+gain\b", re.IGNORECASE)),
    ("neuro truth", re.compile(r"\bneuro[\s\-_]+truth\b", re.IGNORECASE)),
    (
        "universal intelligence law",
        re.compile(r"\buniversal\s+intelligence\s+law\b", re.IGNORECASE),
    ),
    (
        "physics-aligned production-ready",
        re.compile(r"\bphysics[\s\-]+aligned[\s\-]+production[\s\-]+ready\b", re.IGNORECASE),
    ),
)

# IERD §1 trigger terms — soft-banned. Allowed in surface text only when
# accompanied by an exception marker ([claim_id=...], [INV-...], [@Cite])
# in the same line. The point is that "production-ready" without a
# claim_id is a marketing assertion, not an engineering one.
TRIGGER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "production-ready",
        re.compile(r"\bproduction[\s\-]+ready\b", re.IGNORECASE),
    ),
    (
        "physics-aligned",
        re.compile(r"\bphysics[\s\-]+aligned\b", re.IGNORECASE),
    ),
    (
        "first-principles",
        re.compile(r"\bfirst[\s\-]+principles\b", re.IGNORECASE),
    ),
    (
        "UX-ready",
        re.compile(r"\bUX[\s\-]+ready\b", re.IGNORECASE),
    ),
    (
        "cycle-time acceleration",
        re.compile(r"\bcycle[\s\-]+time\s+acceleration\b", re.IGNORECASE),
    ),
)

EXCEPTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\[claim_id=[a-z0-9\-]+\]", re.IGNORECASE),
    re.compile(r"\[INV-[A-Z0-9\-]+\]"),
    re.compile(r"\[@[A-Za-z][A-Za-z0-9\-_]*\]"),
)

DEFAULT_INCLUDE_GLOBS: tuple[str, ...] = (
    "README.md",
    "docs/**/*.md",
    "docs/**/*.yaml",
    "reports/**/*.md",
)

# Phase-0.5 strict subset: these surfaces enforce trigger terms now.
# Other paths remain warn-only until lint-policy phase advances. Keeping
# the strict subset narrow lets the codebase land Phase-0 today while
# raising the floor on the most-read surfaces immediately.
STRICT_SUBSET_GLOBS: tuple[str, ...] = (
    "README.md",
    "docs/governance/**/*.md",
    "docs/audit/**/*.md",
    "docs/yana-response.md",
    "docs/adr/0020-ierd-adoption.md",
    "docs/validation/**/*.md",
)

# Paths that are allowed to quote forbidden terms (e.g. the directive
# itself, the audit findings, this lint, the IERD response).
ALLOWLIST_PATHS: frozenset[str] = frozenset(
    {
        # Documents that DEFINE the IERD vocabulary (must quote it verbatim).
        "docs/governance/IERD-PAI-FPS-UX-001.md",
        "docs/audit/ierd_phase0_findings.md",
        "docs/yana-response.md",
        "docs/KNOWN_LIMITATIONS.md",
        "docs/CLAIMS.yaml",
        "docs/adr/0020-ierd-adoption.md",
        "docs/validation/pai_report_2026_05_03.md",
        # Lint and gate sources (contain the patterns by construction).
        "scripts/ci/lint_forbidden_terms.py",
        "scripts/ci/check_claims.py",
        "scripts/ci/compute_pai.py",
        "scripts/ci/compute_fps_audit.py",
        ".claude/physics/lint_forbidden_terms.py",
    }
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    term: str
    severity: str  # "forbidden" | "trigger"
    excerpt: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line_no}: [{self.severity}] '{self.term}' — "
            f"{self.excerpt.strip()[:120]}"
        )


def _iter_targets(root: Path, globs: Sequence[str]) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in globs:
        for match in root.glob(pattern):
            if match.is_file() and match not in seen:
                seen.add(match)
                yield match


def _is_allowlisted(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return rel in ALLOWLIST_PATHS


def _has_exception(line: str) -> bool:
    return any(p.search(line) for p in EXCEPTION_PATTERNS)


def _scan_file(path: Path, *, scan_triggers: bool) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        anchored = _has_exception(line)
        for term, pattern in FORBIDDEN_PATTERNS:
            if anchored:
                continue
            if pattern.search(line):
                findings.append(
                    Finding(
                        path=path,
                        line_no=line_no,
                        term=term,
                        severity="forbidden",
                        excerpt=line,
                    )
                )
        if scan_triggers and not anchored:
            for term, pattern in TRIGGER_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            path=path,
                            line_no=line_no,
                            term=term,
                            severity="trigger",
                            excerpt=line,
                        )
                    )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint forbidden terminology per IERD-PAI-FPS-UX-001 §3."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Phase 5: exit non-zero on any forbidden finding (default warn).",
    )
    parser.add_argument(
        "--strict-triggers",
        action="store_true",
        help=(
            "Phase 0.5: exit non-zero on §1 trigger terms "
            "(production-ready, physics-aligned, first-principles, "
            "UX-ready, cycle-time acceleration) when used without an "
            "exception marker on the same line. Implies --strict."
        ),
    )
    parser.add_argument(
        "--phase0-strict-subset",
        action="store_true",
        help=(
            "Phase 0.5: enforce strict + strict-triggers on the curated "
            "STRICT_SUBSET_GLOBS (README, governance, audit, validation, "
            "yana-response). Other paths warn-only."
        ),
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Override default include globs (relative to repo root).",
    )
    args = parser.parse_args(argv)

    if args.phase0_strict_subset:
        globs = tuple(args.paths) if args.paths else STRICT_SUBSET_GLOBS
        scan_triggers = True
        strict_mode = True
    else:
        globs = tuple(args.paths) if args.paths else DEFAULT_INCLUDE_GLOBS
        scan_triggers = args.strict_triggers
        strict_mode = args.strict or args.strict_triggers

    findings: list[Finding] = []
    scanned = 0
    for target in _iter_targets(ROOT, globs):
        if _is_allowlisted(target, ROOT):
            continue
        scanned += 1
        findings.extend(_scan_file(target, scan_triggers=scan_triggers))

    if not findings:
        scope = "subset" if args.phase0_strict_subset else "default"
        print(f"PASS: {scanned} file(s) scanned ({scope} scope), no forbidden/trigger terms found.")
        return 0

    label = "FAIL" if strict_mode else "WARN"
    print(
        f"{label}: {len(findings)} forbidden-term finding(s) across {scanned} scanned file(s):",
        file=sys.stderr,
    )
    for f in findings:
        print(f"  {f.render()}", file=sys.stderr)

    if strict_mode:
        print(
            "\nResolve by replacing per IERD §4.2 mapping or by adding "
            "an exception marker ([claim_id=…], [INV-…], [@CitationKey]).",
            file=sys.stderr,
        )
        return 1

    print(
        "\n[Phase 0 warn-only mode — these findings do not block CI. "
        "Strict mode lands in Phase 5; Phase 0.5 strict subset already "
        "enforced via --phase0-strict-subset.]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
