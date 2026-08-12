#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GOV-007 stop-the-line release gate — interpreter of ``ci/release_policy.yaml``.

Given a *release-state* JSON, this gate returns ``GO`` if and only if ZERO stop
rules fire, and ``NO_GO`` otherwise with a machine-readable reason per fired
rule. The policy file is the sole source of truth for the stop conditions; this
module never hard-codes a condition and never special-cases a rule.

Three properties are load-bearing and each is covered by a negative control in
``tests/ci/test_release_policy.py``:

  * **No MANUAL-as-GREEN path.** A condition is GREEN only when its evidence
    field is present AND within bound. There is no branch that reads a note,
    sign-off, or marker and treats it as GREEN.
  * **Fail-closed on absence.** A clause whose evidence field is missing FIRES
    (stops the release). Absence of evidence is never read as "clear".
  * **No stop is overridable.** The verdict is a pure function of which stop
    rules fired. This module reads no ``force`` / ``skip`` / override key, and
    exposes no CLI flag that can turn a fired stop into GO. Recovery is a fresh,
    approved rerun — modeled as the fail-closed ``governance`` rules in the
    policy, which can only ADD a NO_GO reason, never remove a safety stop.

Exit codes::

    0  — GO      (zero stop rules fired)
    1  — NO_GO   (at least one stop rule fired)
    2  — usage / unparseable policy or state (fail-closed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "ci" / "release_policy.yaml"

GO = "GO"
NO_GO = "NO_GO"

# Sentinel for "the evidence field was absent from the release-state". Kept
# distinct from ``None`` so a field explicitly set to null is still a real,
# present value (and evaluated on its merits) while a genuinely missing field
# fails closed.
_ABSENT = object()

_SUPPORTED_OPS = frozenset({"gt", "gte", "lt", "lte", "eq", "ne", "in", "not_in"})


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    """Load and minimally validate the policy document."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"policy root must be a mapping: {path}")
    rules = doc.get("stop_rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError(f"policy has no stop_rules: {path}")
    for rule in rules:
        if not isinstance(rule, dict) or "id" not in rule:
            raise ValueError(f"malformed stop rule (needs id): {rule!r}")
        clauses = rule.get("fires_if_any")
        if not isinstance(clauses, list) or not clauses:
            raise ValueError(f"rule {rule.get('id')!r} has no fires_if_any clauses")
        for clause in clauses:
            op = clause.get("op")
            if op not in _SUPPORTED_OPS:
                raise ValueError(f"rule {rule.get('id')!r} uses unsupported op {op!r}")
    return doc


def _resolve(state: Any, dotpath: str) -> Any:
    """Return the value at ``dotpath`` in ``state`` or ``_ABSENT`` if any hop
    is missing / not a mapping. Missing means fail-closed at the call site."""
    cur: Any = state
    for part in dotpath.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _ABSENT
        cur = cur[part]
    return cur


def _op_true(op: str, observed: Any, expected: Any) -> bool:
    """Evaluate ``observed <op> expected``. A type error is treated as a fired
    clause (fail-closed) rather than silently swallowed."""
    try:
        if op == "gt":
            return observed > expected
        if op == "gte":
            return observed >= expected
        if op == "lt":
            return observed < expected
        if op == "lte":
            return observed <= expected
        if op == "eq":
            return observed == expected
        if op == "ne":
            return observed != expected
        if op == "in":
            return observed in expected
        if op == "not_in":
            return observed not in expected
    except TypeError:
        return True  # incomparable / wrong-typed evidence -> fail closed
    raise ValueError(f"unsupported op {op!r}")  # pragma: no cover - guarded in load_policy


def _clause_fires(state: Any, clause: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Return (fired, machine_reason) for a single clause."""
    field = str(clause["field"])
    op = str(clause["op"])
    expected = clause.get("value")
    observed = _resolve(state, field)

    if observed is _ABSENT:
        return True, {
            "field": field,
            "op": op,
            "expected": expected,
            "observed": None,
            "why": "evidence field absent — fail-closed (absence is not clearance)",
        }

    fired = _op_true(op, observed, expected)
    return fired, {
        "field": field,
        "op": op,
        "expected": expected,
        "observed": observed,
        "why": f"observed {observed!r} {op} {expected!r}" if fired else "within bound",
    }


def _rule_fires(state: Any, rule: dict[str, Any]) -> dict[str, Any] | None:
    """Return a machine-readable stop record if the rule fires, else None."""
    triggers: list[dict[str, Any]] = []
    for clause in rule["fires_if_any"]:
        fired, reason = _clause_fires(state, clause)
        if fired:
            triggers.append(reason)
    if not triggers:
        return None
    return {
        "id": rule["id"],
        "category": rule.get("category", "safety"),
        "title": rule.get("title", rule["id"]),
        "description": (rule.get("description") or "").strip(),
        "triggers": triggers,
    }


def evaluate(state: Any, policy: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all stop rules against ``state``.

    The verdict is a pure function of ``stops``: GO iff no rule fired. There is
    deliberately no other input — no flag, marker, or approval token can change
    a GO into NO_GO's complement once a stop has fired.
    """
    stops: list[dict[str, Any]] = []
    for rule in policy["stop_rules"]:
        record = _rule_fires(state, rule)
        if record is not None:
            stops.append(record)

    verdict = GO if not stops else NO_GO
    return {
        "verdict": verdict,
        "task": policy.get("task", "GOV-007"),
        "policy_version": policy.get("version"),
        "stop_count": len(stops),
        "stop_ids": [s["id"] for s in stops],
        "stops": stops,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GOV-007 stop-the-line release gate.")
    parser.add_argument(
        "state",
        type=Path,
        help="path to the release-state JSON to evaluate",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY,
        help="path to the machine-readable release policy (default: ci/release_policy.yaml)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="optional path to write the machine-readable decision record",
    )
    # Note: there is intentionally NO --force / --override / --approve flag.
    # Recovery from NO_GO is a fresh, approved rerun (governance rules), never a
    # command-line escape hatch.
    args = parser.parse_args(argv)

    try:
        policy = load_policy(args.policy)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: cannot load policy: {exc}", file=sys.stderr)
        return 2

    try:
        state = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load release-state: {exc}", file=sys.stderr)
        return 2

    decision = evaluate(state, policy)

    if args.json is not None:
        args.json.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if decision["verdict"] == GO:
        print(f"[GOV-007] GO — zero stop conditions fired (policy v{decision['policy_version']}).")
        return 0

    print(f"[GOV-007] NO_GO — {decision['stop_count']} stop condition(s) fired:", file=sys.stderr)
    for stop in decision["stops"]:
        print(f"  - {stop['id']} ({stop['category']}): {stop['title']}", file=sys.stderr)
        for trig in stop["triggers"]:
            print(f"      · {trig['field']}: {trig['why']}", file=sys.stderr)
    print(
        "[GOV-007] Recovery: fix the cause, then a FRESH approved rerun. "
        "No override flag exists.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
