#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-evidence registry gate.

GeoSync doctrine: a negative result is information, not a failure to bury. The
four operational categories of negative evidence — a failed null comparison,
an invalid input, a calibration miss, a replay mismatch — must each be
preserved (artifact in the tree, sha-anchored), never rewritten, and NEVER
laundered into a "partial success".

This gate reads ``governance/NEGATIVE_EVIDENCE.yaml`` and fails closed unless
every entry:

  1.  declares one of the four allowed categories;
  2.  carries a negative-class verdict (never a positive/promotion verdict);
  3.  has a non-empty description with NO promotion language
      ("partial success", "validated", "unblocked", "passed", ...);
  4.  sha-anchors a 40-hex commit; and
  5.  references an in-repo artifact path that still EXISTS (preservation).

Run::

    python scripts/ci/check_negative_evidence.py

Exit codes::

    0  — every negative-evidence entry is preserved and honestly negative
    1  — a lost artifact, a missing sha, a non-negative verdict, a forbidden
         category, or promotion language laundering a negative into a "win"
    2  — the registry itself is missing or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "governance" / "NEGATIVE_EVIDENCE.yaml"

VALID_CATEGORIES = {
    "failed_null_comparison",
    "invalid_input",
    "calibration_miss",
    "replay_mismatch",
}
# A negative result keeps a negative-class verdict. Anything else is a
# promotion of a null into a claim.
NEGATIVE_VERDICTS = {
    "REJECTED",
    "INVALID",
    "MISS",
    "MISMATCH",
    "FALSIFIED",
    "NULL",
    "INFEASIBLE",
    "RETRACTED",
}
# Language that launders a negative into a "win" — forbidden in any entry.
FORBIDDEN_PROMOTION = (
    "partial success",
    "partially validated",
    "validated",
    "unblocked",
    "passed",
    "promising",
    "breakthrough",
    "confirmed positive",
    "success",
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class EntryReport:
    entry_id: str
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_entry(entry: dict[str, Any]) -> EntryReport:
    eid = str(entry.get("id", "<unnamed>"))
    rep = EntryReport(entry_id=eid)

    category = entry.get("category")
    if category not in VALID_CATEGORIES:
        rep.errors.append(f"category {category!r} not one of {sorted(VALID_CATEGORIES)}")

    verdict = str(entry.get("verdict", ""))
    if verdict not in NEGATIVE_VERDICTS:
        rep.errors.append(
            f"verdict {verdict!r} is not a negative-class verdict {sorted(NEGATIVE_VERDICTS)}"
        )

    description = entry.get("description")
    if not isinstance(description, str) or not description.strip():
        rep.errors.append("missing/empty description")
    else:
        low = description.lower()
        for term in FORBIDDEN_PROMOTION:
            if term in low:
                rep.errors.append(
                    f"promotion language {term!r} in description (a negative is not a success)"
                )

    sha = str(entry.get("sha", ""))
    if not _SHA40.match(sha):
        rep.errors.append("missing/malformed 'sha' (need 40 hex)")

    artifact = entry.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        rep.errors.append("missing 'artifact' path")
    elif not (ROOT / artifact).exists():
        rep.errors.append(f"artifact does not exist (negative record lost): {artifact}")

    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args(argv)

    if not args.registry.is_file():
        print(f"FAIL: negative-evidence registry not found: {args.registry}", file=sys.stderr)
        return 2
    try:
        registry = yaml.safe_load(args.registry.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL: registry is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(registry, dict):
        print("FAIL: registry root must be a mapping", file=sys.stderr)
        return 2
    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        print("FAIL: registry 'entries' must be a non-empty list", file=sys.stderr)
        return 2

    reports = [_check_entry(e) for e in entries if isinstance(e, dict)]
    failed = [r for r in reports if not r.ok]
    for rep in reports:
        print(f"[{'PASS' if rep.ok else 'FAIL'}] {rep.entry_id}")
        for err in rep.errors:
            print(f"       - {err}")

    covered = {e.get("category") for e in entries if isinstance(e, dict)}
    missing = sorted(VALID_CATEGORIES - covered)
    if missing:
        # Not a failure — the registry grows — but never silently: log the gap.
        print(f"\nNOTE: categories with no recorded negative yet: {missing}")

    n = len(reports)
    if failed:
        print(
            f"\nFAIL: {len(failed)}/{n} negative-evidence entries lost, rewritten, or laundered",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: all {n} negative-evidence entries preserved and honestly negative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
