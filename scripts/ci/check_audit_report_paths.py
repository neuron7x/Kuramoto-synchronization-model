#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed falsifier for the 2026-06 physics-depth external audit report.

An audit DESCRIBES the repository surface; it must therefore cite only paths
that actually exist in the tree. A fabricated path (a defect mapped to a file
that is not there) is exactly the kind of invented finding the audit-discipline
forbids. This probe parses the audit report, extracts every backtick-quoted
token that looks like a repository-relative path (contains a ``/`` and ends in a
known source/contract/governance suffix, OR names a top-level governance
markdown file), and verifies each cited path EXISTS on disk.

Polarity (matches the commit-acceptor evidence runner convention used across the
corpus: ``exit 0`` == the green-state precondition is BROKEN, i.e. the falsifier
FIRED):

    exit 0  -> at least one cited path is MISSING (the audit cites a path that
               does not exist) OR the report file itself is missing. The audit
               has a fabricated/rotted citation and must be repaired, not
               patched green.
    exit 1  -> every cited path resolves (the report cites only existing paths).
    exit 2  -> usage / IO error.

Usage:
    python scripts/ci/check_audit_report_paths.py [REPORT_PATH]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = "docs/audit/2026-06-physics-depth-external-audit.md"

# Suffixes that mark a backtick token as a concrete repository artifact path.
_PATH_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".toml",
    ".cff",
    ".bib",
    ".sh",
)

# Top-level governance markdown files cited by bare name (no directory).
_BARE_GOVERNANCE_FILES: frozenset[str] = frozenset(
    {
        "VERDICT.md",
        "FORBIDDEN_CLAIMS.md",
        "PRODUCT_CATEGORY.md",
        "CLAIMS.md",
        "README.md",
        "BASELINE.md",
        "CLAUDE.md",
        "BLOCKED.md",
    }
)

# Backtick-quoted token. We only treat a token as a path candidate when it has
# no whitespace and either contains a "/" or is a known bare governance file.
_BACKTICK = re.compile(r"`([^`\n]+)`")


def _is_path_candidate(token: str) -> bool:
    token = token.strip()
    if not token or " " in token:
        return False
    if token in _BARE_GOVERNANCE_FILES:
        return True
    if "/" not in token:
        return False
    # Strip a trailing "::symbol" (pytest-style) or "::ClassName" reference.
    base = token.split("::", 1)[0]
    return base.endswith(_PATH_SUFFIXES)


def extract_cited_paths(report_text: str) -> list[str]:
    """Return the sorted, de-duplicated list of repo-path citations in *text*."""
    seen: set[str] = set()
    for raw in _BACKTICK.findall(report_text):
        token = raw.strip()
        if _is_path_candidate(token):
            seen.add(token.split("::", 1)[0])
    return sorted(seen)


def missing_paths(report_path: Path) -> list[str]:
    """Return the cited paths that do NOT exist relative to the repo root."""
    text = report_path.read_text(encoding="utf-8")
    missing: list[str] = []
    for cited in extract_cited_paths(text):
        if not (ROOT / cited).exists():
            missing.append(cited)
    return missing


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    rel = args[0] if args else DEFAULT_REPORT
    report_path = ROOT / rel
    if not report_path.is_file():
        # No report -> the green-state precondition (a report citing real paths)
        # cannot hold. Fire.
        print(f"FIRED: audit report not found at {rel}", file=sys.stderr)
        return 0
    missing = missing_paths(report_path)
    if missing:
        print(
            "FIRED: audit report cites path(s) that do not exist: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 0
    cited = extract_cited_paths(report_path.read_text(encoding="utf-8"))
    print(f"OK: all {len(cited)} cited repository paths in {rel} exist")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
