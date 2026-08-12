# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for monotonic violation tracking and telemetry exposure."""

from __future__ import annotations

import networkx as nx
from fastapi.testclient import TestClient

from runtime import thermo_api
from runtime.thermo_controller import ThermoController, ToleranceCheck


def _build_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("a", cpu_norm=0.2)
    graph.add_node("b", cpu_norm=0.3)
    graph.add_edge("a", "b", type="covalent", latency_norm=0.5, coherency=0.7)
    return graph


def test_monotonic_violation_counter_increments() -> None:
    controller = ThermoController(_build_graph())

    assert controller.get_monotonic_violations_total() == 0

    controller._record_tolerance_outcome(  # type: ignore[attr-defined]
        ToleranceCheck(accepted=False, reason="test_violation")
    )

    assert controller.get_monotonic_violations_total() == 1

    controller._record_tolerance_outcome(  # type: ignore[attr-defined]
        ToleranceCheck(accepted=True, reason="ok")
    )

    assert controller.get_monotonic_violations_total() == 1


def test_status_reports_monotonic_violation_total(monkeypatch) -> None:
    controller = ThermoController(_build_graph())
    controller._record_tolerance_outcome(  # type: ignore[attr-defined]
        ToleranceCheck(accepted=False, reason="test_violation")
    )

    monkeypatch.setattr(thermo_api, "_controller", controller)
    client = TestClient(thermo_api.app)

    response = client.get("/thermo/status")
    payload = response.json()

    assert payload["violations_total"] == 1
