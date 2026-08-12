# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import networkx as nx
import pytest

import runtime.thermo_controller as thermo


@pytest.mark.skipif(
    thermo.evolve_bonds.__module__ != "runtime.thermo_controller",
    reason="DEAP is installed; fallback behaviour is not active.",
)
def test_fallback_evolution_warns_and_returns_copy():
    if hasattr(thermo, "_FALLBACK_WARNING_EMITTED"):
        thermo._FALLBACK_WARNING_EMITTED = False  # type: ignore[attr-defined]

    graph = nx.DiGraph()
    graph.add_edge("a", "b", type="covalent")

    snapshot = thermo.MetricsSnapshot(
        latencies={("a", "b"): 0.5},
        coherency={("a", "b"): 0.9},
        resource_usage=0.4,
        entropy=0.1,
    )

    with pytest.warns(RuntimeWarning):
        evolved = thermo.evolve_bonds(graph, snapshot, generations=5)

    assert evolved is not graph
    assert sorted(evolved.edges(data=True)) == sorted(graph.edges(data=True))
