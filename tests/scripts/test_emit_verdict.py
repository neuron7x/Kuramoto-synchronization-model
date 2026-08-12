# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the claim-governance evidence-bundle aggregator (emit_verdict)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci.emit_verdict import (
    GATES,
    Gate,
    GateOutcome,
    build_verdict,
    main,
    run_gate,
)


def _outcome(name: str, *, passed: bool) -> GateOutcome:
    return GateOutcome(
        name=name,
        command=f"python {name}.py",
        description="d",
        returncode=0 if passed else 1,
        passed=passed,
        summary="ok" if passed else "boom",
    )


def test_build_verdict__all_pass__release_ready_true() -> None:
    outcomes = [_outcome("a", passed=True), _outcome("b", passed=True)]
    v = build_verdict(outcomes, commit="abc123", timestamp="2026-06-18T00:00:00+00:00")
    assert v["release_ready"] is True
    assert v["blocking_gates"] == []
    assert v["gate_count"] == 2
    assert v["commit"] == "abc123"


def test_build_verdict__any_fail__release_ready_false_and_lists_blocker() -> None:
    """Fail-closed: one failing gate sinks the whole verdict and is named."""
    outcomes = [_outcome("a", passed=True), _outcome("b", passed=False)]
    v = build_verdict(outcomes, commit="x", timestamp="t")
    assert v["release_ready"] is False
    assert v["blocking_gates"] == ["b"]


def test_build_verdict__deterministic_for_fixed_inputs() -> None:
    """Byte-reproducible artifact: same inputs ⇒ identical canonical JSON."""
    outcomes = [_outcome("a", passed=True)]
    a = json.dumps(
        build_verdict(outcomes, commit="c", timestamp="t"), sort_keys=True
    )
    b = json.dumps(
        build_verdict(outcomes, commit="c", timestamp="t"), sort_keys=True
    )
    assert a == b


def test_run_gate__nonzero_exit__fails_closed() -> None:
    gate = Gate("boom", ("-c", "import sys; print('nope'); sys.exit(3)"), "always fails")
    outcome = run_gate(gate)
    assert outcome.passed is False
    assert outcome.returncode == 3
    assert outcome.summary == "nope"


def test_run_gate__zero_exit__passes_and_captures_summary() -> None:
    gate = Gate("okgate", ("-c", "print('all good')"), "passes")
    outcome = run_gate(gate)
    assert outcome.passed is True
    assert outcome.returncode == 0
    assert outcome.summary == "all good"


def test_main__all_pass_injected__writes_verdict_and_returns_zero(tmp_path: Path) -> None:
    out = tmp_path / "VERDICT.json"

    def fake_runner(gate: Gate) -> GateOutcome:
        return _outcome(gate.name, passed=True)

    rc = main(
        ["--output", str(out), "--timestamp", "2026-06-18T00:00:00+00:00"],
        runner=fake_runner,
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_ready"] is True
    assert payload["gate_count"] == len(GATES)
    assert {g["name"] for g in payload["gates"]} == {g.name for g in GATES}


def test_main__one_gate_fails_injected__returns_one_and_flags_not_ready(
    tmp_path: Path,
) -> None:
    out = tmp_path / "VERDICT.json"

    def fake_runner(gate: Gate) -> GateOutcome:
        return _outcome(gate.name, passed=gate.name != "claims-evidence")

    rc = main(
        ["--output", str(out), "--timestamp", "t"],
        runner=fake_runner,
    )
    assert rc == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["release_ready"] is False
    assert "claims-evidence" in payload["blocking_gates"]


def test_gates_registry__names_unique_and_nonempty() -> None:
    names = [g.name for g in GATES]
    assert len(names) == len(set(names)), "gate names must be unique"
    assert all(g.argv for g in GATES), "every gate needs an argv"


@pytest.mark.parametrize("blank", ["", "   \n  \n"])
def test_last_meaningful_line__blank_input__empty(blank: str) -> None:
    from scripts.ci.emit_verdict import _last_meaningful_line

    assert _last_meaningful_line(blank) == ""
