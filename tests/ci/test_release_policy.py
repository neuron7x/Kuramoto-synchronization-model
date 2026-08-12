# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GOV-007 — negative + positive controls for the stop-the-line release gate.

The controls are DRIVEN BY THE POLICY: the suite enumerates every rule in
``ci/release_policy.yaml`` and, for each, proves that a state which trips it
yields NO_GO with that rule's id — and that a state which trips none yields GO.
So a rule added to the policy without a working detector cannot pass silently.

The load-bearing negative control (``test_no_manual_flag_turns_no_go_into_go``)
proves there is no code path where a manual / override / approval flag converts
a fired safety stop into GO.
"""

from __future__ import annotations

import copy
import inspect
from pathlib import Path
from typing import Any

import yaml

from scripts.ci.check_release_policy import (
    DEFAULT_POLICY,
    GO,
    NO_GO,
    evaluate,
    load_policy,
    main,
)

POLICY = load_policy(DEFAULT_POLICY)
RULES: list[dict[str, Any]] = POLICY["stop_rules"]
SAFETY_RULE_IDS = [r["id"] for r in RULES if r.get("category") == "safety"]


# --------------------------------------------------------------------------
# state builders driven by the policy (so the tests track the policy exactly)
# --------------------------------------------------------------------------
def _set(state: dict[str, Any], dotpath: str, value: Any) -> None:
    cur = state
    parts = dotpath.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _del(state: dict[str, Any], dotpath: str) -> None:
    cur = state
    parts = dotpath.split(".")
    for part in parts[:-1]:
        cur = cur.get(part, {})
    cur.pop(parts[-1], None)


_CLEAR_SENTINEL_STR = "__cleared__"


def _non_firing_value(op: str, value: Any) -> Any:
    """A value for which the clause does NOT fire (the all-clear state)."""
    if op == "gt":
        return value
    if op == "gte":
        return value - 1
    if op == "lt":
        return value
    if op == "lte":
        return value + 1
    if op == "eq":
        return _CLEAR_SENTINEL_STR if value is not _CLEAR_SENTINEL_STR else "__other__"
    if op == "ne":
        return value  # observed == value ⇒ ne is False ⇒ not fired
    if op == "in":
        return _CLEAR_SENTINEL_STR
    if op == "not_in":
        return value[0]
    raise AssertionError(f"unhandled op {op!r}")


def _firing_value(op: str, value: Any) -> Any:
    """A value for which the clause DOES fire (trips the stop)."""
    if op == "gt":
        return value + 1
    if op == "gte":
        return value
    if op == "lt":
        return value - 1
    if op == "lte":
        return value
    if op == "eq":
        return value
    if op == "ne":
        return "__definitely_not_%r__" % (value,)
    if op == "in":
        return value[0]
    if op == "not_in":
        return _CLEAR_SENTINEL_STR
    raise AssertionError(f"unhandled op {op!r}")


def clean_state() -> dict[str, Any]:
    """An all-clear release-state: every clause set to a non-firing value."""
    state: dict[str, Any] = {}
    for rule in RULES:
        for clause in rule["fires_if_any"]:
            _set(state, clause["field"], _non_firing_value(clause["op"], clause.get("value")))
    return state


# --------------------------------------------------------------------------
# POSITIVE control
# --------------------------------------------------------------------------
def test_all_clear_state_is_go() -> None:
    decision = evaluate(clean_state(), POLICY)
    assert decision["verdict"] == GO, decision
    assert decision["stop_count"] == 0
    assert decision["stop_ids"] == []


def test_policy_covers_the_eight_required_stop_conditions() -> None:
    """The eight required stop-the-line conditions are all present as rules."""
    required = {
        "STOP-INTEGRITY-MISMATCH",
        "STOP-STALE-EVIDENCE",
        "STOP-UNSUPPORTED-ENV",
        "STOP-CRITICAL-VULN",
        "STOP-CLAIM-EVIDENCE-CONTRADICTION",
        "STOP-DATA-LEAKAGE",
        "STOP-EXTERNAL-REPRO-FAILED",
        "STOP-NONDETERMINISTIC-CANONICAL",
    }
    assert required <= {r["id"] for r in RULES}


# --------------------------------------------------------------------------
# NEGATIVE controls — one per stop rule, generated from the policy
# --------------------------------------------------------------------------
def _first_clause(rule: dict[str, Any]) -> dict[str, Any]:
    return rule["fires_if_any"][0]


def test_each_stop_rule_triggers_no_go() -> None:
    for rule in RULES:
        clause = _first_clause(rule)
        state = clean_state()
        _set(state, clause["field"], _firing_value(clause["op"], clause.get("value")))
        decision = evaluate(state, POLICY)
        assert decision["verdict"] == NO_GO, f"{rule['id']} should stop the release: {decision}"
        assert rule["id"] in decision["stop_ids"], (
            f"{rule['id']} fired but is not in stop_ids: {decision['stop_ids']}"
        )
        # the machine-readable reason names the offending field
        stop = next(s for s in decision["stops"] if s["id"] == rule["id"])
        assert stop["triggers"][0]["field"] == clause["field"]


def test_each_stop_rule_fails_closed_on_absent_evidence() -> None:
    """A missing evidence field is itself a stop — absence is not clearance."""
    for rule in RULES:
        clause = _first_clause(rule)
        state = clean_state()
        _del(state, clause["field"])
        decision = evaluate(state, POLICY)
        assert decision["verdict"] == NO_GO, f"absent {clause['field']} must stop: {decision}"
        assert rule["id"] in decision["stop_ids"]
        stop = next(s for s in decision["stops"] if s["id"] == rule["id"])
        assert stop["triggers"][0]["observed"] is None
        assert "absent" in stop["triggers"][0]["why"]


def test_empty_state_stops_on_everything() -> None:
    decision = evaluate({}, POLICY)
    assert decision["verdict"] == NO_GO
    assert set(decision["stop_ids"]) == {r["id"] for r in RULES}


# --------------------------------------------------------------------------
# THE load-bearing control: no manual flag converts NO_GO into GO
# --------------------------------------------------------------------------
def test_no_manual_flag_turns_no_go_into_go() -> None:
    """A live safety stop stays NO_GO no matter what manual/override/approval
    keys are injected into the state."""
    base = clean_state()
    # trip a real safety stop
    vuln = next(r for r in RULES if r["id"] == "STOP-CRITICAL-VULN")
    clause = _first_clause(vuln)
    _set(base, clause["field"], _firing_value(clause["op"], clause.get("value")))

    injected_keys = [
        {"override": True},
        {"force": True},
        {"force_green": True},
        {"manual_ok": True},
        {"skip_stops": True},
        {"approved": True},
        {"waiver": {"granted": True, "by": "someone"}},
    ]
    for extra in injected_keys:
        state = copy.deepcopy(base)
        state.update(extra)
        # approval precondition explicitly satisfied — still must not override
        _set(state, "approval.approved", True)
        _set(state, "run.fresh", True)
        decision = evaluate(state, POLICY)
        assert decision["verdict"] == NO_GO, f"{extra} must not force GO: {decision}"
        assert "STOP-CRITICAL-VULN" in decision["stop_ids"], (
            f"{extra} removed the safety stop: {decision['stop_ids']}"
        )


def test_approval_alone_cannot_release_a_dirty_state() -> None:
    state = clean_state()
    _set(state, "approval.approved", True)
    _set(state, "data_leakage.leak_count", 1)  # a live leak
    decision = evaluate(state, POLICY)
    assert decision["verdict"] == NO_GO
    assert "STOP-DATA-LEAKAGE" in decision["stop_ids"]


def test_go_requires_approval_and_fresh_rerun() -> None:
    """Governance preconditions are themselves fail-closed: a clean-but-
    unapproved or stale-rerun state is NO_GO, proving recovery needs a fresh
    approved rerun, not a flag."""
    unapproved = clean_state()
    _set(unapproved, "approval.approved", False)
    d1 = evaluate(unapproved, POLICY)
    assert d1["verdict"] == NO_GO
    assert "GOV-APPROVAL-ABSENT" in d1["stop_ids"]

    not_fresh = clean_state()
    _set(not_fresh, "run.fresh", False)
    d2 = evaluate(not_fresh, POLICY)
    assert d2["verdict"] == NO_GO
    assert "GOV-RERUN-NOT-FRESH" in d2["stop_ids"]


# --------------------------------------------------------------------------
# structural: the gate exposes no escape hatch
# --------------------------------------------------------------------------
def test_gate_exposes_no_force_or_override_flag() -> None:
    src = Path(inspect.getfile(main)).read_text(encoding="utf-8")
    forbidden = ("force", "override", "skip", "green", "waiver", "approve")
    for line in src.splitlines():
        if "add_argument" in line:
            low = line.lower()
            assert not any(tok in low for tok in forbidden), (
                f"gate must not expose an escape-hatch CLI flag: {line.strip()}"
            )


def test_evaluate_signature_takes_only_state_and_policy() -> None:
    params = list(inspect.signature(evaluate).parameters)
    assert params == ["state", "policy"], (
        f"evaluate() must not accept an override/approval parameter: {params}"
    )


# --------------------------------------------------------------------------
# the shipped example artifact is a real NO_GO record
# --------------------------------------------------------------------------
def test_example_stop_record_is_a_no_go() -> None:
    import json

    root = Path(__file__).resolve().parents[2]
    rec = json.loads(
        (root / "artifacts" / "release" / "stop_record.example.json").read_text(encoding="utf-8")
    )
    assert rec["verdict"] == NO_GO
    assert rec["stop_count"] == len(rec["stops"]) >= 1
    for stop in rec["stops"]:
        assert stop["id"] in {r["id"] for r in RULES}
        assert stop["triggers"], "a recorded stop must carry machine-readable triggers"


def test_real_policy_file_loads() -> None:
    doc = yaml.safe_load(DEFAULT_POLICY.read_text(encoding="utf-8"))
    assert doc["task"] == "GOV-007"
    assert isinstance(doc["stop_rules"], list) and doc["stop_rules"]
