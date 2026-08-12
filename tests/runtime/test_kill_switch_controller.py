# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import json

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from runtime.dual_approval import DualApprovalManager
from runtime.kill_switch import activate_kill_switch, deactivate_kill_switch
from runtime.thermo_controller import CRITICAL_HALT_STATE, ThermoController


@pytest.fixture(autouse=True)
def cleanup_kill_switch():
    deactivate_kill_switch()
    yield
    deactivate_kill_switch()


def _graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("ingest", cpu_norm=0.4)
    graph.add_node("matcher", cpu_norm=0.5)
    graph.add_edge("ingest", "matcher", type="vdw", latency_norm=0.8, coherency=0.7)
    return graph


def test_kill_switch_prevents_control_step(tmp_path, monkeypatch):
    log_path = tmp_path / "thermo_audit.jsonl"
    monkeypatch.setattr(ThermoController, "AUDIT_LOG_PATH", log_path)
    controller = ThermoController(_graph())
    controller.set_dual_approval_token(
        DualApprovalManager(secret="test-secret").issue_service_token(action_id="thermo_topology")
    )

    activate_kill_switch()
    controller.control_step()

    assert controller.controller_state == CRITICAL_HALT_STATE
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["action"] == "kill_switch"
    assert entry["circuit_breaker_active"] is True


def test_apply_stabilizer_blocks_when_por(monkeypatch):
    controller = ThermoController(_graph())

    def fake_process(raw_signals, ga_phase):
        controller.stabilizer._log_event(  # type: ignore[attr-defined]
            ga_phase,
            {
                "phase": "pre-spike",
                "action": "veto",
                "integrity": 0.5,
                "monotonic": "violated",
            },
            action_class="SELF_REGULATE",
            allowed=False,
        )
        controller.stabilizer.system_mode = "PoR"  # force rest mode
        return []

    monkeypatch.setattr(controller.stabilizer, "process_signals_sync", fake_process)

    df = pd.DataFrame({"coherency": np.linspace(0.0, 1.0, num=4)})
    result = controller._apply_stabilizer(df, ga_phase="pre_evolve")

    assert (result["coherency"] == 0.0).all()
    block_event = controller.stabilizer.get_eventlog()[-1]
    assert block_event["data"].get("action") == "external_block"
    assert block_event["data"].get("reason") == "system_mode_PoR"
    assert block_event["action_class"] == "INFLUENCE_EXTERNAL"
    assert controller.crisis_ga.homeostasis_penalty == 0.0


# --- DEFECT 1: public trip helper must not be suppressible by the cooldown ---
def test_public_activate_bypasses_cooldown_and_returns_result(monkeypatch):
    """activate_kill_switch() must force through the anti-toggle cooldown.

    Before the fix the public helper called ``.activate(reason, source)`` without
    ``force=True`` and discarded the bool, so an automated trip within
    ``cooldown_seconds`` of a prior state change (e.g. an operator deactivate)
    was silently refused and the caller could not tell.
    """
    import runtime.kill_switch as ks

    mgr = ks.KillSwitchManager(_force_new=True, cooldown_seconds=100.0)
    monkeypatch.setattr(ks, "_manager", mgr)

    # Arm the cooldown with a real prior state change.
    assert mgr.activate("prior", force=True) is True
    assert mgr.deactivate("operator_clear", force=True) is True
    assert mgr.is_active() is False

    # Sanity: an UNFORCED activate is refused inside the cooldown window
    # (this is exactly what the old helper did).
    assert mgr.activate("would_block", source="auto") is False
    assert mgr.is_active() is False

    # The public trip helper must bypass the cooldown and report success.
    result = ks.activate_kill_switch(ks.KillSwitchReason.CIRCUIT_BREAKER, source="auto")
    assert result is True
    assert mgr.is_active() is True


# --- DEFECT 2: a failing halt callback must be surfaced, not swallowed ---
def test_failing_halt_callback_surfaces_but_isolates_others():
    """A halt callback that raises must fail CLOSED: other callbacks still run,
    the internal state stays changed, and the failure is surfaced (not a silent
    ``True`` while the protective side-effect never executed)."""
    import runtime.kill_switch as ks

    mgr = ks.KillSwitchManager(_force_new=True, cooldown_seconds=0.0)
    calls: list[str] = []

    def bad(active: bool, reason: str) -> None:
        calls.append("bad")
        raise RuntimeError("flatten failed")

    def good(active: bool, reason: str) -> None:
        calls.append("good")

    mgr.register_callback(bad)
    mgr.register_callback(good)

    with pytest.raises(ks.KillSwitchCallbackError) as excinfo:
        mgr.activate(ks.KillSwitchReason.SECURITY_INCIDENT, source="auto", force=True)

    # Per-callback isolation preserved: the good callback still fired.
    assert "bad" in calls and "good" in calls
    # Failure surfaced with the underlying exception attached.
    assert any(isinstance(e, RuntimeError) for e in excinfo.value.errors)
    # State transition NOT rolled back (fail-closed).
    assert mgr.is_active() is True
