"""Synthetic thermodynamic prototype used for empirical validation.

This module mirrors the experimental setup described in the research notes
that accompany the thermodynamic control loop.  It builds a lightweight
limit-order-book inspired processing graph, evaluates its free energy and
performs a single optimisation sweep over the bond types.  The result is a
deterministic artefact that can be executed inside tests to ensure that the
energy model behaves as expected even without access to production data.

The implementation keeps the core model (``core.energy`` and
``runtime.thermo_controller``) as the source of truth.  We avoid duplicating
the physics-inspired equations and instead rely on the public API.  This makes
the prototype resilient to future changes while still giving us a convenient
way to regression-test empirical observations that were previously only
available in standalone notebooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import networkx as nx
import numpy as np

from core.energy import BondType, system_free_energy
from runtime.thermo_controller import estimate_entropy


@dataclass(frozen=True)
class PrototypeResult:
    """Container for the outcome of the synthetic optimisation run."""

    initial_free_energy: float
    optimised_free_energy: float
    delta_free_energy: float
    derivative: float
    energy_trace: List[float]
    stable: bool

    def as_dict(self) -> Dict[str, float | List[float] | bool]:
        """Return a JSON-serialisable representation of the result."""

        return {
            "initial_free_energy": self.initial_free_energy,
            "optimised_free_energy": self.optimised_free_energy,
            "delta_free_energy": self.delta_free_energy,
            "derivative": self.derivative,
            "energy_trace": self.energy_trace,
            "stable": self.stable,
        }


def _default_nodes() -> Iterable[Tuple[str, Dict[str, float]]]:
    # CPU normalisation roughly matches the empirical setup from the notes.
    return (
        ("PulseGen", {"cpu_norm": 0.45}),
        ("Analyzer", {"cpu_norm": 0.51}),
        ("Trader", {"cpu_norm": 0.62}),
        ("RiskMgr", {"cpu_norm": 0.56}),
        ("Logger", {"cpu_norm": 0.33}),
    )


def _edge_layout() -> List[Tuple[str, str]]:
    # Ten directed edges to emulate a dense pulse-processing fabric.
    return [
        ("PulseGen", "Analyzer"),
        ("Analyzer", "Trader"),
        ("Trader", "RiskMgr"),
        ("RiskMgr", "Logger"),
        ("Logger", "PulseGen"),
        ("Analyzer", "RiskMgr"),
        ("PulseGen", "Trader"),
        ("Trader", "Logger"),
        ("RiskMgr", "PulseGen"),
        ("Logger", "Analyzer"),
    ]


def _build_graph(seed: int) -> nx.DiGraph:
    rng = np.random.default_rng(seed)
    graph = nx.DiGraph()
    graph.add_nodes_from(_default_nodes())

    bond_types = list(BondType.__args__)

    for src, dst in _edge_layout():
        graph.add_edge(
            src,
            dst,
            type=str(rng.choice(bond_types)),
            latency_norm=float(rng.uniform(0.2, 1.1)),
            coherency=float(rng.uniform(0.8, 1.0)),
        )

    return graph


def _snapshot_metrics(graph: nx.DiGraph) -> Tuple[
    Dict[Tuple[str, str], float],
    Dict[Tuple[str, str], float],
    float,
    float,
]:
    latencies: Dict[Tuple[str, str], float] = {}
    coherency: Dict[Tuple[str, str], float] = {}

    for src, dst, data in graph.edges(data=True):
        latencies[(src, dst)] = float(data.get("latency_norm", 0.5))
        coherency[(src, dst)] = float(data.get("coherency", 0.8))

    resource_usage = 0.0
    for _, node_data in graph.nodes(data=True):
        resource_usage += float(node_data.get("cpu_norm", 0.2))
    resource_usage /= max(graph.number_of_nodes(), 1)

    entropy = estimate_entropy(graph)

    return latencies, coherency, resource_usage, entropy


def _free_energy(graph: nx.DiGraph) -> float:
    latencies, coherency, resource_usage, entropy = _snapshot_metrics(graph)
    bonds = {(u, v): data.get("type", "vdw") for u, v, data in graph.edges(data=True)}
    return system_free_energy(
        bonds=bonds,
        latencies=latencies,
        coherency=coherency,
        resource_usage=resource_usage,
        entropy=entropy,
    )


def _optimise(graph: nx.DiGraph) -> Tuple[nx.DiGraph, float]:
    baseline_energy = _free_energy(graph)
    best_energy = baseline_energy
    best_graph = graph.copy()
    improvement_threshold = max(abs(baseline_energy) * 1e-6, 1e-24)

    for src, dst, data in graph.edges(data=True):
        current_type = data.get("type", "vdw")
        for candidate in BondType.__args__:
            if candidate == current_type:
                continue

            trial_graph = graph.copy()
            trial_graph.edges[(src, dst)]["type"] = candidate
            trial_energy = _free_energy(trial_graph)

            if trial_energy < best_energy - improvement_threshold:
                best_energy = trial_energy
                best_graph = trial_graph

    return best_graph, best_energy


def run_prototype(
    seed: int = 42,
    dt_seconds: float = 1e-3,
    stability_threshold: float = 1e-12,
) -> PrototypeResult:
    """Execute the synthetic optimisation experiment.

    Parameters
    ----------
    seed:
        RNG seed that guarantees deterministic graphs and therefore stable
        regression outputs across runs.
    dt_seconds:
        Artificial timestep used to emulate controller cadence when computing
        the derivative ``dF/dt``.
    stability_threshold:
        Absolute bound on ``|dF/dt|`` that marks the system as dynamically
        stable.  The default mirrors the experimental write-up (``1e-12``).
    """

    graph = _build_graph(seed)

    initial_energy = _free_energy(graph)
    optimised_graph, optimised_energy = _optimise(graph)

    delta = optimised_energy - initial_energy
    derivative = delta / dt_seconds if dt_seconds > 0 else 0.0
    energy_trace = [initial_energy, optimised_energy]
    stable = abs(derivative) < stability_threshold

    return PrototypeResult(
        initial_free_energy=initial_energy,
        optimised_free_energy=optimised_energy,
        delta_free_energy=delta,
        derivative=derivative,
        energy_trace=energy_trace,
        stable=stable,
    )


__all__ = ["run_prototype", "PrototypeResult"]

