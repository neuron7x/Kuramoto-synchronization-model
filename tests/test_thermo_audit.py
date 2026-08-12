# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import json
import time
import types

import networkx as nx
import pytest

from runtime.dual_approval import DualApprovalManager
from runtime.recovery_agent import RecoveryState
from runtime.thermo_controller import (
    CrisisComputation,
    ThermoController,
    ToleranceCheck,
)


def _build_simple_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("ingest", cpu_norm=0.4)
    graph.add_node("matcher", cpu_norm=0.5)
    graph.add_edge("ingest", "matcher", type="vdw", latency_norm=0.8, coherency=0.7)
    return graph


def test_audit_log_records_normal_step(tmp_path, monkeypatch):
    log_path = tmp_path / "thermo_audit.jsonl"
    monkeypatch.setattr(ThermoController, "AUDIT_LOG_PATH", log_path)

    controller = ThermoController(_build_simple_graph())
    controller.set_dual_approval_token(
        DualApprovalManager(secret="test-secret").issue_service_token(action_id="thermo_topology")
    )
    controller.manual_override_active = True
    controller.manual_override_reason = "maintenance window"

    controller.control_step()
    controller.control_step()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    latest_entry = json.loads(lines[-1])
    assert latest_entry["action"] == "accepted"
    assert latest_entry["manual_override"] is True
    assert latest_entry["override_reason"] == "maintenance window"
    assert latest_entry["topology_changes"] == []
    assert latest_entry["F_new"] == pytest.approx(controller.get_current_F())
    assert latest_entry["ts"] <= time.time()


def test_audit_log_records_rejected_actions(tmp_path, monkeypatch):
    log_path = tmp_path / "thermo_audit.jsonl"
    monkeypatch.setattr(ThermoController, "AUDIT_LOG_PATH", log_path)

    controller = ThermoController(_build_simple_graph())
    controller.set_dual_approval_token(
        DualApprovalManager(secret="test-secret").issue_service_token(action_id="thermo_topology")
    )
    controller.baseline_F = 1.0
    controller.baseline_ema = 1.0
    controller.previous_F = 1.0
    controller.crisis_ga.F_baseline = 1.0
    controller.previous_t = time.time() - 1.0

    def compute_stub(self, topology=None, snapshot=None):  # type: ignore[unused-argument]
        return 2.0

    controller._compute_free_energy = types.MethodType(compute_stub, controller)

    rejection = ToleranceCheck(accepted=False, reason="test_reject")
    crisis_result = CrisisComputation(
        state=RecoveryState(F_current=2.0, F_baseline=1.0, latency_spike=1.0, steps_in_crisis=1),
        action=None,
        new_topology=None,
        proposed_F=2.5,
        tolerance=rejection,
        latency_spike=1.0,
    )

    def crisis_stub(self, snapshot, current_F, crisis_mode):  # type: ignore[unused-argument]
        return crisis_result

    controller._handle_crisis = types.MethodType(crisis_stub, controller)

    controller.control_step()

    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1

    entry = json.loads(content[0])
    assert entry["action"] == "rejected"
    assert entry["circuit_breaker_active"] is True
    assert entry["F_old"] == pytest.approx(2.0)
    assert entry["F_new"] == pytest.approx(2.0)
    assert entry["topology_changes"] == []
