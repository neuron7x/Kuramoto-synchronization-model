#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GOV-002 RACI closure gate — fail-closed.

Asserts the remediation RACI contract is well-formed:

  (a) every one of the 11 workstreams appears in the RACI matrix,
  (b) the two-signature / conflict-of-interest (COI) rule is present,
  (c) the YAML parses.

Additionally checks the structural COI guarantee: for every workstream the
declared independent ``approver`` differs from the ``accountable`` owner, so
the accountable owner cannot be the sole closer of a P0 they authored.

Usage::

    python scripts/ci/check_raci.py [path/to/REMEDIATION_RACI.yaml]

Exit codes::

    0  — contract well-formed
    1  — a workstream is missing, the COI/two-signature rule is absent,
         an approver collides with its accountable owner, or YAML is invalid
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RACI = ROOT / "governance" / "REMEDIATION_RACI.yaml"

# The 11 canonical remediation workstreams that MUST every appear in the RACI.
REQUIRED_WORKSTREAMS = (
    "GOV",
    "REL",
    "ENV",
    "TST",
    "ARC",
    "PKG",
    "SEC",
    "DOC",
    "RES",
    "DAT",
    "OPS",
)


def check(path: Path) -> list[str]:
    """Return a list of contract violations (empty list == pass)."""
    errors: list[str] = []

    # (c) YAML parses.
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except FileNotFoundError:
        return [f"RACI file not found: {path}"]
    except yaml.YAMLError as exc:
        return [f"RACI YAML failed to parse: {exc}"]

    if not isinstance(data, dict):
        return [f"RACI root must be a mapping, got {type(data).__name__}"]

    raci = data.get("raci")
    if not isinstance(raci, dict):
        errors.append("missing or malformed 'raci' matrix (expected a mapping)")
        raci = {}

    # (a) every workstream appears in the RACI matrix.
    for ws in REQUIRED_WORKSTREAMS:
        if ws not in raci:
            errors.append(f"workstream missing from RACI matrix: {ws}")
            continue
        entry = raci[ws]
        if not isinstance(entry, dict):
            errors.append(f"RACI entry for {ws} must be a mapping")
            continue
        accountable = entry.get("accountable")
        approver = entry.get("approver")
        if not accountable:
            errors.append(f"{ws}: no single 'accountable' owner declared")
        if isinstance(accountable, list):
            errors.append(f"{ws}: 'accountable' must be a single role, not a list")
        if not approver:
            errors.append(f"{ws}: no independent 'approver' declared")
        # Structural COI: approver must not be the accountable owner.
        if accountable and approver and accountable == approver:
            errors.append(
                f"{ws}: independent approver equals accountable owner "
                f"({accountable}) — self-approval is forbidden"
            )

    # (b) two-signature / COI rule present.
    two_sig = data.get("two_signature_rule")
    if not isinstance(two_sig, dict):
        errors.append("missing 'two_signature_rule' block")
    else:
        requires = two_sig.get("requires") or []
        if "author_signoff" not in requires or "independent_approver_signoff" not in requires:
            errors.append(
                "two_signature_rule.requires must include both "
                "'author_signoff' and 'independent_approver_signoff'"
            )

    coi = data.get("conflict_of_interest")
    if not isinstance(coi, dict):
        errors.append("missing 'conflict_of_interest' (COI) block")
    else:
        rule = str(coi.get("rule", ""))
        if "author" not in rule or "sole_closer" not in rule:
            errors.append(
                "conflict_of_interest.rule must encode author != sole_closer_of_own_P0"
            )

    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_RACI
    errors = check(path)
    if errors:
        print(f"RACI contract FAILED ({path}):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"RACI contract OK: {path}")
    print(f"  workstreams covered: {', '.join(REQUIRED_WORKSTREAMS)}")
    print("  two-signature rule: present")
    print("  COI clause (author != sole closer): present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
