import json
import time

import networkx as nx
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
