from __future__ import annotations

import time
from typing import Dict, Tuple
import warnings
from dataclasses import dataclass

import networkx as nx

from core.energy import BondType, delta_free_energy, system_free_energy
try:
    from evolution.bond_evolver import MetricsSnapshot as _BondMetricsSnapshot
    from evolution.bond_evolver import evolve_bonds as _evolve_bonds
except ModuleNotFoundError as exc:  # pragma: no cover - exercised via dedicated tests
    if exc.name != "deap":
        raise

    _FALLBACK_WARNING_EMITTED = False

    @dataclass(slots=True)
    class MetricsSnapshot:
        latencies: Dict[Tuple[str, str], float]
        coherency: Dict[Tuple[str, str], float]
        resource_usage: float
        entropy: float

    def evolve_bonds(  # type: ignore[override]
        base_graph: nx.DiGraph,
        snap: "MetricsSnapshot",
        generations: int,
        pop_size: int = 16,
        cx_prob: float = 0.4,
        mut_prob: float = 0.6,
    ) -> nx.DiGraph:
        global _FALLBACK_WARNING_EMITTED

        if not _FALLBACK_WARNING_EMITTED:
            warnings.warn(
                "DEAP dependency is missing; bond evolution fallback keeps the graph unchanged.",
                RuntimeWarning,
                stacklevel=2,
            )
            _FALLBACK_WARNING_EMITTED = True

        return base_graph.copy()

else:
    MetricsSnapshot = _BondMetricsSnapshot
    evolve_bonds = _evolve_bonds


class PrometheusMetrics:
    def record(self, key: str, value: float, labels: Dict[str, str] | None = None) -> None:
        print(f"[metric] {key}={value} {labels or {}}")


def estimate_entropy(graph: nx.DiGraph) -> float:
    import math

    counts: Dict[str, int] = {}
    for _, _, data in graph.edges(data=True):
        bond_type = data.get("type", "vdw")
        counts[bond_type] = counts.get(bond_type, 0) + 1

    total = sum(counts.values()) or 1
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy += -p * math.log(p + 1e-12)

    max_entropy = math.log(len(counts) + 1e-12)
    return entropy / max_entropy if max_entropy > 0 else 0.0


def gradient_descent_step(graph: nx.DiGraph, snap: MetricsSnapshot, lr: float = 0.02) -> bool:
    bonds = {(u, v): data.get("type") for u, v, data in graph.edges(data=True)}
    base_energy = system_free_energy(
        bonds,
        snap.latencies,
        snap.coherency,
        snap.resource_usage,
        snap.entropy,
    )

    improved = False
    improvement_threshold = max(lr, 1e-6) * 1e-12

    for (src, dst, data) in list(graph.edges(data=True)):
        current_type = data.get("type")
        candidates = [bond for bond in BondType.__args__ if bond != current_type]

        best_type = current_type
        best_energy = base_energy

        for candidate in candidates:
            graph.edges[(src, dst)]["type"] = candidate
            bonds_tmp = {(u, v): attrs.get("type") for u, v, attrs in graph.edges(data=True)}
            energy = system_free_energy(
                bonds_tmp,
                snap.latencies,
                snap.coherency,
                snap.resource_usage,
                snap.entropy,
            )
            if energy < best_energy - improvement_threshold:
                best_energy = energy
                best_type = candidate

        graph.edges[(src, dst)]["type"] = best_type
        if best_type != current_type:
            improved = True

    return improved


class ThermoController:
    def __init__(self, graph: nx.DiGraph, metrics_exporter: PrometheusMetrics | None = None) -> None:
        self.graph = graph
        self.metrics = metrics_exporter or PrometheusMetrics()
        self.prev_F: float | None = None
        self.prev_t: float | None = None

    def snapshot_metrics(self) -> MetricsSnapshot:
        latencies: Dict[Tuple[str, str], float] = {}
        coherency: Dict[Tuple[str, str], float] = {}

        for (src, dst, data) in self.graph.edges(data=True):
            latencies[(src, dst)] = data.get("latency_norm", 0.5)
            coherency[(src, dst)] = data.get("coherency", 0.8)

        resource_usage = sum(self.graph.nodes[node].get("cpu_norm", 0.1) for node in self.graph.nodes())
        resource_usage /= max(len(self.graph.nodes()), 1)
        entropy = estimate_entropy(self.graph)

        return MetricsSnapshot(
            latencies=latencies,
            coherency=coherency,
            resource_usage=resource_usage,
            entropy=entropy,
        )

    def hot_swap_bonds(self, new_graph: nx.DiGraph | None = None) -> None:
        if new_graph is not None:
            self.graph = new_graph

    def control_step(self) -> None:
        snapshot = self.snapshot_metrics()

        bonds_now = {(u, v): data.get("type") for u, v, data in self.graph.edges(data=True)}
        energy_before = system_free_energy(
            bonds_now,
            snapshot.latencies,
            snapshot.coherency,
            snapshot.resource_usage,
            snapshot.entropy,
        )

        time_now = time.time()

        gradient_descent_step(self.graph, snapshot, lr=0.02)

        bonds_after_local = {(u, v): data.get("type") for u, v, data in self.graph.edges(data=True)}
        energy_after_local = system_free_energy(
            bonds_after_local,
            snapshot.latencies,
            snapshot.coherency,
            snapshot.resource_usage,
            snapshot.entropy,
        )

        final_energy = energy_after_local

        if energy_before - energy_after_local < 1e-10:
            evolved = evolve_bonds(self.graph, snapshot, generations=50)
            self.hot_swap_bonds(evolved)

            bonds_after_evo = {(u, v): data.get("type") for u, v, data in self.graph.edges(data=True)}
            energy_after_evo = system_free_energy(
                bonds_after_evo,
                snapshot.latencies,
                snapshot.coherency,
                snapshot.resource_usage,
                snapshot.entropy,
            )
            final_energy = energy_after_evo

        if self.prev_F is not None and self.prev_t is not None:
            dFdt = delta_free_energy(self.prev_F, final_energy, time_now - self.prev_t)
            self.metrics.record("system_dFdt", dFdt)

        self.metrics.record("system_free_energy", final_energy)
        self.prev_F = final_energy
        self.prev_t = time_now


__all__ = [
    "ThermoController",
    "PrometheusMetrics",
    "estimate_entropy",
    "gradient_descent_step",
]
