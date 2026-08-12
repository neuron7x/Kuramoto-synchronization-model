#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Docs-consistency gate — fail-closed enforcement of the canonical-root decision.

[ADR 0024](../../docs/adr/0024-import-architecture-canonicalization.md) (Accepted
2026-06-09) makes top-level ``geosync/`` the single canonical install root and
retires the ``src/geosync/`` fork. Several docs historically asserted the
opposite (``Root: src/geosync``, "src/geosync ... canonical"). This gate fails
the build if any documentation file *reasserts* ``src/geosync`` as the canonical
root, so the docs cannot drift back out of sync with the ADR.

What counts as a violation:

* a Markdown line that mentions ``src/geosync`` **and** a canonical-assertion
  token ("canonical", "source of truth", "root:") on the same line,
* **unless** the same line also carries an explicit retirement/transition word
  (retired, legacy, fork, migrat..., transition, ...) — i.e. it is honestly
  describing the in-flight legacy state, not asserting current canonicality,
* **or** the line is an explicitly reviewed exception in
  ``.github/docs_consistency_allow.json``.

Stdlib-only; fast. Mirrors the claim-boundary / import-architecture gates.

Usage::

    python scripts/ci/check_docs_consistency.py            # verify (CI)
    python scripts/ci/check_docs_consistency.py --json out.json

Exit codes::

    0  — no doc reasserts src/geosync as canonical
    1  — at least one violation (printed with file:line)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOW_PATH = ROOT / ".github" / "docs_consistency_allow.json"

# The retired fork path, as written in docs.
_SRC_PKG_RE = re.compile(r"src/geosync\b")

# Present-tense canonical-assertion tokens. ``root:`` is matched even when wrapped
# in Markdown emphasis (e.g. ``**Root:**``), via the word boundary before "root".
_CANONICAL_RE = re.compile(
    r"\bcanonical\b|\bsource of truth\b|\broot:",
    re.IGNORECASE,
)

# Words that mark an honest description of the *retired/legacy* state, which is
# allowed (and required) when documenting the migration.
_EXEMPT_RE = re.compile(
    r"\bretir(?:e|ed|es|ing)\b|\blegacy\b|\bformer(?:ly)?\b|\bdeprecat\w*\b"
    r"|\babandon\w*\b|\bfork\b|\bmigrat\w*\b|\btransition\w*\b|\bpredate\w*\b"
    r"|\bsupersed\w*\b|\bstale\b|\bno longer\b|\bnot trusted\b|\bbeing\b|\btracked\b",
    re.IGNORECASE,
)


def _doc_files() -> list[Path]:
    files: list[Path] = []
    readme = ROOT / "README.md"
    if readme.exists():
        files.append(readme)
    docs_dir = ROOT / "docs"
    if docs_dir.exists():
        files.extend(sorted(docs_dir.rglob("*.md")))
    return files


def _load_allow() -> list[tuple[str, str]]:
    """Return reviewed exceptions as (relative_file, lowercased_match)."""
    if not ALLOW_PATH.exists():
        return []
    payload = json.loads(ALLOW_PATH.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for entry in payload.get("allow", []):
        out.append((str(entry["file"]), str(entry["match"]).lower()))
    return out


def _is_allowed(rel: str, line: str, allow: list[tuple[str, str]]) -> bool:
    low = line.lower()
    return any(a_file == rel and a_match in low for a_file, a_match in allow)


def scan() -> list[tuple[str, int, str]]:
    """Return [(relative_path, line_no, line_text)] for every violation."""
    allow = _load_allow()
    violations: list[tuple[str, int, str]] = []
    for path in _doc_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if not _SRC_PKG_RE.search(line):
                continue
            if not _CANONICAL_RE.search(line):
                continue
            if _EXEMPT_RE.search(line):
                continue
            if _is_allowed(rel, line, allow):
                continue
            violations.append((rel, i, line.strip()))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Docs-consistency gate (ADR 0024).")
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Write the violation report as JSON to this path.",
    )
    args = parser.parse_args(argv)

    violations = scan()

    if args.json is not None:
        report = {
            "version": 1,
            "ok": not violations,
            "violations": [{"file": f, "line": ln, "text": txt} for f, ln, txt in violations],
        }
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if violations:
        print(
            "ERROR: docs reassert `src/geosync` as canonical — contradicts ADR 0024 "
            "(canonical root is top-level `geosync/`)."
        )
        for f, ln, txt in violations:
            print(f"  {f}:{ln}: {txt}")
        print(
            "Fix: describe `geosync/` as canonical and `src/geosync/` as the retired "
            "fork, or add a reviewed exception to .github/docs_consistency_allow.json."
        )
        return 1

    print("Docs-consistency gate held: no doc reasserts `src/geosync` as canonical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
