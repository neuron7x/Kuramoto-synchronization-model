"""Thermodynamic controller with crisis-aware adaptations."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import warnings
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    Callable,
    cast,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

import networkx as nx
import numpy as np
import pandas as pd
import yaml

from core.energy import (
    ENERGY_SCALE,
    BondType,
    bond_internal_energy,
    delta_free_energy,
    system_free_energy,
)
from core.indicators.multiscale_kuramoto import fractal_gcl_novelty, multiscale_kuramoto
from core.metrics.aperiodic import aperiodic_slope
from core.metrics.dfa import dfa_alpha
from evolution import bond_evolver
from evolution.crisis_ga import CrisisAwareGA, CrisisMode, Topology
from rl.replay.sleep_engine import SleepReplayEngine
from runtime.behavior_contract import (
    ActionClass,
    get_current_state,
    tacl_gate,
)
from runtime.cns_stabilizer import CNSStabilizer
from runtime.drift_monitor import DriftDetector, DriftStatus
from runtime.dual_approval import DualApprovalManager
from runtime.filters.vlpo_core_filter import VLPOCoreFilter
from runtime.kill_switch import is_kill_switch_active
from runtime.link_activator import LinkActivator
from runtime.recovery_agent import AdaptiveRecoveryAgent, RecoveryState
from utils.change_point import cusum_score, vol_shock
from utils.fractal_cascade import DyadicPMCascade, pink_noise

torch: ModuleType | None = None
try:
    import torch as _torch
except ImportError:  # pragma: no cover - optional dependency
    pass
else:
    torch = cast(ModuleType, _torch)

try:  # pragma: no cover - optional dependency wrapper retained for compatibility
    from evolution.bond_evolver import MetricsSnapshot as _BondMetricsSnapshot
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name != "deap":
        raise

    @dataclass(slots=True)
    class MetricsSnapshot:
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


_BOND_TYPES: Tuple[str, ...] = tuple(getattr(BondType, "__args__", ())) or (
    "covalent",
    "ionic",
    "metallic",
    "vdw",
    "hydrogen",
)


@runtime_checkable
class SupportsThermoFeedback(Protocol):
    """Protocol describing the risk controls exposed by trading agents."""

    target_coverage: float
    cvar_floor: float

    def apply_thermo_feedback(
        self,
        *,
        latency_ratio: float,
        coherency: float,
        tail_risk: float,
        coverage_shortfall: float,
    ) -> None:
        """Update internal risk budgets using thermodynamic feedback."""


@dataclass(slots=True)
class _AgentBinding:
    agent: SupportsThermoFeedback
    metrics: Deque[Dict[str, float]]
    drift_detector: DriftDetector
    latest_drift: Optional[DriftStatus] = None


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

    def record(
        self, key: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        print(f"[metric] {key}={value} {labels or {}}")


class _NoopMetric:
    """Fallback metric collector used when prometheus_client is unavailable."""

    def labels(self, **_: Any) -> "_NoopMetric":
        return self

    def inc(self, amount: float = 1.0) -> None:
        _ = amount

    def set(self, value: float) -> None:
        _ = value

    def observe(self, value: float) -> None:
        _ = value


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


def gradient_descent_step(
    graph: nx.DiGraph, snap: MetricsSnapshot, lr: float = 0.02
) -> bool:
    bonds = {(u, v): data.get("type", "vdw") for u, v, data in graph.edges(data=True)}
    base_energy = system_free_energy(
        bonds,
        snap.latencies,
        snap.coherency,
        snap.resource_usage,
        snap.entropy,
    )

    bond_contributions: Dict[Tuple[str, str], float] = {}
    total_bond_energy = 0.0
    for (src, dst), kind in bonds.items():
        contribution = ENERGY_SCALE * bond_internal_energy(
            src,
            dst,
            kind,
            snap.latencies,
            snap.coherency,
        )
        bond_contributions[(src, dst)] = contribution
        total_bond_energy += contribution

    non_bond_component = base_energy - total_bond_energy

    improved = False
    scale_reference = max(abs(base_energy), ENERGY_SCALE)
    improvement_threshold = scale_reference * 1e-6

    for src, dst in list(graph.edges()):
        current_type = bonds.get((src, dst))
        if current_type is None:
            continue

        base_contribution = bond_contributions.get((src, dst), 0.0)
        best_type = current_type
        best_energy = base_energy
        best_contribution = base_contribution

        for candidate in _BOND_TYPES:
            if candidate == current_type:
                continue

            candidate_contribution = ENERGY_SCALE * bond_internal_energy(
                src,
                dst,
                candidate,
                snap.latencies,
                snap.coherency,
            )
            candidate_energy = (
                non_bond_component
                + total_bond_energy
                - base_contribution
                + candidate_contribution
            )

            if candidate_energy < best_energy - improvement_threshold:
                best_energy = candidate_energy
                best_type = candidate
                best_contribution = candidate_contribution

        if best_type != current_type:
            graph.edges[(src, dst)]["type"] = best_type
            bonds[(src, dst)] = best_type
            total_bond_energy = (
                total_bond_energy - base_contribution + best_contribution
            )
            bond_contributions[(src, dst)] = best_contribution
            base_energy = best_energy
            non_bond_component = base_energy - total_bond_energy
            improved = True

    return improved


class ThermoController:
    """Thermodynamic control loop with safety guarantees."""

    AUDIT_LOG_PATH = Path(
        os.environ.get(
            "THERMO_AUDIT_LOG_PATH", "/var/log/tradepulse/thermo_audit.jsonl"
        )
    )

    def __init__(
        self, graph: nx.DiGraph, metrics_exporter: Optional[PrometheusMetrics] = None
    ) -> None:
        self.graph = graph
        self.metrics = metrics_exporter or PrometheusMetrics()

        self.audit_logger = logging.getLogger("tradepulse.audit")
        self.circuit_breaker_active = False
        self.controller_state: str = CrisisMode.NORMAL
        self._last_tolerance_check: Optional[ToleranceCheck] = None
        self.monotonic_violations_total = 0

        self.link_activator = LinkActivator()
        self.recovery_agent = AdaptiveRecoveryAgent()
        self.vlpo_filter = VLPOCoreFilter()
        self.dual_approval = DualApprovalManager()
        self._dual_approval_token = os.getenv("THERMO_DUAL_TOKEN", "")
        self.telemetry_history: List[Dict[str, float | str]] = []
        self._agent_bindings: Dict[str, _AgentBinding] = {}
        self.drift_history: List[Dict[str, Any]] = []

        self.stabilizer = CNSStabilizer(normalize="logret", hybrid_mode=True)
        self.stabilizer.start_circadian()
        self._init_homeostasis_metrics()
        self._last_stabilizer_event: Optional[Dict[str, Any]] = None

        self.override_reason: Optional[str] = None
        self.override_time: Optional[float] = None

        snapshot = self.snapshot_metrics(ga_phase="init")
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

    def bind_agent(
        self,
        name: str,
        agent: SupportsThermoFeedback,
        *,
        window: int = 64,
    ) -> Callable[[Dict[str, float]], None]:
        """Register an agent and return a telemetry hook for runtime metrics."""

        if not isinstance(
            agent, SupportsThermoFeedback
        ):  # pragma: no cover - defensive
            raise TypeError("agent must implement SupportsThermoFeedback")
        if name in self._agent_bindings:
            raise ValueError(f"agent '{name}' is already registered")

        binding = _AgentBinding(
            agent=agent,
            metrics=deque(maxlen=max(1, window)),
            drift_detector=DriftDetector(),
        )
        self._agent_bindings[name] = binding

        def _hook(metrics: Dict[str, float]) -> None:
            clean: Dict[str, float] = {}
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    clean[key] = float(value)
            if clean:
                binding.metrics.append(clean)
                drift_status = binding.drift_detector.update(clean)
                if drift_status is not None:
                    binding.latest_drift = drift_status
                    self.metrics.record(
                        "agent_drift_score",
                        drift_status.score,
                        labels={"agent": name},
                    )
                    if drift_status.drifted:
                        self.metrics.record(
                            "agent_drift_detected",
                            1.0,
                            labels={"agent": name},
                        )
                        self.drift_history.append(
                            {
                                "timestamp": drift_status.timestamp,
                                "agent": name,
                                "score": drift_status.score,
                                "metrics": dict(drift_status.metric_scores),
                                "threshold": drift_status.threshold,
                            }
                        )

        return _hook

    def broadcast_agent_feedback(self, snapshot: MetricsSnapshot) -> None:
        """Push thermodynamic feedback to all registered agents."""

        if not self._agent_bindings:
            return

        latency_ratio = self._detect_latency_spike(snapshot)
        if snapshot.coherency:
            coherency = float(
                sum(snapshot.coherency.values()) / len(snapshot.coherency)
            )
        else:
            coherency = 0.0

        for binding in self._agent_bindings.values():
            if not binding.metrics:
                binding.agent.apply_thermo_feedback(
                    latency_ratio=latency_ratio,
                    coherency=coherency,
                    tail_risk=0.0,
                    coverage_shortfall=0.0,
                )
                continue

            metrics_list = list(binding.metrics)
            cvar_values = [
                float(m.get("cvar_hat", 0.0)) for m in metrics_list if "cvar_hat" in m
            ]
            if cvar_values:
                avg_cvar = float(np.mean(cvar_values))
                tail_risk = max(0.0, binding.agent.cvar_floor - avg_cvar)
            else:
                tail_risk = 0.0

            coverage_values = [
                float(m.get("coverage", 1.0)) for m in metrics_list if "coverage" in m
            ]
            if coverage_values:
                recent = coverage_values[-3:]
                coverage_shortfall = max(
                    0.0, binding.agent.target_coverage - float(np.mean(recent))
                )
            else:
                coverage_shortfall = 0.0

            ood_values = [
                float(m.get("ood_score", 0.0)) for m in metrics_list if "ood_score" in m
            ]
            if ood_values:
                tail_risk += max(0.0, float(np.mean(ood_values)) - 0.2) * 0.1

            binding.agent.apply_thermo_feedback(
                latency_ratio=latency_ratio,
                coherency=coherency,
                tail_risk=tail_risk,
                coverage_shortfall=coverage_shortfall,
            )

    def _init_homeostasis_metrics(self) -> None:
        try:
            from prometheus_client import REGISTRY, Counter, Gauge, Histogram
        except Exception:  # pragma: no cover - optional dependency not installed
            noop = _NoopMetric()
            self.integrity_ratio = noop
            self.phase_counter = noop
            self.veto_events = noop
            self.delta_f_hist = noop
            return

        def _create(
            factory: Any, name: str, documentation: str, labelnames: Iterable[str] = ()
        ) -> Any:
            labels_tuple = tuple(labelnames)
            try:
                return factory(name, documentation, labelnames=labels_tuple)
            except ValueError:
                existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
                if existing is not None:
                    return existing
                return factory(
                    name, documentation, labelnames=labels_tuple, registry=None
                )

        self.integrity_ratio = _create(
            Gauge,
            "homeostasis_integrity_ratio",
            "ΔF margin / threshold ratio (CNSStabilizer v2.1)",
        )
        self.phase_counter = _create(
            Counter,
            "stabilizer_phase_total",
            "Phases annotated by CNSStabilizer",
            ("phase",),
        )
        self.veto_events = _create(
            Counter,
            "stabilizer_veto_events_total",
            "Hard veto decisions from CNSStabilizer",
            ("type",),
        )
        self.delta_f_hist = _create(
            Histogram,
            "tacl_delta_f",
            "Observed ΔF after Kalman/PID/micro-recovery",
        )

    def _record_homeostasis_metrics(self, event: Optional[Dict[str, Any]]) -> None:
        if not event:
            return
        data = event.get("data", {}) if isinstance(event, dict) else {}
        phase = str(data.get("phase", "unknown"))
        try:
            ratio = float(self.stabilizer.get_integrity_ratio())
        except (TypeError, ValueError):  # pragma: no cover - defensive
            ratio = 0.0
        self.integrity_ratio.set(ratio)
        self.phase_counter.labels(phase=phase).inc()

        if data.get("action") == "veto":
            veto_type = str(data.get("type", "unknown"))
            self.veto_events.labels(type=veto_type).inc()

        delta_f_value = data.get("delta_f")
        if isinstance(delta_f_value, (int, float)):
            self.delta_f_hist.observe(float(delta_f_value))

    def _apply_stabilizer(self, df: pd.DataFrame, ga_phase: str) -> pd.DataFrame:
        if df.empty or "coherency" not in df:
            return df

        raw_signals = df["coherency"].to_numpy(dtype=float).tolist()
        filtered_signals = self.stabilizer.process_signals_sync(
            raw_signals, ga_phase=ga_phase
        )
        eventlog = self.stabilizer.get_eventlog()
        self._last_stabilizer_event = eventlog[-1] if eventlog else None

        if self.stabilizer.get_system_mode() == "PoR":
            self.stabilizer.notify_external_block(
                ga_phase=ga_phase, reason="system_mode_PoR"
            )
            eventlog = self.stabilizer.get_eventlog()
            self._last_stabilizer_event = eventlog[-1] if eventlog else None
            self._record_homeostasis_metrics(self._last_stabilizer_event)
            blocked_df = df.copy()
            blocked_df["coherency"] = 0.0
            return blocked_df

        if getattr(self, "crisis_ga", None) is not None:
            ga_feedback = self.stabilizer.get_ga_fitness_feedback()
            self.crisis_ga.apply_homeostasis_feedback(ga_feedback)

        self._record_homeostasis_metrics(self._last_stabilizer_event)

        ratio = self.stabilizer.get_integrity_ratio()
        should_export = ratio < 0.8 or (self.stabilizer.epoch % 10 == 0)
        if should_export:
            try:
                self.stabilizer.export_heatmap("/var/log/tacl/delta_f_heatmap.csv")
            except OSError:  # pragma: no cover - path may be missing in tests
                pass

        stabilised_df = df.copy()
        if not filtered_signals:
            stabilised_df["coherency"] = 0.0
            return stabilised_df

        filtered_array = np.asarray(filtered_signals, dtype=float)
        if len(filtered_array) != len(stabilised_df):
            indices = np.linspace(0, len(filtered_array) - 1, num=len(stabilised_df))
            filtered_array = np.interp(
                indices, np.arange(len(filtered_array)), filtered_array
            )
        stabilised_df["coherency"] = filtered_array
        return stabilised_df

    def _handle_stabilizer_veto(
        self, snapshot: MetricsSnapshot, event: Dict[str, Any]
    ) -> None:
        current_F = self._compute_free_energy(snapshot=snapshot)
        phase = str(event.get("data", {}).get("phase", "unknown"))
        integrity = float(event.get("data", {}).get("integrity", 0.0))
        veto_type = str(event.get("data", {}).get("type", "unknown"))

        self.audit_logger.warning(
            "CNS stabiliser vetoed signal chunk",
            extra={
                "event": "thermo.cns.veto",
                "phase": phase,
                "veto_type": veto_type,
                "integrity": f"{integrity:.3f}",
            },
        )

        self.metrics.record("system_free_energy", current_F)
        self.metrics.record("system_dFdt", self.dF_dt)
        self.previous_F = current_F
        self.previous_t = time.time()

        self._record_telemetry(
            F_old=current_F,
            F_new=current_F,
            crisis_mode=self.controller_state,
            action="cns_veto",
            topology_changes=[],
        )

    def control_step(self) -> None:
        if is_kill_switch_active():
            current_F = float(self.previous_F)
            self.circuit_breaker_active = True
            self.controller_state = CRITICAL_HALT_STATE
            self.audit_logger.error(
                "Thermodynamic control loop halted: kill switch active",
                extra={"event": "thermo.kill_switch", "state": CRITICAL_HALT_STATE},
            )
            self._record_telemetry(
                F_old=current_F,
                F_new=current_F,
                crisis_mode=CRITICAL_HALT_STATE,
                action="kill_switch",
                topology_changes=[],
            )
            return

        snapshot = self.snapshot_metrics(ga_phase="pre_evolve")
        self._latest_snapshot = snapshot
        current_time = time.time()

        self.broadcast_agent_feedback(snapshot)

        last_event = self._last_stabilizer_event or {}
        if (
            isinstance(last_event, dict)
            and last_event.get("data", {}).get("action") == "veto"
        ):
            self._handle_stabilizer_veto(snapshot, last_event)
            return

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

        crisis_mode = CrisisMode.detect(
            current_F, self.baseline_F, self.crisis_ga.crisis_threshold
        )
        control_state = (
            CRITICAL_HALT_STATE if self.circuit_breaker_active else crisis_mode
        )
        in_crisis = (
            crisis_mode != CrisisMode.NORMAL or abs(self.dF_dt) > self.epsilon_adaptive
        )

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
                log_level = (
                    logging.ERROR if not was_active_before_tolerance else logging.INFO
                )
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
                action_class = (
                    ActionClass.A2_SYSTEMIC
                    if crisis_result.new_topology is not None
                    else ActionClass.A0_OBSERVATION
                )
                system_state_enum = get_current_state(current_F, self.baseline_F)
                recovery_path = tolerance.reason.startswith("temporary_spike")
                gate_decision = tacl_gate(
                    module_name="thermo_controller",
                    action_class=action_class,
                    system_state=system_state_enum,
                    F_now=current_F,
                    F_next=crisis_result.proposed_F,
                    epsilon=self.epsilon_adaptive,
                    recovery_path=recovery_path,
                    dual_approved=bool(self._dual_approval_token),
                )

                if not gate_decision.allowed:
                    self.circuit_breaker_active = True
                    control_state = CRITICAL_HALT_STATE
                    self.audit_logger.error(
                        "TACL gate denied systemic action",
                        extra={
                            "event": "thermo.circuit_breaker",
                            "reason": gate_decision.reason,
                            "F_old": f"{current_F:.6f}",
                            "F_new": f"{crisis_result.proposed_F:.6f}",
                        },
                    )
                    resulting_F = current_F
                    decision_action = "rejected"
                else:
                    proceed = True
                    if action_class is ActionClass.A2_SYSTEMIC:
                        if not self._dual_approval_token:
                            self.circuit_breaker_active = True
                            control_state = CRITICAL_HALT_STATE
                            self.audit_logger.error(
                                "Dual approval token missing",
                                extra={
                                    "event": "thermo.dual_approval",
                                    "error": "token_missing",
                                },
                            )
                            resulting_F = current_F
                            decision_action = "rejected"
                            proceed = False
                        else:
                            try:
                                self.dual_approval.validate(
                                    action_id="thermo_topology",
                                    token=self._dual_approval_token,
                                )
                            except ValueError as exc:
                                self.circuit_breaker_active = True
                                control_state = CRITICAL_HALT_STATE
                                self.audit_logger.error(
                                    "Dual approval validation failed",
                                    extra={
                                        "event": "thermo.dual_approval",
                                        "error": str(exc),
                                    },
                                )
                                resulting_F = current_F
                                decision_action = "rejected"
                                proceed = False
                            else:
                                self._dual_approval_token = ""

                    if proceed:
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
            control_state = (
                crisis_mode if not self.circuit_breaker_active else CRITICAL_HALT_STATE
            )
        else:
            self.crisis_step_count = 0
            if not self.circuit_breaker_active and gradient_descent_step(
                self.graph, snapshot, lr=0.02
            ):
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
        topology_changes = self._diff_topologies(
            topology_before_step, self.current_topology
        )
        self._record_telemetry(
            F_old=F_before_action,
            F_new=current_F,
            crisis_mode=control_state,
            action=decision_action,
            topology_changes=topology_changes,
        )

    def manual_override(self, reason: str) -> None:
        """Clear circuit breaker state after human validation."""

        previous_state = self.controller_state
        self.circuit_breaker_active = False
        self.unresolved_rise_steps = 0
        self.crisis_step_count = 0
        self._last_tolerance_check = None
        self.override_reason = reason
        self.override_time = time.time()
        self.controller_state = CrisisMode.NORMAL

        self.audit_logger.warning(
            "B1 Thermodynamic circuit breaker manually overridden by operator",
            extra={
                "event": "thermo.circuit_breaker",
                "code": "B1",
                "manual_override": True,
                "reason": reason,
                "state_before": previous_state,
                "override_time": f"{self.override_time:.6f}",
            },
        )

    def set_dual_approval_token(self, token: str) -> None:
        """Inject a dual-approval token for the next systemic action."""

        self._dual_approval_token = token

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
            tolerance = self._record_tolerance_outcome(
                ToleranceCheck(
                    accepted=False,
                    reason="circuit_breaker_active",
                )
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
        tolerance = self._record_tolerance_outcome(
            self._check_monotonic_with_tolerance(current_F, new_F)
        )

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
    def snapshot_metrics(self, ga_phase: str = "pre_evolve") -> MetricsSnapshot:
        edges: List[Tuple[str, str]] = []
        latency_values: List[float] = []
        coherency_values: List[float] = []

        for src, dst, data in self.graph.edges(data=True):
            edges.append((src, dst))
            latency_values.append(float(data.get("latency_norm", 0.5)))
            coherency_values.append(float(data.get("coherency", 0.8)))

        latencies: Dict[Tuple[str, str], float] = {}
        coherency: Dict[Tuple[str, str], float] = {}
        if edges:
            df = pd.DataFrame(
                {"latency": latency_values, "coherency": coherency_values}
            )
            filtered = self.vlpo_filter.filter(df, target_col="coherency")
            filtered = self._apply_stabilizer(filtered, ga_phase)
            for edge, latency, coherence in zip(
                edges,
                filtered["latency"].to_numpy(dtype=float),
                filtered["coherency"].to_numpy(dtype=float),
            ):
                latencies[edge] = float(latency)
                coherency[edge] = float(np.clip(coherence, 0.0, 1.0))

        resource_usage = sum(
            self.graph.nodes[node].get("cpu_norm", 0.1) for node in self.graph.nodes()
        )
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
            (src, dst), value = max(
                snapshot.latencies.items(), key=lambda item: item[1]
            )
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
    def _monotonic_tolerance_budget(self, F_reference: float) -> float:
        """Return the admissible free-energy spike for monotonicity checks.

        Historically the controller used ``0.01 * baseline_ema`` as the
        tolerance.  When the baseline hovered around zero – especially with
        slightly negative free energy – this resulted in a *negative*
        tolerance, meaning even improvements were flagged as regressions.  The
        new formulation clamps the tolerance to a small, positive budget that
        scales with both the historical baseline and the currently evaluated
        free energy.  We also fold in a fraction of the adaptive epsilon so the
        budget grows gracefully during sharp transients.
        """

        baseline_scale = max(abs(self.baseline_ema), abs(F_reference))
        epsilon_from_baseline = 0.01 * baseline_scale
        epsilon_from_dynamics = 0.5 * abs(self.epsilon_adaptive)
        return max(1e-4, epsilon_from_baseline, epsilon_from_dynamics)

    def _check_monotonic_with_tolerance(
        self, F_old: float, F_new: float, window_size: int = 3
    ) -> ToleranceCheck:
        epsilon_spike = self._monotonic_tolerance_budget(F_old)
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

    def _record_tolerance_outcome(self, tolerance: ToleranceCheck) -> ToleranceCheck:
        if not tolerance.accepted:
            self.monotonic_violations_total += 1
            self.metrics.record(
                "monotonic_violations_total",
                float(self.monotonic_violations_total),
            )
        return tolerance

    def _predict_recovery_window(self, F_new: float, window_size: int) -> List[float]:
        decay = 0.9
        return [
            F_new * (decay**i) + self.baseline_F * (1 - decay**i)
            for i in range(1, window_size + 1)
        ]

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
        return [
            (src, dst, data.get("type", "vdw"))
            for src, dst, data in graph.edges(data=True)
        ]

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
        return self._compute_free_energy(
            topology=topology, snapshot=self._latest_snapshot
        )

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
        # Use SHA256 instead of SHA1 for stronger collision resistance (CWE-327)
        digest = hashlib.sha256()
        for src, dst, bond in sorted(self.current_topology):
            digest.update(f"{src}->{dst}:{bond}".encode())
        return digest.hexdigest()

    def get_monotonic_violations_total(self) -> int:
        return int(self.monotonic_violations_total)

    # HPC-AI Integration -------------------------------------------------
    def init_hpc_ai(
        self,
        input_dim: int = 10,
        state_dim: int = 128,
        action_dim: int = 3,
        learning_rate: float = 1e-4,
    ) -> None:
        """
        Initialize HPC-AI module for adaptive trading.

        Args:
            input_dim: Input feature dimension
            state_dim: Latent state dimension
            action_dim: Number of actions (Hold=0, Buy=1, Sell=2)
            learning_rate: Learning rate for optimizer
        """
        if torch is None:
            warnings.warn(
                "PyTorch is not available; HPC-AI features disabled.",
                RuntimeWarning,
            )
            self._hpc_ai_enabled = False
            return

        try:
            from neuropro.hpc_active_inference_v4 import HPCActiveInferenceModuleV4

            self.hpc_ai = HPCActiveInferenceModuleV4(
                input_dim=input_dim,
                state_dim=state_dim,
                action_dim=action_dim,
                learning_rate=learning_rate,
            )
            self.prev_pwpe = 0.0
            self._hpc_ai_enabled = True
        except ImportError as e:
            warnings.warn(
                f"Failed to initialize HPC-AI module: {e}. HPC-AI features disabled.",
                RuntimeWarning,
            )
            self._hpc_ai_enabled = False

    def hpc_ai_control_step(
        self,
        market_data: pd.DataFrame,
        execute_action: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute HPC-AI control step with optional action execution.

        Args:
            market_data: Market data DataFrame with OHLCV
            execute_action: Whether to execute the decided action

        Returns:
            Dictionary with action, td_error, pwpe, and state info
        """
        if torch is None:
            self._hpc_ai_enabled = False
            return {
                "action": 0,
                "td_error": 0.0,
                "pwpe": 0.0,
                "reward": 0.0,
                "state_norm": 0.0,
                "error": "PyTorch not available",
            }

        if not getattr(self, "_hpc_ai_enabled", False):
            return {
                "action": 0,
                "td_error": 0.0,
                "pwpe": 0.0,
                "reward": 0.0,
                "state_norm": 0.0,
                "error": "HPC-AI not initialized",
            }

        # Decide action
        action = self.hpc_ai.decide_action(market_data, self.prev_pwpe)

        # Execute action if requested (placeholder)
        if execute_action:
            if action == 1:
                self.audit_logger.info(
                    "HPC-AI Buy signal",
                    extra={"event": "hpc_ai.action", "action": "buy"},
                )
            elif action == 2:
                self.audit_logger.info(
                    "HPC-AI Sell signal",
                    extra={"event": "hpc_ai.action", "action": "sell"},
                )

        # Compute metrics (mock for now)
        pnl = 0.0
        sharpe = 1.0
        drawdown = 0.0

        expert_metrics = torch.tensor([sharpe, drawdown, pnl], dtype=torch.float32)
        state = self.hpc_ai.afferent_synthesis(market_data)
        pred, pwpe = self.hpc_ai.hpc_forward(state)
        reward = self.hpc_ai.compute_self_reward(expert_metrics, pwpe.item())

        # Simulate next state (use same data for now)
        next_state = state

        # Update with SRDRL
        td_error = self.hpc_ai.sr_drl_step(
            state,
            torch.tensor([action], dtype=torch.int64),
            reward,
            next_state,
            pwpe.item(),
        )

        # Update previous PWPE
        self.prev_pwpe = pwpe.item()

        return {
            "action": action,
            "td_error": td_error,
            "pwpe": pwpe.item(),
            "reward": reward,
            "state_norm": torch.norm(state).item(),
            "error": None,
        }


class FHMC:
    """Fracto-Hypothalamic Meta-Controller."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        root_cfg = cfg["fhmc"] if "fhmc" in cfg else cfg
        self.cfg = root_cfg
        self.state = "WAKE"
        self._alpha_hist: list[float] = []
        self._slope_hist: list[float] = []
        self.cascade = DyadicPMCascade(
            depth=int(root_cfg["mfs"].get("depth", 12)),
            p=float(root_cfg["mfs"].get("p", 0.6)),
            heavy_tail=float(root_cfg["mfs"].get("heavy_tail", 0.5)),
            base_dt=float(root_cfg["mfs"].get("base_dt_seconds", 60.0)),
        )
        self.sleep_engine = SleepReplayEngine(
            dgr_ratio=float(root_cfg["sleep"].get("dgr_ratio", 0.25))
        )
        self._ox = 0.5
        self._th = 0.3

    @classmethod
    def from_yaml(cls, path: str | Path) -> "FHMC":
        with open(path, "r", encoding="utf-8") as stream:
            cfg = yaml.safe_load(stream)
        return cls(cfg)

    def orexin_value(self) -> float:
        return float(self._ox)

    def threat_value(self) -> float:
        return float(self._th)

    def update_biomarkers(
        self,
        action_scalar_series: Iterable[float],
        internal_latents: Iterable[float],
        *,
        fs_latents: int = 50,
    ) -> None:
        actions = list(action_scalar_series)
        if len(actions) >= 500:
            tail = np.asarray(actions[-2000:], dtype=float)
            alpha = dfa_alpha(
                tail, min_win=50, max_win=min(2000, len(tail) // 2), n_win=12
            )
            self._alpha_hist.append(alpha)
            lo, hi = self.cfg["alpha_target"]
            if self.cfg["mfs"].get("adapt_alpha", False):
                if alpha < lo:
                    self.cascade.adjust_heavy_tail(+0.05)
                elif alpha > hi:
                    self.cascade.adjust_heavy_tail(-0.05)

        latents = list(internal_latents)
        window = fs_latents * 10
        if len(latents) >= window:
            tail = np.asarray(latents[-window:], dtype=float)
            slope = aperiodic_slope(tail, fs=float(fs_latents), f_lo=0.5, f_hi=40.0)
            self._slope_hist.append(slope)
            if (
                self.cfg["arousal"].get("slope_gate", False)
                and slope < -1.5
                and self.state == "WAKE"
            ):
                self.state = "SLEEP"

    def compute_orexin(self, exp_return: float, novelty: float, load: float) -> float:
        orexin_cfg = self.cfg["orexin"]
        stimulus = (
            orexin_cfg.get("k1", 1.0) * exp_return
            + orexin_cfg.get("k2", 0.7) * novelty
            + orexin_cfg.get("k3", 0.3) * load
        )
        self._ox = float(1.0 / (1.0 + np.exp(-stimulus)))
        return self._ox

    def compute_threat(self, maxdd: float, volshock: float, cp_score: float) -> float:
        threat_cfg = self.cfg["threat"]
        weighted = (
            threat_cfg.get("w_dd", 0.5) * max(0.0, maxdd)
            + threat_cfg.get("w_vol", 0.3) * max(0.0, volshock)
            + threat_cfg.get("w_cp", 0.2) * max(0.0, cp_score)
        )
        self._th = float(np.tanh(weighted))
        return self._th

    def flipflop_step(self) -> str:
        theta_lo = self.cfg["flipflop"].get("theta_lo", 0.6)
        theta_hi = self.cfg["flipflop"].get("theta_hi", 0.8)
        omega_lo = self.cfg["flipflop"].get("omega_lo", 0.4)
        omega_hi = self.cfg["flipflop"].get("omega_hi", 0.6)
        if self.state == "WAKE":
            if self._th > theta_hi or self._ox < omega_lo:
                self.state = "SLEEP"
        else:
            if self._th < theta_lo and self._ox > omega_hi:
                self.state = "WAKE"
        return self.state

    def next_window_seconds(self) -> float:
        return float(self.cascade.sample(n=1)[0])

    def novelty_from_embeddings(
        self,
        graph: nx.Graph,
        embeddings_i: np.ndarray,
        embeddings_j: np.ndarray,
    ) -> tuple[float, float]:
        return fractal_gcl_novelty(graph, embeddings_i, embeddings_j)

    def threat_markers(self, returns: Iterable[float]) -> tuple[float, float]:
        series = list(returns)
        cp_score = cusum_score(
            series, drift=0.0, threshold=self.cfg["threat"].get("cp_threshold", 5.0)
        )
        vs = vol_shock(series, window=int(self.cfg["threat"].get("vol_window", 60)))
        return vs, cp_score

    def sync_order(self, phases: Iterable[float]) -> float:
        return multiscale_kuramoto(list(phases))

    def sample_colored_noise(self, n: int, beta: float = 1.0) -> np.ndarray:
        return pink_noise(n, beta=beta)


__all__ = [
    "evolve_bonds",
    "ThermoController",
    "PrometheusMetrics",
    "estimate_entropy",
    "gradient_descent_step",
    "CRITICAL_HALT_STATE",
    "FHMC",
]
