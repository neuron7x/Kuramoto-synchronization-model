import time

import networkx as nx
import pytest

from core.energy import delta_free_energy
from runtime.thermo_controller import ThermoController

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
