"""Thermodynamic controller with crisis-aware adaptations."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import networkx as nx
import numpy as np

from evolution import bond_evolver
from core.energy import BondType, delta_free_energy, system_free_energy
from evolution.crisis_ga import CrisisAwareGA, CrisisMode, Topology
from runtime.link_activator import LinkActivator
from runtime.recovery_agent import AdaptiveRecoveryAgent, RecoveryState

try:  # pragma: no cover - optional dependency wrapper retained for compatibility
    from evolution.bond_evolver import MetricsSnapshot as _BondMetricsSnapshot
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name != "deap":
        raise

    @dataclass(slots=True)
    class MetricsSnapshot:  # type: ignore[override]
        latencies: Dict[Tuple[str, str], float]
        coherency: Dict[Tuple[str, str], float]
        resource_usage: float
        entropy: float

else:  # pragma: no cover - exercised in existing suite
    MetricsSnapshot = _BondMetricsSnapshot


@dataclass(slots=True)
class ToleranceCheck:
    """Outcome of a monotonicity check for a proposed topology."""

    accepted: bool
    reason: str


@dataclass(slots=True)
class CrisisComputation:
    """Intermediate crisis handling artefact returned to the control loop."""

    state: RecoveryState
    action: Optional[str]
    new_topology: Optional[Topology]
    proposed_F: float
    tolerance: ToleranceCheck
    latency_spike: float


_FALLBACK_WARNING_EMITTED = False


CRITICAL_HALT_STATE = "CRITICAL_HALT"


def evolve_bonds(
    graph: nx.DiGraph,
    snapshot: MetricsSnapshot,
    generations: int,
    *,
    pop_size: int = 16,
    cx_prob: float = 0.4,
    mut_prob: float = 0.6,
) -> nx.DiGraph:
    """Delegate to the evolutionary optimiser with a deterministic fallback.

    The public thermodynamic API guarantees that callers can evolve bond
    topologies even when the optional :mod:`deap` dependency is unavailable.
    ``evolution.bond_evolver`` already ships a deterministic fallback
    implementation – here we wrap it to emit an explicit ``RuntimeWarning`` so
    operators understand why the stochastic optimiser was not used.
    """

    global _FALLBACK_WARNING_EMITTED

    deap_available = getattr(bond_evolver, "_DEAP_AVAILABLE", False)
    if not deap_available and not _FALLBACK_WARNING_EMITTED:
        warnings.warn(
            "DEAP is not available; using deterministic thermodynamic fallback optimiser.",
            RuntimeWarning,
            stacklevel=2,
        )
        _FALLBACK_WARNING_EMITTED = True

    return bond_evolver.evolve_bonds(
        graph,
        snapshot,
        generations,
        pop_size=pop_size,
        cx_prob=cx_prob,
        mut_prob=mut_prob,
    )


if getattr(bond_evolver, "_DEAP_AVAILABLE", False):
    evolve_bonds.__module__ = bond_evolver.evolve_bonds.__module__


class PrometheusMetrics:
    """Minimal metrics exporter used in unit tests."""

    def record(self, key: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
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
        entropy -= p * math.log(p + 1e-12)

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
    """Thermodynamic control loop with safety guarantees."""

    AUDIT_LOG_PATH = Path("/var/log/tradepulse/thermo_audit.jsonl")

    def __init__(self, graph: nx.DiGraph, metrics_exporter: Optional[PrometheusMetrics] = None) -> None:
        self.graph = graph
        self.metrics = metrics_exporter or PrometheusMetrics()

        self.audit_logger = logging.getLogger("tradepulse.audit")
        self.circuit_breaker_active = False
        self.controller_state: str = CrisisMode.NORMAL
        self._last_tolerance_check: Optional[ToleranceCheck] = None

        self.link_activator = LinkActivator()
        self.recovery_agent = AdaptiveRecoveryAgent()
        self.telemetry_history: List[Dict[str, float | str]] = []

        snapshot = self.snapshot_metrics()
        self._latest_snapshot = snapshot
        self.current_topology = self._graph_to_topology(graph)

        initial_F = self._compute_free_energy(snapshot=snapshot)
        self.baseline_F = initial_F
        self.baseline_ema = initial_F
        self.previous_F = initial_F
        self.previous_t = time.time()
        self.dF_dt = 0.0
        self.epsilon_adaptive = 0.0
        self.crisis_step_count = 0
        self.bottleneck_edge: Optional[str] = None
        self.bottleneck_cost = 0.0
        self._baseline_latency = self._compute_average_latency(snapshot)
        self.unresolved_rise_steps = 0

        self.manual_override_active = False
        self.manual_override_reason = ""

        self.crisis_ga = CrisisAwareGA(
            fitness_func=self._evaluate_topology,
            F_baseline=self.baseline_F,
            crisis_threshold=0.1,
        )

    # Core loop ----------------------------------------------------------
    def control_step(self) -> None:
        snapshot = self.snapshot_metrics()
        self._latest_snapshot = snapshot
        current_time = time.time()

        topology_before_step = list(self.current_topology)
        current_F = self._compute_free_energy(snapshot=snapshot)
        F_before_action = current_F
        if self.previous_F is not None and current_F > self.previous_F:
            self.unresolved_rise_steps += 1
        else:
            self.unresolved_rise_steps = 0

        was_active_before_step = self.circuit_breaker_active
        sustained_rise_triggered = False
        if self.unresolved_rise_steps > 5:
            self.circuit_breaker_active = True
            if not was_active_before_step:
                sustained_rise_triggered = True
                self.audit_logger.critical(
                    "B1 Thermodynamic circuit breaker activated due to sustained free energy rise",
                    extra={
                        "event": "thermo.circuit_breaker",
                        "code": "B1",
                        "state": CRITICAL_HALT_STATE,
                        "rise_steps": self.unresolved_rise_steps,
                        "F_current": f"{current_F:.6f}",
                    },
                )

        if self.previous_F is not None and self.previous_t is not None:
            dt = max(current_time - self.previous_t, 1e-9)
            self.dF_dt = delta_free_energy(self.previous_F, current_F, dt)
        else:  # pragma: no cover - initial iteration
            self.dF_dt = 0.0

        self._update_baseline(current_F)
        self._update_adaptive_epsilon(self.dF_dt)
        self._update_bottleneck(snapshot)

        crisis_mode = CrisisMode.detect(current_F, self.baseline_F, self.crisis_ga.crisis_threshold)
        control_state = CRITICAL_HALT_STATE if self.circuit_breaker_active else crisis_mode
        in_crisis = crisis_mode != CrisisMode.NORMAL or abs(self.dF_dt) > self.epsilon_adaptive

        resulting_F = current_F
        decision_action = "accepted"
        if self.circuit_breaker_active:
            self._last_tolerance_check = None
            if was_active_before_step and not sustained_rise_triggered:
                self.audit_logger.info(
                    "Thermodynamic circuit breaker blocking topology mutation",
                    extra={
                        "event": "thermo.circuit_breaker",
                        "state": CRITICAL_HALT_STATE,
                    },
                )
            decision_action = "rejected"
        elif in_crisis:
            crisis_result = self._handle_crisis(snapshot, current_F, crisis_mode)
            tolerance = crisis_result.tolerance
            self._last_tolerance_check = tolerance

            was_active_before_tolerance = self.circuit_breaker_active
            if not tolerance.accepted:
                self.circuit_breaker_active = True
                control_state = CRITICAL_HALT_STATE
                log_level = logging.ERROR if not was_active_before_tolerance else logging.INFO
                message = (
                    "Thermodynamic circuit breaker activated due to unsafe topology proposal"
                    if not was_active_before_tolerance
                    else "Thermodynamic circuit breaker blocking topology mutation"
                )
                self.audit_logger.log(
                    log_level,
                    message,
                    extra={
                        "event": "thermo.circuit_breaker",
                        "reason": tolerance.reason,
                        "F_old": f"{current_F:.6f}",
                        "F_new": f"{crisis_result.proposed_F:.6f}",
                    },
                )
                decision_action = "rejected"
            else:
                reward = -abs(crisis_result.proposed_F - current_F)
                if (
                    crisis_result.new_topology is not None
                    and self._apply_topology_changes(crisis_result.new_topology)
                ):
                    self.current_topology = self._graph_to_topology(self.graph)
                    resulting_F = crisis_result.proposed_F
                    reward = -(crisis_result.proposed_F - current_F)

                next_state = RecoveryState(
                    F_current=resulting_F,
                    F_baseline=self.baseline_F,
                    latency_spike=self._detect_latency_spike(snapshot),
                    steps_in_crisis=self.crisis_step_count,
                )

                if (
                    not self.circuit_breaker_active
                    and crisis_result.action is not None
                ):
                    self.recovery_agent.update(
                        crisis_result.state,
                        crisis_result.action,
                        reward,
                        next_state,
                    )
                decision_action = "accepted"
            control_state = crisis_mode if not self.circuit_breaker_active else CRITICAL_HALT_STATE
        else:
            self.crisis_step_count = 0
            if not self.circuit_breaker_active and gradient_descent_step(self.graph, snapshot, lr=0.02):
                self.current_topology = self._graph_to_topology(self.graph)
                resulting_F = self._compute_free_energy(snapshot=snapshot)
            control_state = crisis_mode
            decision_action = "rejected" if self.circuit_breaker_active else "accepted"

        current_F = resulting_F

        self.metrics.record("system_free_energy", current_F)
        self.metrics.record("system_dFdt", self.dF_dt)
        self.previous_F = current_F
        self.previous_t = current_time
        self.controller_state = control_state
        topology_changes = self._diff_topologies(topology_before_step, self.current_topology)
        self._record_telemetry(
            F_old=F_before_action,
            F_new=current_F,
            crisis_mode=control_state,
            action=decision_action,
            topology_changes=topology_changes,
        )

    # ------------------------------------------------------------------
    # Backwards compatibility properties
    @property
    def prev_F(self) -> float | None:
        """Alias maintained for scripts expecting the legacy attribute."""

        return self.previous_F

    @prev_F.setter
    def prev_F(self, value: float | None) -> None:
        self.previous_F = value

    @property
    def prev_t(self) -> float | None:
        """Alias maintained for scripts expecting the legacy attribute."""

        return self.previous_t

    @prev_t.setter
    def prev_t(self, value: float | None) -> None:
        self.previous_t = value

    # Crisis handling ----------------------------------------------------
    def _handle_crisis(
        self, snapshot: MetricsSnapshot, current_F: float, crisis_mode: str
    ) -> CrisisComputation:
        self.crisis_step_count += 1
        latency_spike = self._detect_latency_spike(snapshot)
        state = RecoveryState(
            F_current=current_F,
            F_baseline=self.baseline_F,
            latency_spike=latency_spike,
            steps_in_crisis=self.crisis_step_count,
        )

        if self.circuit_breaker_active:
            tolerance = ToleranceCheck(
                accepted=False,
                reason="circuit_breaker_active",
            )
            return CrisisComputation(
                state=state,
                action=None,
                new_topology=None,
                proposed_F=current_F,
                tolerance=tolerance,
                latency_spike=latency_spike,
            )

        action = self.recovery_agent.choose_action(state)
        recovery_params = self.recovery_agent.get_recovery_params(action)
        _ = recovery_params  # Currently used for observability only

        new_topology, new_F, _ = self.crisis_ga.evolve(self.current_topology, current_F)
        tolerance = self._check_monotonic_with_tolerance(current_F, new_F)

        return CrisisComputation(
            state=state,
            action=action,
            new_topology=new_topology,
            proposed_F=new_F,
            tolerance=tolerance,
            latency_spike=latency_spike,
        )

    # Telemetry helpers --------------------------------------------------
    def _record_telemetry(
        self,
        *,
        F_old: float,
        F_new: float,
        crisis_mode: str,
        action: str,
        topology_changes: List[Tuple[str, str, str, str]],
    ) -> None:
        timestamp = time.time()
        topology_change_records = [
            {"src": src, "dst": dst, "old": old_type, "new": new_type}
            for src, dst, old_type, new_type in topology_changes
        ]
        record = {
            "timestamp": timestamp,
            "F": F_new,
            "F_old": F_old,
            "F_new": F_new,
            "dF_dt": self.dF_dt,
            "epsilon": self.epsilon_adaptive,
            "baseline_ema": self.baseline_ema,
            "bottleneck_edge": self.bottleneck_edge or "",
            "bottleneck_cost": self.bottleneck_cost,
            "crisis_mode": crisis_mode,
            "circuit_breaker_active": self.circuit_breaker_active,
            "topology_changes": topology_change_records,
            "manual_override": self.manual_override_active,
            "override_reason": self.manual_override_reason,
            "action": action,
        }
        self.telemetry_history.append(record)

        audit_payload = {
            "ts": timestamp,
            "F_old": F_old,
            "F_new": F_new,
            "dF_dt": self.dF_dt,
            "epsilon": self.epsilon_adaptive,
            "crisis_mode": crisis_mode,
            "circuit_breaker_active": self.circuit_breaker_active,
            "topology_changes": topology_change_records,
            "manual_override": self.manual_override_active,
            "override_reason": self.manual_override_reason,
            "action": action,
        }

        try:
            audit_path = self.AUDIT_LOG_PATH
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(audit_payload, ensure_ascii=False) + "\n")
        except OSError as exc:  # pragma: no cover - filesystem failure
            self.audit_logger.error(
                "Failed to persist thermodynamic audit record",
                extra={
                    "event": "thermo.audit.write_failed",
                    "error": str(exc),
                },
            )

    # Metrics helpers ----------------------------------------------------
    def snapshot_metrics(self) -> MetricsSnapshot:
        latencies: Dict[Tuple[str, str], float] = {}
        coherency: Dict[Tuple[str, str], float] = {}

        for src, dst, data in self.graph.edges(data=True):
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

    def _update_baseline(self, current_F: float) -> None:
        self.baseline_ema = 0.9 * self.baseline_ema + 0.1 * current_F

    def _update_adaptive_epsilon(self, dF_dt: float) -> None:
        self.epsilon_adaptive = max(1e-9, 0.01 * self.baseline_ema + 0.05 * abs(dF_dt))

    def _update_bottleneck(self, snapshot: MetricsSnapshot) -> None:
        if snapshot.latencies:
            (src, dst), value = max(snapshot.latencies.items(), key=lambda item: item[1])
            self.bottleneck_edge = f"{src}->{dst}"
            self.bottleneck_cost = value
        else:
            self.bottleneck_edge = None
            self.bottleneck_cost = 0.0

    def _detect_latency_spike(self, snapshot: MetricsSnapshot) -> float:
        avg_latency = self._compute_average_latency(snapshot)
        if self._baseline_latency == 0:
            return 1.0
        return max(avg_latency / self._baseline_latency, 1.0)

    def _compute_average_latency(self, snapshot: MetricsSnapshot) -> float:
        if not snapshot.latencies:
            return 0.0
        return float(sum(snapshot.latencies.values()) / len(snapshot.latencies))

    # Safety -------------------------------------------------------------
    def _check_monotonic_with_tolerance(
        self, F_old: float, F_new: float, window_size: int = 3
    ) -> ToleranceCheck:
        epsilon_spike = 0.01 * self.baseline_ema
        if F_new > F_old + epsilon_spike:
            return ToleranceCheck(
                accepted=False,
                reason=(
                    "free_energy_spike_exceeds_tolerance("
                    f"F_old={F_old:.6f}, F_new={F_new:.6f}, epsilon={epsilon_spike:.6f})"
                ),
            )
        if F_new > F_old:
            predictions = self._predict_recovery_window(F_new, window_size)
            predicted_mean = float(np.mean(predictions))
            if predicted_mean < F_old:
                return ToleranceCheck(
                    accepted=True,
                    reason="temporary_spike_with_expected_recovery",
                )
            return ToleranceCheck(
                accepted=False,
                reason=(
                    "no_recovery_within_prediction_window("
                    f"predicted_mean={predicted_mean:.6f}, F_old={F_old:.6f})"
                ),
            )
        return ToleranceCheck(
            accepted=True,
            reason="non_increasing_free_energy",
        )

    def _predict_recovery_window(self, F_new: float, window_size: int) -> List[float]:
        decay = 0.9
        return [F_new * (decay ** i) + self.baseline_F * (1 - decay ** i) for i in range(1, window_size + 1)]

    def _apply_topology_changes(self, new_topology: Topology) -> bool:
        changed = self._diff_topologies(self.current_topology, new_topology)
        success = True
        for src, dst, old_type, new_type in changed:
            self.graph.add_edge(src, dst)
            self.graph.edges[(src, dst)]["type"] = new_type
            result = self.link_activator.apply(new_type, src, dst)
            if not result.success:
                self.graph.edges[(src, dst)]["type"] = old_type
                success = False
        return success

    # Data conversion ----------------------------------------------------
    def _graph_to_topology(self, graph: nx.DiGraph) -> Topology:
        return [(src, dst, data.get("type", "vdw")) for src, dst, data in graph.edges(data=True)]

    def _diff_topologies(
        self, old: Iterable[Tuple[str, str, str]], new: Iterable[Tuple[str, str, str]]
    ) -> List[Tuple[str, str, str, str]]:
        old_map = {(src, dst): bond for src, dst, bond in old}
        new_map = {(src, dst): bond for src, dst, bond in new}
        changed: List[Tuple[str, str, str, str]] = []
        for edge, new_type in new_map.items():
            old_type = old_map.get(edge)
            if old_type != new_type:
                changed.append((edge[0], edge[1], old_type or "vdw", new_type))
        return changed

    def _compute_free_energy(
        self,
        topology: Optional[Topology] = None,
        snapshot: Optional[MetricsSnapshot] = None,
    ) -> float:
        snapshot = snapshot or self._latest_snapshot
        topology = topology or self.current_topology
        bonds = {(src, dst): bond for src, dst, bond in topology}
        return system_free_energy(
            bonds,
            snapshot.latencies,
            snapshot.coherency,
            snapshot.resource_usage,
            snapshot.entropy,
        )

    def _evaluate_topology(self, topology: Topology) -> float:
        return self._compute_free_energy(topology=topology, snapshot=self._latest_snapshot)

    # Public getters -----------------------------------------------------
    def get_current_F(self) -> float:
        return float(self.previous_F)

    def get_dF_dt(self) -> float:
        return float(self.dF_dt)

    def get_bottleneck_cost(self) -> float:
        return float(self.bottleneck_cost)

    def get_bottleneck_edge(self) -> Optional[str]:
        return self.bottleneck_edge

    def get_topology_id(self) -> str:
        digest = hashlib.sha1()
        for src, dst, bond in sorted(self.current_topology):
            digest.update(f"{src}->{dst}:{bond}".encode())
        return digest.hexdigest()


__all__ = [
    "evolve_bonds",
    "ThermoController",
    "PrometheusMetrics",
    "estimate_entropy",
    "gradient_descent_step",
    "CRITICAL_HALT_STATE",
]
