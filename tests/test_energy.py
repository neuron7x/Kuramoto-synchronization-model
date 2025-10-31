import time

import math

import networkx as nx
import pytest

from core.energy import delta_free_energy, system_free_energy
from evolution.bond_evolver import MetricsSnapshot
from runtime.thermo_controller import ThermoController, gradient_descent_step

pytestmark = pytest.mark.stability


def test_dFdt_is_small_under_controller():
    graph = nx.DiGraph()
    graph.add_node("ingest", cpu_norm=0.4)
    graph.add_node("matcher", cpu_norm=0.6)
    graph.add_node("risk", cpu_norm=0.5)
    graph.add_node("broker", cpu_norm=0.3)

    graph.add_edge("ingest", "matcher", type="covalent", latency_norm=0.4, coherency=0.9)
    graph.add_edge("matcher", "risk", type="ionic", latency_norm=0.8, coherency=0.7)
    graph.add_edge("risk", "broker", type="metallic", latency_norm=0.2, coherency=0.85)
    graph.add_edge("broker", "ingest", type="hydrogen", latency_norm=1.1, coherency=0.6)

    controller = ThermoController(graph)

    controller.control_step()
    F1 = controller.prev_F
    t1 = controller.prev_t

    time.sleep(0.001)

    controller.control_step()
    F2 = controller.prev_F
    t2 = controller.prev_t

    assert F1 is not None and F2 is not None
    assert t1 is not None and t2 is not None

    dFdt = delta_free_energy(F1, F2, t2 - t1)
    assert abs(dFdt) < 1e-12, f"dF/dt too high: {dFdt}"


def test_free_energy_monotonic_drop():
    graph = nx.DiGraph()
    graph.add_node("a", cpu_norm=0.5)
    graph.add_node("b", cpu_norm=0.5)
    graph.add_edge("a", "b", type="vdw", latency_norm=1.0, coherency=0.4)

    controller = ThermoController(graph)

    controller.control_step()
    F_before = controller.prev_F

    controller.control_step()
    F_after = controller.prev_F

    assert F_before is not None and F_after is not None
    assert F_after <= F_before + 1e-12


def test_gradient_descent_step_improves_energy():
    graph = nx.DiGraph()
    graph.add_node("a", cpu_norm=0.4)
    graph.add_node("b", cpu_norm=0.4)
    graph.add_edge("a", "b", type="vdw", latency_norm=0.2, coherency=0.95)

    controller = ThermoController(graph)
    snapshot = controller.snapshot_metrics()

    bonds_before = {(u, v): data.get("type") for u, v, data in graph.edges(data=True)}
    energy_before = system_free_energy(
        bonds_before,
        snapshot.latencies,
        snapshot.coherency,
        snapshot.resource_usage,
        snapshot.entropy,
    )

    changed = gradient_descent_step(graph, snapshot, lr=0.05)

    bonds_after = {(u, v): data.get("type") for u, v, data in graph.edges(data=True)}
    energy_after = system_free_energy(
        bonds_after,
        snapshot.latencies,
        snapshot.coherency,
        snapshot.resource_usage,
        snapshot.entropy,
    )

    assert changed
    assert energy_after < energy_before


def test_system_free_energy_bounds_non_finite_metrics():
    bonds = {("a", "b"): "vdw"}
    latencies = {("a", "b"): math.inf}
    coherency = {("a", "b"): math.nan}
    snapshot = MetricsSnapshot(latencies, coherency, resource_usage=math.inf, entropy=math.nan)

    energy = system_free_energy(
        bonds,
        snapshot.latencies,
        snapshot.coherency,
        snapshot.resource_usage,
        snapshot.entropy,
    )

    assert math.isfinite(energy)
