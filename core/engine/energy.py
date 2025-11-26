"""Thermodynamic energy model for impulse-driven trading graphs.

This module provides a lightweight abstraction that maps TradePulse's
computation graph into a thermodynamic system.  Nodes behave like charged
particles, edges encode communication channels, and the resulting energy
surface can be optimised via gradient descent to reduce execution latency and
instability.

The implementation is intentionally self-contained and depends only on
``networkx`` and ``numpy`` which are already part of the platform.  It exposes
three main concepts:

``PulseBuffer``
    Rolling window of latency measurements.  The buffer computes Shannon
    entropy which stands in for thermodynamic entropy in the trading system.

``ThermodynamicSystem``
    Couples a computational graph and a ``PulseBuffer``.  It provides
    convenience helpers for measuring internal and free energy of the system.

``gradient_descent_step``
    Single optimisation step that adjusts edge distances (communication
    latencies) following the Coulomb potential.  Lower energy states correspond
    to more efficient execution graphs.

The public API follows modern 2025 Python practices: dataclasses with ``slots``
for reduced overhead, type hints, input validation, and numerically stable
operations using ``numpy``.  Each function is written with readability and
testability in mind.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import networkx as nx
import numpy as np

# Normalised Coulomb constant (scaled to avoid astronomical magnitudes while
# preserving the inverse-distance relationship).
COULOMB_CONSTANT: float = 1.0

# Guardrails to maintain numerical stability and physical plausibility.
MIN_DISTANCE: float = 1e-6
MIN_BANDWIDTH: float = 1e-9


@dataclass(slots=True)
class PulseBuffer:
    """Rolling buffer of latency measurements.

    Parameters
    ----------
    capacity:
        Maximum number of samples stored in the buffer.  When the capacity is
        exceeded the oldest samples are discarded.
    """

    capacity: int = 4096
    timestamps: deque[float] = field(default_factory=deque)
    latencies: deque[float] = field(default_factory=deque)

    def observe(self, timestamp: float, latency: float) -> None:
        """Record a latency measurement.

        The function enforces finite values to prevent contamination of the
        entropy calculation.
        """

        latency_value = float(latency)
        if not math.isfinite(latency_value):  # pragma: no cover - safety check
            raise ValueError("latency must be a finite float")

        ts_value = float(timestamp)
        self.timestamps.append(ts_value)
        self.latencies.append(latency_value)

        if len(self.timestamps) > self.capacity:
            self.timestamps.popleft()
            self.latencies.popleft()

    def extend(self, timestamp: float, latencies: Iterable[float]) -> None:
        """Record multiple latency measurements sharing the same timestamp."""

        for latency in latencies:
            self.observe(timestamp, latency)

    def as_array(self) -> np.ndarray:
        """Return the buffered latencies as a NumPy array."""

        if not self.latencies:
            return np.empty(0, dtype=float)
        return np.fromiter(self.latencies, dtype=float, count=len(self.latencies))

    def entropy(self, *, bins: int = 32) -> float:
        """Compute Shannon entropy for the buffered latencies."""

        return measure_entropy(self, bins=bins)


def measure_entropy(buffer: PulseBuffer, *, bins: int = 32) -> float:
    """Estimate Shannon entropy from the latency histogram.

    The default configuration uses 32 bins which offers a balance between
    stability and sensitivity for the latency distributions observed in
    high-frequency trading workloads.  Bin counts are converted into
    probabilities before the logarithm is applied which prevents domain errors
    when the histogram is sparse while preserving a true Shannon entropy
    measure.
    """

    values = buffer.as_array()
    if values.size == 0:
        return 0.0

    counts, _ = np.histogram(values, bins=bins, density=False)
    counts = counts[counts > 0]
    if counts.size == 0:
        return 0.0
    probabilities = counts / counts.sum()
    entropy = -float(np.sum(probabilities * np.log(probabilities)))
    return entropy


def compute_edge_latency(edge_attributes: Mapping[str, float]) -> float:
    """Return the latency contribution for a single graph edge."""

    data_size = float(edge_attributes.get("data_size", 1.0))
    bandwidth = float(edge_attributes.get("bandwidth", 1.0))
    jitter = float(edge_attributes.get("jitter", 0.0))
    bias = float(edge_attributes.get("latency_bias", 0.0))

    latency = data_size / max(bandwidth, MIN_BANDWIDTH)
    latency += jitter + bias
    return latency


def total_latency(graph: nx.Graph) -> float:
    """Aggregate latency across all edges of the graph."""

    return float(
        sum(
            compute_edge_latency(edge_data)
            for _, _, edge_data in graph.edges(data=True)
        )
    )


def compute_potential_energy(
    graph: nx.Graph, *, constant: float = COULOMB_CONSTANT
) -> float:
    """Compute the Coulomb-style potential energy of the graph."""

    potential = 0.0
    for node_u, node_v, edge_data in graph.edges(data=True):
        charge_u = float(graph.nodes[node_u].get("charge", 0.0))
        charge_v = float(graph.nodes[node_v].get("charge", 0.0))
        distance = float(edge_data.get("distance", 1.0))
        distance = max(distance, MIN_DISTANCE)
        potential += constant * charge_u * charge_v / distance
    return float(potential)


def buffer_uncertainty(buffer: PulseBuffer) -> float:
    """Return the standard deviation of buffered latencies."""

    values = buffer.as_array()
    if values.size < 2:
        return 0.0
    return float(np.std(values, ddof=1))


@dataclass(slots=True)
class ThermodynamicSystem:
    """Thermodynamic abstraction over a TradePulse execution graph."""

    graph: nx.Graph = field(default_factory=nx.Graph)
    buffer: PulseBuffer = field(default_factory=PulseBuffer)
    temperature: float = 1.0
    coulomb_constant: float = COULOMB_CONSTANT
    uncertainty_weight: float = 1.0

    def snapshot(self, *, timestamp: float | None = None) -> None:
        """Record the current edge latency distribution into the buffer."""

        if timestamp is None:
            timestamp = time.time()
        latencies = [
            compute_edge_latency(edge_data)
            for _, _, edge_data in self.graph.edges(data=True)
        ]
        self.buffer.extend(timestamp, latencies)

    def internal_energy(self) -> float:
        """Return the internal energy of the system."""

        potential = compute_potential_energy(self.graph, constant=self.coulomb_constant)
        latency_term = total_latency(self.graph)
        uncertainty_term = self.uncertainty_weight * buffer_uncertainty(self.buffer)
        return potential + latency_term + uncertainty_term

    def free_energy(self) -> float:
        """Return Helmholtz free energy (:math:`F = U - TS`)."""

        entropy = self.buffer.entropy()
        return self.internal_energy() - self.temperature * entropy


def gradient_descent_step(
    graph: nx.Graph,
    *,
    learning_rate: float = 0.01,
    constant: float = COULOMB_CONSTANT,
    min_distance: float = MIN_DISTANCE,
) -> None:
    """Adjust edge distances to minimise the Coulomb potential.

    The update rule follows ``distance -= learning_rate * dE/dd`` where ``E`` is
    the pairwise potential energy.  Distances are clamped to ``min_distance`` to
    avoid degeneracy.
    """

    updates: list[tuple[tuple[str, str], float]] = []
    for node_u, node_v, data in graph.edges(data=True):
        charge_u = float(graph.nodes[node_u].get("charge", 0.0))
        charge_v = float(graph.nodes[node_v].get("charge", 0.0))
        distance = float(data.get("distance", 1.0))
        distance = max(distance, min_distance)

        gradient = -constant * charge_u * charge_v / (distance**2)
        updated_distance = max(distance - learning_rate * gradient, min_distance)
        updates.append(((node_u, node_v), updated_distance))

    for (node_u, node_v), distance in updates:
        cast_data = graph.edges[node_u, node_v]  # mutable mapping view
        cast_data["distance"] = distance


__all__ = [
    "COULOMB_CONSTANT",
    "MIN_BANDWIDTH",
    "MIN_DISTANCE",
    "PulseBuffer",
    "ThermodynamicSystem",
    "buffer_uncertainty",
    "compute_edge_latency",
    "compute_potential_energy",
    "gradient_descent_step",
    "measure_entropy",
    "total_latency",
]
