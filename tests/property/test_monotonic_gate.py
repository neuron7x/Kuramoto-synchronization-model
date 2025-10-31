"""Tests covering the monotonic free-energy invariant."""

from __future__ import annotations

import math

import networkx as nx
import pytest
import sympy as sp

from runtime.monotonic_gate import (
    MonotonicGateResult,
    assert_monotonic_invariant,
    check_monotonic_invariant,
    compute_epsilon_spike,
    predict_recovery_window,
)
from runtime.thermo_controller import ThermoController


pytestmark = pytest.mark.monotonic


def _build_controller() -> ThermoController:
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
    return controller


def test_symbolic_invariant_boundary_condition() -> None:
    F_old, epsilon_spike, delta = sp.symbols(
        "F_old epsilon_spike delta", real=True, positive=True
    )
    F_new = sp.symbols("F_new", real=True, positive=True)
    invariant = sp.Lt(F_new, F_old + epsilon_spike)
    boundary = sp.simplify(invariant.subs(F_new, F_old + epsilon_spike - delta))

    assert boundary == sp.S.true


def test_monotonic_gate_blocks_violation() -> None:
    controller = _build_controller()
    F_old = controller.get_current_F()
    epsilon = compute_epsilon_spike(controller.baseline_ema)
    F_new = F_old + 2.5 * epsilon

    result = check_monotonic_invariant(F_old, F_new, epsilon)
    assert isinstance(result, MonotonicGateResult)
    assert result.holds is False

    with pytest.raises(AssertionError):
        assert_monotonic_invariant(F_old, F_new, baseline_ema=controller.baseline_ema)


def test_monotonic_gate_allows_predicted_recovery() -> None:
    controller = _build_controller()
    F_old = controller.get_current_F()
    epsilon = compute_epsilon_spike(controller.baseline_ema)
    spike = 1.5 * epsilon
    F_new = F_old + spike

    predictions = [F_old * 0.95, F_old * 0.9, F_old * 0.85]
    result = assert_monotonic_invariant(
        F_old,
        F_new,
        baseline_ema=controller.baseline_ema,
        predictions=predictions,
    )

    assert result.holds is True
    assert math.isclose(result.epsilon_spike, epsilon, rel_tol=1e-9)


def test_predict_recovery_window_regresses_to_baseline() -> None:
    F_old = 1.0e-6
    baseline = 0.9e-6
    F_new = F_old * 1.2

    predictions = predict_recovery_window(F_new, baseline, window_size=3)
    assert len(predictions) == 3
    assert predictions[0] > baseline
    assert predictions[-1] > baseline
    assert sum(predictions) / len(predictions) < F_new
