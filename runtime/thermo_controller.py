from __future__ import annotations

import json
import logging
import time
import warnings
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Tuple, get_args

import networkx as nx

from core.energy import (
    BondType,
    bond_free_energy,
    delta_free_energy,
    system_free_energy,
)
from runtime.link_activator import LinkActivator

MONOTONIC_TOLERANCE = 1e-22

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


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelemetrySnapshot:
    """Structured metrics emitted by :class:`ThermoController`."""

    current_F: float
    dF_dt: float
    max_edge_cost: float
    bottleneck_edge: str | None
    topology_id: str
    timestamp: float
    activations: Tuple[Dict[str, object], ...]
    adaptive_epsilon: float | None

    def as_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "current_F": self.current_F,
            "dF_dt": self.dF_dt,
            "max_edge_cost": self.max_edge_cost,
            "topology_id": self.topology_id,
            "timestamp": self.timestamp,
            "adaptive_epsilon": self.adaptive_epsilon,
        }
        if self.bottleneck_edge is not None:
            payload["bottleneck_edge"] = self.bottleneck_edge
        if self.activations:
            payload["activations"] = [dict(entry) for entry in self.activations]
        return payload


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
        candidates = [bond for bond in get_args(BondType) if bond != current_type]

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
    def __init__(
        self,
        graph: nx.DiGraph,
        metrics_exporter: PrometheusMetrics | None = None,
        *,
        baseline_window: int = 10,
        link_activator: LinkActivator | None = None,
        audit_log_path: Path | None = Path("observability/audit/thermo_audit.log"),
    ) -> None:
        self.graph = graph
        self.metrics = metrics_exporter or PrometheusMetrics()
        self.prev_F: float | None = None
        self.prev_t: float | None = None
        self._baseline_window = max(int(baseline_window), 1)
        self._baseline_derivatives: deque[float] = deque(maxlen=self._baseline_window)
        self._adaptive_epsilon: float | None = None
        self._telemetry = TelemetrySnapshot(
            current_F=0.0,
            dF_dt=0.0,
            max_edge_cost=0.0,
            bottleneck_edge=None,
            topology_id="thermo-topology-0",
            timestamp=time.time(),
            activations=tuple(),
            adaptive_epsilon=None,
        )
        self._topology_version = 0
        self._last_activations: Tuple[Dict[str, object], ...] = tuple()
        self._link_activator = link_activator or LinkActivator()
        self._audit_log_path = audit_log_path

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

    def adaptive_epsilon(self) -> float | None:
        return self._adaptive_epsilon

    def telemetry_snapshot(self) -> TelemetrySnapshot:
        return self._telemetry

    def collect_telemetry(self) -> Dict[str, object]:
        return self._telemetry.as_dict()

    def get_current_F(self) -> float:
        return self._telemetry.current_F

    def get_dF_dt(self) -> float:
        return self._telemetry.dF_dt

    def get_bottleneck_cost(self) -> float:
        return self._telemetry.max_edge_cost

    def get_bottleneck_edge(self) -> str | None:
        return self._telemetry.bottleneck_edge

    def get_topology_id(self) -> str:
        return self._telemetry.topology_id

    def _update_baseline(self, derivative: float) -> None:
        self._baseline_derivatives.append(abs(derivative))
        if len(self._baseline_derivatives) == self._baseline_window:
            baseline = fmean(self._baseline_derivatives)
            self._adaptive_epsilon = 0.1 * baseline if baseline > 0 else 1e-12

    def _audit_event(self, event_type: str, payload: Dict[str, object]) -> None:
        payload_with_meta = {
            "event": event_type,
            "timestamp": time.time(),
            **payload,
        }
        logger.warning("ThermoController audit: %s", payload_with_meta)
        if self._audit_log_path is None:
            return

        try:
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload_with_meta) + "\n")
        except OSError:  # pragma: no cover - audit logging should never fail hard
            logger.exception("Failed to persist thermodynamic audit event")

    def _compute_bottleneck(self, snapshot: MetricsSnapshot) -> Tuple[float, str | None]:
        max_cost = 0.0
        edge_name: str | None = None
        for src, dst, data in self.graph.edges(data=True):
            bond_type = data.get("type", "vdw")
            latency = snapshot.latencies.get((src, dst), data.get("latency_norm", 0.5))
            coherence = snapshot.coherency.get((src, dst), data.get("coherency", 0.8))
            cost = bond_free_energy(src, dst, bond_type, latency, coherence)
            if cost > max_cost:
                max_cost = cost
                edge_name = f"{src}→{dst}"
        return max_cost, edge_name

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

        graph_before = self.graph.copy()
        time_now = time.time()

        gradient_descent_step(self.graph, snapshot, lr=0.02)

        final_bonds = {(u, v): data.get("type") for u, v, data in self.graph.edges(data=True)}
        final_energy = system_free_energy(
            final_bonds,
            snapshot.latencies,
            snapshot.coherency,
            snapshot.resource_usage,
            snapshot.entropy,
        )

        if energy_before - final_energy < 1e-10:
            evolved = evolve_bonds(self.graph, snapshot, generations=50)
            self.hot_swap_bonds(evolved)
            final_bonds = {(u, v): data.get("type") for u, v, data in self.graph.edges(data=True)}
            final_energy = system_free_energy(
                final_bonds,
                snapshot.latencies,
                snapshot.coherency,
                snapshot.resource_usage,
                snapshot.entropy,
            )

        prev_energy = self.prev_F
        prev_time = self.prev_t
        rejection_reason: str | None = None

        if prev_energy is not None and prev_time is not None:
            dt = max(time_now - prev_time, 1e-9)
            proposed_dFdt = delta_free_energy(prev_energy, final_energy, dt)
            if final_energy > prev_energy + MONOTONIC_TOLERANCE:
                rejection_reason = "monotonic_violation"
            elif self._adaptive_epsilon is not None and abs(proposed_dFdt) > self._adaptive_epsilon:
                rejection_reason = "stability_gate"

        if rejection_reason is not None:
            self.graph = graph_before
            final_bonds = bonds_now
            final_energy = prev_energy if prev_energy is not None else energy_before
            self._last_activations = tuple()
            self._audit_event(
                rejection_reason,
                {
                    "energy_before": energy_before,
                    "energy_after": final_energy,
                    "previous_energy": prev_energy,
                },
            )
        else:
            changed_edges = [
                (src, dst, final_bonds[(src, dst)])
                for (src, dst), previous_type in bonds_now.items()
                if final_bonds.get((src, dst), previous_type) != previous_type
            ]
            activations: List[Dict[str, object]] = []
            if changed_edges:
                self._topology_version += 1
                for src, dst, bond_type in changed_edges:
                    activations.append(self._link_activator.apply(bond_type, src, dst))
            self._last_activations = tuple(activations)

        if prev_energy is not None and prev_time is not None:
            dt = max(time_now - prev_time, 1e-9)
            dFdt = delta_free_energy(prev_energy, final_energy, dt)
            self.metrics.record("system_dFdt", dFdt)
            self._update_baseline(dFdt)
        else:
            dFdt = 0.0

        self.metrics.record("system_free_energy", final_energy)
        self.prev_F = final_energy
        self.prev_t = time_now

        max_cost, edge_name = self._compute_bottleneck(snapshot)

        self._telemetry = TelemetrySnapshot(
            current_F=final_energy,
            dF_dt=dFdt,
            max_edge_cost=max_cost,
            bottleneck_edge=edge_name,
            topology_id=f"thermo-topology-{self._topology_version}",
            timestamp=time_now,
            activations=self._last_activations,
            adaptive_epsilon=self._adaptive_epsilon,
        )


__all__ = [
    "ThermoController",
    "PrometheusMetrics",
    "estimate_entropy",
    "gradient_descent_step",
    "TelemetrySnapshot",
]
