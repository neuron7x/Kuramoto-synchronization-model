#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Post-vacuous-oracle revalidation ledger gate (DEBT_5).

GeoSync doctrine: the ``python-fast-shard`` PR gate ran ZERO tests for the
entire history of the repository (a double ``-q`` collect bug). PR #1153
restores a real fast oracle but is still OPEN. Every critical lane that merged
before #1153 terminalizes therefore merged under a VACUOUS green and carries a
WEAKENED evidence-class — the gate that was meant to prove it was inert.

A weakened-evidence lane is honest open debt: it must be REPLAYED under a real
oracle (with the proof recorded) or BOUNDED with an explicit residual, but it
must NEVER be silently relabelled "revalidated" with no proof a real oracle
existed. ``PENDING`` is the honest default and is always admissible.

This gate reads ``governance/REVALIDATION_LEDGER.yaml`` and fails closed
unless every entry is well-formed AND the INTERLOCK holds:

  * ``replay_status == REPLAYED`` is admissible ONLY when the entry also
    carries ``oracle_terminal_sha`` (a 40-hex commit at which a real oracle
    was proven live) AND ``replay_evidence`` (an in-repo path that EXISTS).
    Missing either => violation: a lane cannot be declared revalidated
    without a real-oracle sha and a preserved evidence artifact.
  * ``replay_status == BOUNDED`` requires a non-empty ``bound`` field that
    describes the residual.
  * ``replay_status == PENDING`` requires nothing extra (open debt is
    allowed) but a seeded entry must keep ``merged_under_vacuous_oracle``
    true — the reason the lane is in the ledger at all.
  * ``note`` must carry NO promotion language ("partial success",
    "validated", "unblocked", "passed", ...) — a weakened lane is not a win.

Run::

    python scripts/ci/check_revalidation_ledger.py

Exit codes::

    0  — every ledger entry is well-formed and the revalidation interlock holds
    1  — a malformed entry, a duplicate id/pr, a bad sha/lane_class/status, a
         REPLAYED claim without a real-oracle sha + existing evidence, a
         BOUNDED entry with no residual, or promotion language in a note
    2  — the ledger itself is missing or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "governance" / "REVALIDATION_LEDGER.yaml"

VALID_LANE_CLASSES = {"physics", "governance", "security", "infra", "kuramoto"}
VALID_REPLAY_STATUSES = {"PENDING", "REPLAYED", "BOUNDED"}
# Language that launders a weakened-evidence lane into a "win" — forbidden in
# any note. Mirrors the negative-evidence gate's promotion ban list.
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


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _check_entry(entry: dict[str, Any]) -> EntryReport:
    eid = str(entry.get("id", "<unnamed>"))
    rep = EntryReport(entry_id=eid)

    if not isinstance(entry.get("id"), str) or not str(entry.get("id")).strip():
        rep.errors.append("missing/empty 'id'")

    pr = entry.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or pr <= 0:
        rep.errors.append("'pr' must be a positive int")

    sha = entry.get("merge_sha")
    if not isinstance(sha, str) or not _SHA40.match(sha):
        rep.errors.append("missing/malformed 'merge_sha' (need 40 hex)")

    lane_class = entry.get("lane_class")
    if lane_class not in VALID_LANE_CLASSES:
        rep.errors.append(f"lane_class {lane_class!r} not one of {sorted(VALID_LANE_CLASSES)}")

    vac = entry.get("merged_under_vacuous_oracle")
    if not isinstance(vac, bool):
        rep.errors.append("'merged_under_vacuous_oracle' must be a bool")
    elif not vac:
        # A seeded entry exists precisely because it merged under the vacuous
        # oracle; flipping this to false would smuggle a lane out of the debt.
        rep.errors.append(
            "'merged_under_vacuous_oracle' must be true for a seeded revalidation entry"
        )

    status = entry.get("replay_status")
    if status not in VALID_REPLAY_STATUSES:
        rep.errors.append(f"replay_status {status!r} not one of {sorted(VALID_REPLAY_STATUSES)}")

    if not _is_iso_date(entry.get("recorded_utc")):
        rep.errors.append("missing/malformed 'recorded_utc' (need ISO date YYYY-MM-DD)")

    note = entry.get("note")
    if not isinstance(note, str) or not note.strip():
        rep.errors.append("missing/empty 'note'")
    else:
        low = note.lower()
        for term in FORBIDDEN_PROMOTION:
            if term in low:
                rep.errors.append(
                    f"promotion language {term!r} in note "
                    "(a weakened-evidence lane is not a success)"
                )

    # INTERLOCK — the anti-theater core.
    if status == "REPLAYED":
        oracle_sha = entry.get("oracle_terminal_sha")
        if not isinstance(oracle_sha, str) or not _SHA40.match(oracle_sha):
            rep.errors.append(
                "REPLAYED requires 'oracle_terminal_sha' (40-hex): cannot claim a lane "
                "revalidated without a real-oracle sha"
            )
        evidence = entry.get("replay_evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            rep.errors.append(
                "REPLAYED requires 'replay_evidence' (in-repo path): cannot claim a lane "
                "revalidated without a preserved evidence artifact"
            )
        elif not (ROOT / evidence).exists():
            rep.errors.append(f"replay_evidence path does not exist: {evidence}")
    elif status == "BOUNDED":
        bound = entry.get("bound")
        if not isinstance(bound, str) or not bound.strip():
            rep.errors.append("BOUNDED requires a non-empty 'bound' describing the residual")

    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args(argv)

    if not args.registry.is_file():
        print(f"FAIL: revalidation ledger not found: {args.registry}", file=sys.stderr)
        return 2
    try:
        registry = yaml.safe_load(args.registry.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL: ledger is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(registry, dict):
        print("FAIL: ledger root must be a mapping", file=sys.stderr)
        return 2

    if registry.get("schema_version") != 1:
        print("FAIL: ledger schema_version must be 1", file=sys.stderr)
        return 2
    oracle_fix_pr = registry.get("oracle_fix_pr")
    if not isinstance(oracle_fix_pr, int) or isinstance(oracle_fix_pr, bool):
        print("FAIL: ledger 'oracle_fix_pr' must be an int", file=sys.stderr)
        return 2
    coverage_bound = registry.get("coverage_bound")
    if not isinstance(coverage_bound, str) or not coverage_bound.strip():
        print("FAIL: ledger 'coverage_bound' must be a non-empty string", file=sys.stderr)
        return 2

    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        print("FAIL: ledger 'entries' must be a non-empty list", file=sys.stderr)
        return 2

    reports = [_check_entry(e) for e in entries if isinstance(e, dict)]

    # Uniqueness of id and pr across the ledger.
    seen_ids: dict[str, int] = {}
    seen_prs: dict[int, int] = {}
    for idx, entry in enumerate(e for e in entries if isinstance(e, dict)):
        rep = reports[idx]
        eid = entry.get("id")
        if isinstance(eid, str):
            if eid in seen_ids:
                rep.errors.append(f"duplicate id {eid!r}")
            else:
                seen_ids[eid] = idx
        pr = entry.get("pr")
        if isinstance(pr, int) and not isinstance(pr, bool):
            if pr in seen_prs:
                rep.errors.append(f"duplicate pr {pr}")
            else:
                seen_prs[pr] = idx

    failed = [r for r in reports if not r.ok]
    for rep in reports:
        print(f"[{'PASS' if rep.ok else 'FAIL'}] {rep.entry_id}")
        for err in rep.errors:
            print(f"       - {err}")

    pending = sum(1 for e in entries if isinstance(e, dict) and e.get("replay_status") == "PENDING")
    print(f"\nNOTE: {pending} lane(s) still PENDING replay under oracle PR #{oracle_fix_pr}")

    n = len(reports)
    if failed:
        print(
            f"\nFAIL: {len(failed)}/{n} revalidation entries malformed or laundered",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: all {n} revalidation entries well-formed; replay interlock holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
