import json

import networkx as nx

from runtime.thermo_controller import ControlStepResult, ToleranceCheck
from scripts import admission_check


def test_load_topology_from_file(tmp_path):
    topology = {
        "nodes": [
            {"id": "a", "cpu_norm": 0.5},
            "b",
        ],
        "edges": [
            {"src": "a", "dst": "b", "type": "ionic", "latency_norm": 0.7},
        ],
    }
    path = tmp_path / "topology.json"
    path.write_text(json.dumps(topology), encoding="utf-8")

    graph = admission_check.load_topology(path)

    assert set(graph.nodes()) == {"a", "b"}
    assert graph.edges[("a", "b")]["type"] == "ionic"
    assert graph.edges[("a", "b")]["latency_norm"] == 0.7


def test_perform_admission_check_uses_simulation(monkeypatch):
    expected_graph = nx.DiGraph()

    expected_result = ControlStepResult(
        accepted=True,
        circuit_breaker_active=False,
        tolerance=ToleranceCheck(accepted=True, reason="ok"),
        controller_state="normal",
    )

    class DummyController:
        def __init__(self, graph):
            assert graph is expected_graph

        def control_step(self, simulated=True):  # noqa: D401 - test stub
            assert simulated is True
            return expected_result

    monkeypatch.setattr(admission_check, "load_topology", lambda path: expected_graph)
    monkeypatch.setattr(admission_check, "ThermoController", DummyController)

    result = admission_check.perform_admission_check(None)

    assert result is expected_result


def test_main_returns_failure_on_rejection(monkeypatch, capsys):
    rejected = ControlStepResult(
        accepted=False,
        circuit_breaker_active=False,
        tolerance=ToleranceCheck(accepted=False, reason="boom"),
        controller_state="elevated",
    )

    monkeypatch.setattr(admission_check, "perform_admission_check", lambda path: rejected)

    exit_code = admission_check.main([])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "blocked deployment" in captured.out


def test_main_succeeds_for_safe_state(monkeypatch, capsys):
    accepted = ControlStepResult(
        accepted=True,
        circuit_breaker_active=False,
        tolerance=ToleranceCheck(accepted=True, reason="stable"),
        controller_state="normal",
    )

    monkeypatch.setattr(admission_check, "perform_admission_check", lambda path: accepted)

    exit_code = admission_check.main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "controller simulation accepted" in captured.out
