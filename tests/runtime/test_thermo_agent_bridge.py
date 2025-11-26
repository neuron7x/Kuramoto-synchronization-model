"""Tests for the ThermoController <-> agent feedback bridge."""

from __future__ import annotations

import networkx as nx

from runtime.misanthropic_agent import MisanthropicAgent
from runtime.thermo_controller import ThermoController


def _build_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("a", cpu_norm=0.2)
    graph.add_node("b", cpu_norm=0.3)
    graph.add_edge("a", "b", latency_norm=0.7, coherency=0.5, type="covalent")
    return graph


def test_bind_agent_returns_hook() -> None:
    controller = ThermoController(_build_graph())
    agent = MisanthropicAgent(write_metrics=False)

    hook = controller.bind_agent("misanthropic", agent)
    hook({"coverage": 0.6, "cvar_hat": -0.2, "ood_score": 0.4})

    snapshot = controller.snapshot_metrics()
    before_capital = agent.capital
    controller.broadcast_agent_feedback(snapshot)
    assert agent.capital <= before_capital
    assert agent.lambda_cvar >= 0.0


def test_bind_agent_rejects_duplicates() -> None:
    controller = ThermoController(_build_graph())
    agent = MisanthropicAgent(write_metrics=False)
    controller.bind_agent("misanthropic", agent)

    try:
        controller.bind_agent("misanthropic", agent)
    except ValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("duplicate registration should raise")
