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
        DualApprovalManager(secret="test-secret").issue_service_token(
            action_id="thermo_topology"
        )
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
