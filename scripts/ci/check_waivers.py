#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed waiver / exception gate.

GeoSync doctrine: a governance gate may be relaxed only by a *time-boxed,
accountable* waiver. A deviation with no owner, no compensating control, or —
worst of all — no expiry is not an exception, it is a silent permanent hole.
This gate makes such holes impossible: every waiver must carry a dated expiry,
and the instant that date passes the gate returns RED on its own, with no
human in the loop. There is no indefinite or expiry-less allowlist entry.

The gate reads every ``governance/waivers/*.yaml`` file and fails closed unless
each waiver resolves:

  1.  all required fields present and non-empty
      (``id``, ``gate``, ``priority``, ``rationale``, ``scope``,
      ``compensating_control``, ``owner``, ``approvers``, ``expiry``,
      ``revalidation_command``);
  2.  ``expiry`` is a real ``YYYY-MM-DD`` date (no expiry / bad date -> RED);
  3.  ``expiry`` is not strictly before ``--now`` (expired -> RED);
  4.  ``priority`` is not ``P0`` — a P0 finding can NEVER be waived (-> RED);
  5.  a ``P1`` waiver carries at least two *distinct* approvers (-> RED).

Determinism: the current date is injected via ``--now YYYY-MM-DD``; the
decision logic never reads the wall clock, so every run is reproducible. If
``--now`` is omitted the process date is used only as a convenience for
interactive CI, and is resolved once before any comparison.

Run::

    python scripts/ci/check_waivers.py --now 2026-07-19

Exit codes::

    0  — every waiver is well-formed, in-date, and permitted
    1  — at least one waiver is expired, malformed, forbidden (P0), or
         under-approved (P1 with < 2 approvers)
    2  — the waivers directory is missing, or a file is not valid YAML
         (fail-closed)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WAIVERS_DIR = ROOT / "governance" / "waivers"

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "gate",
    "priority",
    "rationale",
    "scope",
    "compensating_control",
    "owner",
    "approvers",
    "expiry",
    "revalidation_command",
)

KNOWN_PRIORITIES: frozenset[str] = frozenset({"P0", "P1", "P2"})


@dataclass
class WaiverReport:
    source: str
    waiver_id: str = "<unknown>"
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_now(value: str) -> _dt.date:
    """Parse the injected ``--now`` date; raise on anything but YYYY-MM-DD."""
    return _dt.datetime.strptime(value, "%Y-%m-%d").date()


def _parse_expiry(value: Any) -> _dt.date | None:
    """Return the expiry as a date, or ``None`` when it is missing/malformed.

    Accepts a native ``YYYY-MM-DD`` string or a ``datetime.date`` (PyYAML may
    parse an unquoted date scalar directly). Anything else is rejected so a
    non-date expiry fails closed.
    """
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        try:
            return _dt.datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _distinct_approvers(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        if _is_nonempty_str(item):
            name = item.strip()
            if name not in seen:
                seen.append(name)
    return seen


def _check_waiver(source: str, waiver: dict[str, Any], now: _dt.date) -> WaiverReport:
    rep = WaiverReport(source=source)
    if _is_nonempty_str(waiver.get("id")):
        rep.waiver_id = str(waiver["id"]).strip()

    # 1. required-field presence / non-emptiness
    for key in REQUIRED_FIELDS:
        if key == "approvers":
            if key not in waiver:
                rep.errors.append("missing required field: approvers")
            continue
        if key == "expiry":
            if key not in waiver:
                rep.errors.append("missing required field: expiry")
            continue
        if not _is_nonempty_str(waiver.get(key)):
            rep.errors.append(f"missing or empty required field: {key}")

    # 2. expiry must be a real date (no expiry / bad date -> RED)
    expiry = _parse_expiry(waiver.get("expiry"))
    if "expiry" in waiver and expiry is None:
        rep.errors.append("expiry is not a valid YYYY-MM-DD date")

    # 3. expired -> RED
    if expiry is not None and expiry < now:
        rep.errors.append(
            f"waiver expired: expiry {expiry.isoformat()} is before now {now.isoformat()}"
        )

    # 4. priority sanity + P0 can NEVER be waived
    priority = waiver.get("priority")
    if _is_nonempty_str(priority):
        priority = priority.strip()
        if priority not in KNOWN_PRIORITIES:
            rep.errors.append(f"unknown priority: {priority!r}")
        elif priority == "P0":
            rep.errors.append("P0 findings can NEVER be waived")

    # 5. P1 needs >= 2 distinct approvers; any waiver needs >= 1
    approvers = _distinct_approvers(waiver.get("approvers"))
    if "approvers" in waiver and not approvers:
        rep.errors.append("approvers must be a non-empty list of names")
    elif approvers:
        if priority == "P1" and len(approvers) < 2:
            rep.errors.append(
                f"P1 waiver requires >= 2 distinct approvers, found {len(approvers)}"
            )
    return rep


def _load_reports(now: _dt.date, waivers_dir: Path) -> tuple[list[WaiverReport], int]:
    """Return (reports, fatal_exit). ``fatal_exit`` is 2 on a fail-closed load error."""
    if not waivers_dir.is_dir():
        print(
            f"FAIL: waivers directory is missing: {waivers_dir} (fail-closed)",
            file=sys.stderr,
        )
        return [], 2

    reports: list[WaiverReport] = []
    for path in sorted(waivers_dir.glob("*.yaml")):
        rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            print(f"FAIL: {rel} is not valid YAML: {exc} (fail-closed)", file=sys.stderr)
            return [], 2
        if not isinstance(data, dict) or not isinstance(data.get("waiver"), dict):
            rep = WaiverReport(source=rel)
            rep.errors.append("file must contain a top-level 'waiver:' mapping")
            reports.append(rep)
            continue
        reports.append(_check_waiver(rel, data["waiver"], now))
    return reports, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--now",
        default=None,
        help="Current date as YYYY-MM-DD (injected for determinism). "
        "Defaults to the process date only for interactive use.",
    )
    parser.add_argument(
        "--waivers-dir",
        default=str(WAIVERS_DIR),
        help="Directory of *.yaml waiver files (default: governance/waivers).",
    )
    args = parser.parse_args(argv)

    if args.now is None:
        now = _dt.date.today()
    else:
        try:
            now = _parse_now(args.now)
        except ValueError:
            print(f"FAIL: --now must be YYYY-MM-DD, got {args.now!r}", file=sys.stderr)
            return 2

    reports, fatal = _load_reports(now, Path(args.waivers_dir))
    if fatal:
        return fatal

    failed = [r for r in reports if not r.ok]
    for rep in reports:
        print(f"[{'PASS' if rep.ok else 'FAIL'}] {rep.waiver_id} ({rep.source})")
        for err in rep.errors:
            print(f"       - {err}")

    n = len(reports)
    if failed:
        print(
            f"\nFAIL: {len(failed)}/{n} waivers are expired, forbidden, or malformed "
            f"(as of {now.isoformat()})",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: all {n} waivers are well-formed, in-date, and permitted "
          f"(as of {now.isoformat()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
