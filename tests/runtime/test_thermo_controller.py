from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from core.energy import system_free_energy
from runtime.link_activator import LinkActivator
from runtime.thermo_api import create_app
from runtime.thermo_controller import ThermoController


class RecordingActivator(LinkActivator):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Dict[str, object]] = []

    def apply(self, bond_type, src, dst):  # type: ignore[override]
        payload = super().apply(bond_type, src, dst)
        self.calls.append(payload)
        return payload


def _build_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("PulseGen", cpu_norm=0.2)
    graph.add_node("Analyzer", cpu_norm=0.25)
    graph.add_node("Trader", cpu_norm=0.35)
    graph.add_node("RiskMgr", cpu_norm=0.3)

    graph.add_edge(
        "PulseGen",
        "Analyzer",
        type="vdw",
        latency_norm=10.0,
        coherency=0.9,
    )
    graph.add_edge(
        "Trader",
        "RiskMgr",
        type="hydrogen",
        latency_norm=0.7,
        coherency=0.4,
    )
    return graph


def test_link_activator_maps_bonds_to_protocols():
    activator = LinkActivator()
    payload = activator.apply("metallic", "PulseGen", "Analyzer")

    assert payload["protocol"] == "CRDT"
    assert payload["library"] == "y-crdt"
    assert payload["source"] == "PulseGen"
    assert payload["target"] == "Analyzer"


def test_controller_triggers_activation_and_updates_telemetry(monkeypatch):
    graph = _build_graph()

    def fake_evolve(base_graph, snap, generations):  # noqa: D401 - test helper
        evolved = base_graph.copy()
        evolved.edges[("PulseGen", "Analyzer")]["type"] = "metallic"
        evolved.edges[("Trader", "RiskMgr")]["type"] = "metallic"
        return evolved

    monkeypatch.setattr("runtime.thermo_controller.evolve_bonds", fake_evolve)

    activator = RecordingActivator()
    controller = ThermoController(graph, link_activator=activator, audit_log_path=None)

    snapshot = controller.snapshot_metrics()
    baseline_energy = system_free_energy(
        {(u, v): data.get("type") for u, v, data in graph.edges(data=True)},
        snapshot.latencies,
        snapshot.coherency,
        snapshot.resource_usage,
        snapshot.entropy,
    )

    controller.control_step()

    assert controller.get_current_F() < baseline_energy
    assert len(activator.calls) == 2
    telemetry = controller.collect_telemetry()
    assert telemetry["bottleneck_edge"] in {"PulseGen→Analyzer", "Trader→RiskMgr"}
    assert telemetry["topology_id"].startswith("thermo-topology-")


def test_controller_rejects_energy_increase_and_logs(tmp_path: Path, monkeypatch):
    graph = nx.DiGraph()
    graph.add_node("PulseGen", cpu_norm=0.2)
    graph.add_node("Analyzer", cpu_norm=0.25)
    graph.add_edge("PulseGen", "Analyzer", type="metallic", latency_norm=0.3, coherency=0.95)

    activator = RecordingActivator()
    audit_path = tmp_path / "thermo.log"
    controller = ThermoController(graph, link_activator=activator, audit_log_path=audit_path)

    controller.control_step()
    stable_energy = controller.get_current_F()

    def degrade(base_graph, snap, generations):  # noqa: D401 - test helper
        mutated = base_graph.copy()
        mutated.edges[("PulseGen", "Analyzer")]["type"] = "vdw"
        return mutated

    monkeypatch.setattr("runtime.thermo_controller.evolve_bonds", degrade)

    controller.control_step()

    assert controller.get_current_F() == pytest.approx(stable_energy)
    assert not activator.calls  # no activations when change rejected
    contents = audit_path.read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(contents[-1])
    assert record["event"] == "monotonic_violation"


def test_thermo_status_endpoint_returns_snapshot(monkeypatch):
    graph = _build_graph()

    controller = ThermoController(graph, audit_log_path=None)

    def fake_evolve(base_graph, snap, generations):  # noqa: D401 - test helper
        return base_graph

    monkeypatch.setattr("runtime.thermo_controller.evolve_bonds", fake_evolve)
    controller.control_step()

    app = create_app(controller)
    client = TestClient(app)

    response = client.get("/thermo/status")
    assert response.status_code == 200
    payload = response.json()
    for key in {"current_F", "dF_dt", "max_edge_cost", "topology_id"}:
        assert key in payload
