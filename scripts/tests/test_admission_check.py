from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from scripts import admission_check


class DummyController:
    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def control_step(self, *, simulated: bool = False):  # type: ignore[override]
        assert simulated is True
        return admission_check.ControlStepResult(
            tolerance=admission_check.ToleranceCheck(accepted=True, reason="stable"),
            circuit_breaker_active=False,
            controller_state="normal",
        )


def test_main_accepts_topology(monkeypatch):
    monkeypatch.setattr(admission_check, "ThermoController", DummyController)
    monkeypatch.setattr(
        admission_check,
        "load_topology",
        lambda path=None: nx.DiGraph(),
    )

    exit_code = admission_check.main([])
    assert exit_code == 0


def test_main_rejects_on_blocked_topology(monkeypatch):
    class RejectingController(DummyController):
        def control_step(self, *, simulated: bool = False):  # type: ignore[override]
            assert simulated is True
            return admission_check.ControlStepResult(
                tolerance=admission_check.ToleranceCheck(
                    accepted=False, reason="free_energy_spike"
                ),
                circuit_breaker_active=True,
                controller_state="critical",
            )

    monkeypatch.setattr(admission_check, "ThermoController", RejectingController)
    monkeypatch.setattr(
        admission_check,
        "load_topology",
        lambda path=None: nx.DiGraph(),
    )

    exit_code = admission_check.main([])
    assert exit_code == 1


def test_load_topology_from_json(tmp_path: Path):
    topology = {
        "nodes": [
            {"id": "a", "cpu_norm": 0.5},
            {"id": "b", "cpu_norm": 0.3},
        ],
        "edges": [
            {"source": "a", "target": "b", "type": "vdw", "latency_norm": 0.8},
            {"source": "b", "target": "a", "type": "ionic", "latency_norm": 0.6},
        ],
    }
    path = tmp_path / "topology.json"
    path.write_text(json.dumps(topology))

    graph = admission_check.load_topology(path)
    assert set(graph.nodes) == {"a", "b"}
    assert graph.edges["a", "b"]["type"] == "vdw"
    assert graph.edges["b", "a"]["type"] == "ionic"


@pytest.mark.parametrize("invalid_payload", [{}, {"nodes": []}, {"nodes": [{}], "edges": []}])
def test_load_topology_validation(tmp_path: Path, invalid_payload):
    path = tmp_path / "topology.json"
    path.write_text(json.dumps(invalid_payload))

    with pytest.raises(ValueError):
        admission_check.load_topology(path)
