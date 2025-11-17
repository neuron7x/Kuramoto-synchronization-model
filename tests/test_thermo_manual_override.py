import logging
import time

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from runtime import thermo_api
from runtime.dual_approval import DualApprovalManager
from runtime.thermo_controller import CRITICAL_HALT_STATE, CrisisMode, ThermoController


def _build_simple_controller() -> ThermoController:
    graph = nx.DiGraph()
    graph.add_node("a", cpu_norm=0.4)
    graph.add_node("b", cpu_norm=0.5)
    graph.add_edge("a", "b", type="vdw", latency_norm=0.8, coherency=0.7)
    controller = ThermoController(graph)
    token = DualApprovalManager(secret="test-secret").issue_service_token(
        action_id="thermo_topology"
    )
    controller.set_dual_approval_token(token)
    return controller


def test_manual_override_resets_circuit_breaker(caplog):
    controller = _build_simple_controller()
    controller.circuit_breaker_active = True
    controller.unresolved_rise_steps = 7
    controller.controller_state = CRITICAL_HALT_STATE

    with caplog.at_level(logging.WARNING, logger="tradepulse.audit"):
        controller.manual_override("operator acknowledged incident")

    assert controller.circuit_breaker_active is False
    assert controller.unresolved_rise_steps == 0
    assert controller.crisis_step_count == 0
    assert controller.override_reason == "operator acknowledged incident"
    assert controller.override_time is not None
    assert time.time() - controller.override_time < 5
    assert controller.controller_state == CrisisMode.NORMAL

    override_records = [
        r for r in caplog.records if getattr(r, "manual_override", False)
    ]
    assert (
        override_records
    ), "manual override should be logged with manual_override flag"
    assert override_records[0].code == "B1"
    assert "manually overridden" in override_records[0].message


@pytest.fixture(autouse=True)
def reset_api_controller():
    original_controller = thermo_api._controller
    thermo_api._controller = None
    yield
    thermo_api._controller = original_controller


def test_override_endpoint_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("THERMO_OVERRIDE_TOKEN", "super-secret-token")

    controller = _build_simple_controller()
    controller.circuit_breaker_active = True
    controller.unresolved_rise_steps = 6

    monkeypatch.setattr(thermo_api, "get_controller", lambda: controller)

    client = TestClient(thermo_api.app)

    response = client.post(
        "/thermo/override",
        json={"token": "super-secret-token", "reason": "post-incident review complete"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "override_accepted"
    assert controller.circuit_breaker_active is False
    assert controller.unresolved_rise_steps == 0
    assert controller.override_reason == "post-incident review complete"


def test_override_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("THERMO_OVERRIDE_TOKEN", "expected-token")

    controller = _build_simple_controller()
    controller.circuit_breaker_active = True

    monkeypatch.setattr(thermo_api, "get_controller", lambda: controller)

    client = TestClient(thermo_api.app)

    response = client.post(
        "/thermo/override",
        json={"token": "bad-token", "reason": "intrusion"},
    )

    assert response.status_code == 401
    assert controller.circuit_breaker_active is True
    assert controller.override_reason is None
