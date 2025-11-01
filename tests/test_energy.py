import logging
import time
import types

import networkx as nx
import pytest

import runtime.thermo_controller as thermo_module
from core.energy import delta_free_energy
from runtime.recovery_agent import RecoveryAction
from runtime.thermo_controller import CRITICAL_HALT_STATE, ThermoController

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
    F1 = controller.get_current_F()
    t1 = controller.previous_t

    time.sleep(0.001)

    controller.control_step()
    F2 = controller.get_current_F()
    t2 = controller.previous_t

    assert t1 is not None and t2 is not None

    dFdt = delta_free_energy(F1, F2, t2 - t1)
    assert abs(dFdt) <= controller.epsilon_adaptive


def test_free_energy_monotonic_drop():
    graph = nx.DiGraph()
    graph.add_node("a", cpu_norm=0.5)
    graph.add_node("b", cpu_norm=0.5)
    graph.add_edge("a", "b", type="vdw", latency_norm=1.0, coherency=0.4)

    controller = ThermoController(graph)

    controller.control_step()
    F_before = controller.get_current_F()

    controller.control_step()
    F_after = controller.get_current_F()

    assert F_after <= F_before + controller.epsilon_adaptive


def test_circuit_breaker_blocks_unbounded_spike(caplog):
    graph = nx.DiGraph()
    graph.add_node("node_a", cpu_norm=0.5)
    graph.add_node("node_b", cpu_norm=0.6)
    graph.add_edge("node_a", "node_b", type="vdw", latency_norm=0.7, coherency=0.5)

    controller = ThermoController(graph)

    initial_edges = list(controller.graph.edges(data=True))
    initial_topology = controller._graph_to_topology(controller.graph)

    controller.baseline_F = 1.0
    controller.baseline_ema = 1.0
    controller.previous_F = 1.0
    controller.crisis_ga.F_baseline = 1.0

    call_counts = {"ga": 0, "apply": 0, "update": 0}

    def compute_stub(self, topology=None, snapshot=None):  # type: ignore[unused-argument]
        return 1.5

    controller._compute_free_energy = types.MethodType(compute_stub, controller)

    def evolve_stub(self, initial_topology, current_F):  # type: ignore[unused-argument]
        call_counts["ga"] += 1
        mutated = list(initial_topology)
        if mutated:
            src, dst, bond = mutated[0]
            mutated[0] = (src, dst, "ionic" if bond != "ionic" else "metallic")
        return mutated, 2.0, "critical"

    controller.crisis_ga.evolve = types.MethodType(evolve_stub, controller.crisis_ga)

    def apply_stub(self, new_topology):  # type: ignore[unused-argument]
        call_counts["apply"] += 1
        return True

    controller._apply_topology_changes = types.MethodType(apply_stub, controller)

    def choose_stub(self, state):  # type: ignore[unused-argument]
        return RecoveryAction.SLOW

    controller.recovery_agent.choose_action = types.MethodType(choose_stub, controller.recovery_agent)

    def update_stub(self, state, action, reward, next_state):  # type: ignore[unused-argument]
        call_counts["update"] += 1

    controller.recovery_agent.update = types.MethodType(update_stub, controller.recovery_agent)

    with caplog.at_level(logging.INFO, logger="tradepulse.audit"):
        controller.control_step()

    assert controller.circuit_breaker_active is True
    assert call_counts["ga"] == 1
    assert call_counts["apply"] == 0
    assert call_counts["update"] == 0
    assert controller.current_topology == initial_topology
    assert list(controller.graph.edges(data=True)) == initial_edges
    assert any("circuit breaker" in record.message.lower() for record in caplog.records)

    caplog.clear()

    with caplog.at_level(logging.INFO, logger="tradepulse.audit"):
        controller.control_step()

    assert call_counts["ga"] == 1
    assert call_counts["update"] == 0
    assert any("circuit breaker" in record.message.lower() for record in caplog.records)


def test_sustained_rise_triggers_critical_halt(monkeypatch, caplog):
    graph = nx.DiGraph()
    graph.add_node("node_a", cpu_norm=0.4)
    graph.add_node("node_b", cpu_norm=0.5)
    graph.add_edge("node_a", "node_b", type="vdw", latency_norm=0.8, coherency=0.7)

    controller = ThermoController(graph)

    controller.baseline_F = 100.0
    controller.baseline_ema = 100.0
    controller.previous_F = 100.0
    controller.crisis_ga.F_baseline = 100.0
    controller.unresolved_rise_steps = 0

    rising_values = iter([100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 100.7])

    def compute_stub(self, topology=None, snapshot=None):  # type: ignore[unused-argument]
        return next(rising_values)

    controller._compute_free_energy = types.MethodType(compute_stub, controller)

    def epsilon_stub(self, dF_dt: float) -> None:  # type: ignore[unused-argument]
        self.epsilon_adaptive = float("inf")

    controller._update_adaptive_epsilon = types.MethodType(epsilon_stub, controller)

    gradient_calls = {"count": 0}

    def gradient_stub(graph, snapshot, lr=0.02):  # type: ignore[unused-argument]
        if controller.circuit_breaker_active:
            raise AssertionError("gradient descent should not run during CRITICAL_HALT")
        gradient_calls["count"] += 1
        return False

    monkeypatch.setattr(thermo_module, "gradient_descent_step", gradient_stub)

    initial_topology = list(controller.current_topology)
    initial_edges = list(controller.graph.edges(data=True))

    with caplog.at_level(logging.CRITICAL, logger="tradepulse.audit"):
        for _ in range(7):
            controller.previous_t = time.time() - 1.0
            controller.control_step()

    assert controller.circuit_breaker_active is True
    assert controller.controller_state == CRITICAL_HALT_STATE
    assert controller.unresolved_rise_steps >= 6
    assert gradient_calls["count"] == 5
    assert controller.current_topology == initial_topology
    assert list(controller.graph.edges(data=True)) == initial_edges
    assert controller.telemetry_history[-1]["crisis_mode"] == CRITICAL_HALT_STATE
    assert any(getattr(record, "code", None) == "B1" for record in caplog.records)
