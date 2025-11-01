"""Thermodynamic monotonicity regression tests."""

from __future__ import annotations

from typing import List, Tuple

import networkx as nx
import numpy as np
import pytest

from runtime.thermo_controller import MetricsSnapshot, ThermoController


def _compute_epsilon_spike(controller: ThermoController) -> float:
    """Mirror the controller's monotonic tolerance but guard against sign flips."""

    baseline = float(controller.baseline_ema)
    return max(1e-24, 0.01 * abs(baseline))


def _clone_snapshot(snapshot: MetricsSnapshot) -> MetricsSnapshot:
    return MetricsSnapshot(
        latencies=dict(snapshot.latencies),
        coherency=dict(snapshot.coherency),
        resource_usage=snapshot.resource_usage,
        entropy=snapshot.entropy,
    )


def _build_resilient_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("ingest", cpu_norm=0.55)
    graph.add_node("matcher", cpu_norm=0.52)
    graph.add_node("risk", cpu_norm=0.57)
    graph.add_edge("ingest", "matcher", type="metallic", latency_norm=0.45, coherency=0.88)
    graph.add_edge("matcher", "risk", type="hydrogen", latency_norm=0.5, coherency=0.83)
    graph.add_edge("risk", "ingest", type="metallic", latency_norm=0.48, coherency=0.85)
    return graph


@pytest.mark.monotonic
def test_ga_evolution_respects_monotonicity_budget() -> None:
    controller = ThermoController(_build_resilient_graph())
    controller.crisis_ga._rng = np.random.default_rng(2024)

    F_old = controller._compute_free_energy(snapshot=controller._latest_snapshot)
    epsilon_spike = _compute_epsilon_spike(controller)

    new_topology, F_new, crisis_mode = controller.crisis_ga.evolve(
        controller.current_topology,
        F_old,
    )

    assert crisis_mode in {"normal", "elevated", "critical"}
    assert F_new <= F_old + epsilon_spike


def _build_degraded_topology(topology: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
    mutated: List[Tuple[str, str, str]] = []
    threshold = max(1, int(0.2 * len(topology)))
    for idx, (src, dst, bond) in enumerate(topology):
        if idx < threshold:
            mutated.append((src, dst, "covalent"))
        else:
            mutated.append((src, dst, "ionic"))
    return mutated


def _build_high_stress_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("alpha", cpu_norm=0.6)
    graph.add_node("beta", cpu_norm=0.55)
    graph.add_node("gamma", cpu_norm=0.5)
    graph.add_node("delta", cpu_norm=0.52)
    graph.add_edge("alpha", "beta", type="metallic", latency_norm=0.9, coherency=0.7)
    graph.add_edge("beta", "gamma", type="hydrogen", latency_norm=1.1, coherency=0.6)
    graph.add_edge("gamma", "delta", type="metallic", latency_norm=0.85, coherency=0.65)
    graph.add_edge("delta", "alpha", type="hydrogen", latency_norm=1.2, coherency=0.6)
    graph.add_edge("alpha", "gamma", type="metallic", latency_norm=1.0, coherency=0.68)
    return graph


@pytest.mark.monotonic
def test_worsened_topology_trips_monotonicity_guardrail() -> None:
    controller = ThermoController(_build_high_stress_graph())
    snapshot = _clone_snapshot(controller._latest_snapshot)

    F_old = controller._compute_free_energy(snapshot=snapshot)
    epsilon_spike = _compute_epsilon_spike(controller)

    degraded_topology = _build_degraded_topology(list(controller.current_topology))
    F_bad = controller._compute_free_energy(topology=degraded_topology, snapshot=snapshot)

    with pytest.raises(AssertionError):
        assert F_bad <= F_old + epsilon_spike

    tolerance = controller._check_monotonic_with_tolerance(F_old, F_bad)
    assert not tolerance.accepted
    assert "free_energy_spike" in tolerance.reason
