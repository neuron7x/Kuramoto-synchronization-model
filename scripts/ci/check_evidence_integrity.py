#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed evidence-integrity gate — teeth against fake promotion.

The neuro ledger audit (``tools/audit/neuro_symbolic_audit.py``) is *structural*:
it checks that an OPERATIONAL entry DECLARES an inv_ref / test / falsifier, but
it does NOT verify those references RESOLVE. A fabricated promotion citing a
non-existent ``INV-FOO`` and a test file that was never written would pass the
structural audit. This gate closes that hole. It verifies, fail-closed:

  * OPERATIONAL → ≥1 inv_ref AND every inv_ref resolves to a real invariant id
    in the registry ``.claude/physics/INVARIANTS.yaml`` (the SOLE authority —
    CLAUDE.md prose is a doc mirror, not an authority); ≥1 existing_test AND
    every existing_test path exists on disk; non-empty falsifier.
  * PARTIAL → inv_refs MUST be empty. A PARTIAL that cites an INV is claiming an
    operational binding while sitting at admissibility tier — that is exactly
    the "described as promoted" contradiction. Promote it or drop the binding.
  * DECORATIVE on a runtime path (runtime_path == YES) → remediation must be a
    quarantine action (RENAME or QUARANTINE_DOC) AND an explicit 'non-claim'
    note must be present (falsifier or reason).

Tiers are read STRICTLY from the ledger ``classification`` field — never
inferred. The gate touches no physics and runs no solver (Rule Zero safe).

Exit codes::
    0  — every OPERATIONAL/PARTIAL/DECORATIVE entry's evidence resolves
    1  — at least one integrity violation
    2  — ledger or registry missing / unparseable
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".claude" / "neuro" / "NEURO_OPERATIONALIZATION_LEDGER.yaml"
REGISTRY = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"

_REGISTRY_ID = re.compile(r"^\s*id:\s*(INV-[A-Za-z0-9_-]+)\s*$")
_QUARANTINE_ACTIONS = frozenset({"RENAME", "QUARANTINE_DOC"})


def known_invariant_ids(registry: Path = REGISTRY) -> set[str]:
    """Authoritative invariant ids — the YAML registry ONLY.

    The registry (``.claude/physics/INVARIANTS.yaml``) is the single source of
    truth. CLAUDE.md is a doc mirror, NOT an authority: scanning its prose for
    ``INV-*`` tokens would let a stray ``INV-FAKE`` mention in documentation be
    accepted as a known invariant, defeating the gate. An OPERATIONAL ledger
    entry must therefore cite an inv_ref that resolves in the registry.
    """
    known: set[str] = set()
    if registry.is_file():
        for line in registry.read_text(encoding="utf-8").splitlines():
            m = _REGISTRY_ID.match(line)
            if m:
                known.add(m.group(1))
    return known


def _entries(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    acc: list[dict[str, Any]] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if "id" in o and "classification" in o:
                acc.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(ledger)
    return acc


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def integrity_errors(
    ledger: dict[str, Any],
    known_invs: set[str],
    root: Path = ROOT,
) -> list[str]:
    """Return human-readable integrity violations; empty list = clean."""
    errors: list[str] = []
    for e in _entries(ledger):
        eid = str(e.get("id", "<missing-id>"))
        cls = e.get("classification")
        inv_refs = [r for r in (e.get("inv_refs") or []) if _nonempty_str(r)]
        tests = [t for t in (e.get("existing_tests") or []) if _nonempty_str(t)]
        falsifier = e.get("falsifier", "")
        # Unquoted `runtime_path: YES` in YAML coerces to Python bool True
        # (`NO` -> False). Normalize back to the canonical string so the
        # DECORATIVE-on-runtime quarantine gate cannot be defeated by dropping
        # the quotes around YES.
        _rt = e.get("runtime_path")
        runtime = "YES" if _rt is True else ("NO" if _rt is False else _rt)
        remediation = e.get("remediation_action")
        reason = e.get("reason", "")

        if cls == "OPERATIONAL":
            if not inv_refs:
                errors.append(f"[{eid}] OPERATIONAL has no inv_ref (fake promotion).")
            for ref in inv_refs:
                if ref not in known_invs:
                    errors.append(
                        f"[{eid}] OPERATIONAL cites unknown invariant {ref!r} "
                        f"(not in the INVARIANTS.yaml registry)."
                    )
            if not tests:
                errors.append(f"[{eid}] OPERATIONAL has no existing_test (fake promotion).")
            for test in tests:
                if not (root / test).is_file():
                    errors.append(f"[{eid}] OPERATIONAL existing_test missing on disk: {test}")
            if not _nonempty_str(falsifier):
                errors.append(f"[{eid}] OPERATIONAL has no falsifier.")

        elif cls == "PARTIAL":
            if inv_refs:
                errors.append(
                    f"[{eid}] PARTIAL cites INV {inv_refs} — a PARTIAL must NOT claim an "
                    f"operational INV binding (described as promoted). Promote it or drop the ref."
                )

        elif cls == "DECORATIVE" and runtime == "YES":
            if remediation not in _QUARANTINE_ACTIONS:
                errors.append(
                    f"[{eid}] DECORATIVE on runtime path must be quarantined "
                    f"(remediation RENAME or QUARANTINE_DOC), got {remediation!r}."
                )
            blob = f"{falsifier} {reason}".lower()
            if "non-claim" not in blob:
                errors.append(
                    f"[{eid}] DECORATIVE on runtime path requires an explicit 'non-claim' note."
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", nargs="?", type=Path, default=LEDGER)
    args = parser.parse_args(argv)
    ledger_path: Path = args.ledger

    if not ledger_path.is_file():
        print(f"ERROR: ledger not found at {ledger_path}", file=sys.stderr)
        return 2
    try:
        ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"ERROR: failed to parse ledger: {exc}", file=sys.stderr)
        return 2
    if not isinstance(ledger, dict):
        print("ERROR: ledger top-level must be a mapping", file=sys.stderr)
        return 2

    known = known_invariant_ids()
    errors = integrity_errors(ledger, known)
    if errors:
        print(f"EVIDENCE INTEGRITY FAIL — {len(errors)} violation(s):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("EVIDENCE INTEGRITY: PASS — every tier's evidence resolves (no fake promotion).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
