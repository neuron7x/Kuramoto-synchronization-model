"""Tests for the thermodynamic energy model."""

from __future__ import annotations

import math

import networkx as nx
import pytest

from core.engine.energy import (
    MIN_DISTANCE,
    PulseBuffer,
    ThermodynamicSystem,
    buffer_uncertainty,
    compute_potential_energy,
    gradient_descent_step,
    measure_entropy,
    total_latency,
)


def _build_simple_graph() -> nx.Graph:
    graph = nx.Graph()
    graph.add_node("source", charge=1.5)
    graph.add_node("sink", charge=0.75)
    graph.add_edge(
        "source",
        "sink",
        distance=2.0,
        data_size=2.0,
        bandwidth=4.0,
        jitter=0.1,
    )
    return graph


def test_measure_entropy_matches_theoretical_expectation() -> None:
    buffer = PulseBuffer(capacity=16)
    for latency in (0.25, 0.25, 0.75, 0.75):
        buffer.observe(timestamp=0.0, latency=latency)

    # Two equally likely outcomes → entropy equals ln(2).
    entropy = measure_entropy(buffer, bins=2)
    assert entropy == pytest.approx(math.log(2.0), rel=1e-5)


def test_internal_and_free_energy_components() -> None:
    graph = _build_simple_graph()
    system = ThermodynamicSystem(graph=graph, temperature=0.5, uncertainty_weight=2.0)
    system.buffer.extend(0.0, (0.4, 0.6))

    potential = compute_potential_energy(graph)
    latency_term = total_latency(graph)
    uncertainty_term = system.uncertainty_weight * buffer_uncertainty(system.buffer)
    expected_internal = potential + latency_term + uncertainty_term
    assert system.internal_energy() == pytest.approx(expected_internal)

    entropy = measure_entropy(system.buffer, bins=2)
    expected_free = expected_internal - system.temperature * entropy
    assert system.free_energy() == pytest.approx(expected_free)


def test_gradient_descent_step_reduces_potential_energy() -> None:
    graph = nx.Graph()
    graph.add_node("a", charge=1.0)
    graph.add_node("b", charge=1.0)
    graph.add_edge("a", "b", distance=1.0)

    before = compute_potential_energy(graph)
    gradient_descent_step(graph, learning_rate=0.2)
    after = compute_potential_energy(graph)

    assert after <= before
    assert graph.edges["a", "b"]["distance"] >= MIN_DISTANCE
