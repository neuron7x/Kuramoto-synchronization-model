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
from typing import Dict, Iterable, List, Tuple, Union

import networkx as nx
import numpy as np

from core.energy import system_free_energy
from evolution.crisis_ga import CrisisMode
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

    def as_dict(self) -> Dict[str, Union[float, List[float], bool]]:
        """Return a JSON-serialisable representation of the result."""

        return {
            "initial_free_energy": self.initial_free_energy,
            "optimised_free_energy": self.optimised_free_energy,
            "delta_free_energy": self.delta_free_energy,
            "derivative": self.derivative,
            "energy_trace": self.energy_trace,
            "stable": self.stable,
        }


@dataclass(frozen=True)
class BacktestResult:
    """Container for crisis backtest validation outcomes."""

    accuracy: float
    precision: float
    recall: float
    f1_score: float
    crisis_labels: List[str]
    predicted_labels: List[str]
    free_energies: List[float]
    entropy_values: List[float]
    latency_means: List[float]
    false_positive_rate: float
    false_negative_rate: float

    def as_dict(self) -> Dict[str, Union[float, List[float], List[str]]]:
        """Return a JSON-serialisable representation of the backtest result."""

        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "crisis_labels": self.crisis_labels,
            "predicted_labels": self.predicted_labels,
            "free_energies": self.free_energies,
            "entropy_values": self.entropy_values,
            "latency_means": self.latency_means,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
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

    # Explicit bond types list for compatibility across Python versions
    bond_types = ["covalent", "ionic", "metallic", "vdw", "hydrogen"]

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

    # Explicit bond types list for compatibility across Python versions
    bond_types = ["covalent", "ionic", "metallic", "vdw", "hydrogen"]

    for src, dst, data in graph.edges(data=True):
        current_type = data.get("type", "vdw")
        for candidate in bond_types:
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


def run_backtest_on_synthetic_crises(
    seed: int = 42,
    num_scenarios: int = 50,
    crisis_threshold: float = 0.1,
) -> BacktestResult:
    """Execute synthetic crisis validation backtest.

    Synthesizes topologies with varying entropy and latency characteristics,
    simulates crisis conditions, and evaluates ML crisis prediction performance.
    This function provides falsifiability validation for the crisis detection
    system by testing it against controlled synthetic data.

    Parameters
    ----------
    seed:
        RNG seed for reproducible synthetic data generation.
    num_scenarios:
        Number of synthetic scenarios to generate and evaluate.
        Half will be crisis scenarios, half will be normal scenarios.
    crisis_threshold:
        Deviation threshold (as fraction of baseline) to classify as crisis.

    Returns
    -------
    BacktestResult containing accuracy, precision, recall, F1 score, and
    detailed statistics for falsifiability analysis.
    """

    rng = np.random.default_rng(seed)

    # Generate baseline scenario
    baseline_graph = _build_graph(seed)
    baseline_energy = _free_energy(baseline_graph)

    crisis_labels: List[str] = []
    predicted_labels: List[str] = []
    free_energies: List[float] = []
    entropy_values: List[float] = []
    latency_means: List[float] = []

    # Generate half crisis scenarios and half normal scenarios
    num_crisis = num_scenarios // 2
    num_normal = num_scenarios - num_crisis

    # Generate crisis scenarios (high entropy > 2.0, elevated latency > 1.5σ)
    for i in range(num_crisis):
        graph = _build_graph(seed + i + 1000)

        # Inject crisis conditions: high entropy and elevated latency
        for src, dst, data in graph.edges(data=True):
            # Elevate latency to > 1.5 standard deviations (base is ~0.65, std ~0.3)
            # 1.5σ above mean ≈ 0.65 + 1.5 * 0.3 = 1.1
            data["latency_norm"] = float(rng.uniform(1.1, 2.5))

        # Increase entropy by diversifying bond types
        bond_types = ["covalent", "ionic", "metallic", "vdw", "hydrogen"]
        for src, dst, data in graph.edges(data=True):
            data["type"] = str(rng.choice(bond_types))

        entropy = estimate_entropy(graph)
        latencies, coherency, resource_usage, _ = _snapshot_metrics(graph)
        F = system_free_energy(
            bonds={(u, v): d.get("type", "vdw") for u, v, d in graph.edges(data=True)},
            latencies=latencies,
            coherency=coherency,
            resource_usage=resource_usage,
            entropy=entropy,
        )

        # Compute predicted crisis mode
        predicted_mode = CrisisMode.detect(F, baseline_energy, crisis_threshold)

        crisis_labels.append(CrisisMode.ELEVATED)  # Ground truth
        predicted_labels.append(predicted_mode)
        free_energies.append(F)
        entropy_values.append(entropy)
        latency_means.append(float(np.mean(list(latencies.values()))))

    # Generate normal scenarios (low entropy, normal latency)
    for i in range(num_normal):
        graph = _build_graph(seed + i + 2000)

        # Keep latency in normal range (< 1.0)
        for src, dst, data in graph.edges(data=True):
            data["latency_norm"] = float(rng.uniform(0.2, 0.9))

        # Keep entropy low by using fewer bond types
        for src, dst, data in graph.edges(data=True):
            # Use primarily vdw and metallic (low energy bonds)
            data["type"] = str(rng.choice(["vdw", "metallic"]))

        entropy = estimate_entropy(graph)
        latencies, coherency, resource_usage, _ = _snapshot_metrics(graph)
        F = system_free_energy(
            bonds={(u, v): d.get("type", "vdw") for u, v, d in graph.edges(data=True)},
            latencies=latencies,
            coherency=coherency,
            resource_usage=resource_usage,
            entropy=entropy,
        )

        # Compute predicted crisis mode
        predicted_mode = CrisisMode.detect(F, baseline_energy, crisis_threshold)

        crisis_labels.append(CrisisMode.NORMAL)  # Ground truth
        predicted_labels.append(predicted_mode)
        free_energies.append(F)
        entropy_values.append(entropy)
        latency_means.append(float(np.mean(list(latencies.values()))))

    # Calculate performance metrics
    true_positives = sum(
        1
        for true, pred in zip(crisis_labels, predicted_labels)
        if true != CrisisMode.NORMAL and pred != CrisisMode.NORMAL
    )
    false_positives = sum(
        1
        for true, pred in zip(crisis_labels, predicted_labels)
        if true == CrisisMode.NORMAL and pred != CrisisMode.NORMAL
    )
    true_negatives = sum(
        1
        for true, pred in zip(crisis_labels, predicted_labels)
        if true == CrisisMode.NORMAL and pred == CrisisMode.NORMAL
    )
    false_negatives = sum(
        1
        for true, pred in zip(crisis_labels, predicted_labels)
        if true != CrisisMode.NORMAL and pred == CrisisMode.NORMAL
    )

    total = len(crisis_labels)
    accuracy = (true_positives + true_negatives) / total if total > 0 else 0.0

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )
    f1_score = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    false_positive_rate = (
        false_positives / (false_positives + true_negatives)
        if (false_positives + true_negatives) > 0
        else 0.0
    )
    false_negative_rate = (
        false_negatives / (false_negatives + true_positives)
        if (false_negatives + true_positives) > 0
        else 0.0
    )

    return BacktestResult(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        crisis_labels=crisis_labels,
        predicted_labels=predicted_labels,
        free_energies=free_energies,
        entropy_values=entropy_values,
        latency_means=latency_means,
        false_positive_rate=false_positive_rate,
        false_negative_rate=false_negative_rate,
    )


__all__ = [
    "run_prototype",
    "PrototypeResult",
    "run_backtest_on_synthetic_crises",
    "BacktestResult",
]
