# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto-Ricci geometric flow engine.

This module implements a closed geometrodynamic feedback loop where
edge-level Ricci curvature modulates Kuramoto coupling in real time.

Solved system
-------------
For oscillators i=1..N, we integrate

    dθ_i/dt = ω_i + Σ_j K_ij(t) · sin(θ_j - θ_i)

with curvature-modulated coupling

    K_ij(t) = K_base · φ(κ_ij(t))
    φ(κ) = σ · (1 + tanh(ακ)) / 2

Curvature κ_ij is recomputed periodically from a correlation graph derived from
recent oscillator trajectories. Between updates, K_ij is held constant.

Novelty note
------------
Novel coupling — no prior literature combines Kuramoto dynamics with
Ricci-curvature-modulated topology in a closed feedback loop.

This differs from ``KuramotoRicciComposite``: that component fuses two
independent post-hoc indicators, while this engine directly couples geometry to
ODE dynamics.

References
----------
- Sandhu et al. (2016): Ricci curvature as a market stress/crash hallmark.
- Fioriti & Chinnici (2016): Kuramoto synchronization in financial systems.
- Samal et al. (2021): network geometry and instability transitions.
"""

from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .config import KuramotoConfig
from .engine import KuramotoResult, _order_parameter, _rk4_step
from .ricci_flow import (
    NeckpinchEvent,
    RicciFlowConfig,
    ricci_flow_with_surgery,
)

try:  # optional in minimal environments
    from ..indicators.temporal_ricci import LightGraph, OllivierRicciCurvatureLite
except Exception:  # pragma: no cover
    LightGraph = None  # type: ignore[assignment,misc]
    OllivierRicciCurvatureLite = None  # type: ignore[assignment,misc]


class _LocalOllivierRicciCurvatureLite:
    """Fallback lightweight curvature estimator used when temporal module is unavailable.

    Approximation using total variation distance as W1 proxy.
    Exact for complete graphs; upper bound otherwise. See
    Kantorovich-Rubinstein duality.
    """

    def __init__(self, alpha: float = 0.5) -> None:
        self.alpha = float(np.clip(alpha, 0.0, 1.0))  # INV-RC1: Ricci flow step-size alpha ∈ [0,1]

    def _lazy_rw(self, graph: Any, node: int) -> dict[int, float]:
        neighbors = list(graph.neighbors(node))
        if not neighbors:
            return {node: 1.0}
        stay = self.alpha
        step = (1.0 - self.alpha) / len(neighbors)
        out = {node: stay}
        for nbr in neighbors:
            out[int(nbr)] = step
        return out

    def compute_edge_curvature(self, graph: Any, edge: tuple[int, int]) -> float:
        x, y = edge
        mu_x = self._lazy_rw(graph, x)
        mu_y = self._lazy_rw(graph, y)
        keys = set(mu_x) | set(mu_y)
        total_variation = 0.5 * sum(abs(mu_x.get(k, 0.0) - mu_y.get(k, 0.0)) for k in keys)
        d_xy = 1.0 if y in graph.neighbors(x) else float("inf")
        if d_xy <= 0.0 or not np.isfinite(d_xy):
            return 0.0
        return float(1.0 - total_variation / d_xy)


__all__ = [
    "KuramotoRicciFlowEngine",
    "KuramotoRicciFlowResult",
    "KuramotoRicciFlowSurgeryDiagnostics",
]


@dataclass(frozen=True, slots=True)
class KuramotoRicciFlowSurgeryDiagnostics:
    """Auxiliary diagnostics emitted when discrete flow + surgery is enabled.

    Returned alongside :class:`KuramotoRicciFlowResult` via
    :meth:`KuramotoRicciFlowEngine.run_with_surgery`. The default
    :meth:`KuramotoRicciFlowEngine.run` path does not produce this object,
    preserving backward compatibility.
    """

    surgery_event_count: int
    neckpinch_edges: tuple[tuple[int, int], ...]
    events: tuple[NeckpinchEvent, ...]
    total_edge_mass_before: tuple[float, ...]
    total_edge_mass_after: tuple[float, ...]


_logger = logging.getLogger(__name__)


class _SimpleUndirectedGraph:
    """Minimal weighted undirected graph with NetworkX-like surface API."""

    def __init__(self, n: int) -> None:
        self._adj: dict[int, dict[int, float]] = {i: {} for i in range(n)}
        self.graph: dict[str, Any] = {}

    def add_nodes_from(self, nodes: range) -> None:
        for node in nodes:
            self._adj.setdefault(int(node), {})

    def add_edge(self, i: int, j: int, weight: float = 1.0) -> None:
        a, b = int(i), int(j)
        w = float(weight)
        self._adj.setdefault(a, {})
        self._adj.setdefault(b, {})
        self._adj[a][b] = w
        self._adj[b][a] = w

    def neighbors(self, i: int) -> tuple[int, ...]:
        return tuple(self._adj.get(int(i), {}).keys())

    def get_edge_data(
        self, i: int, j: int, default: dict[str, float] | None = None
    ) -> dict[str, float] | None:
        val = self._adj.get(int(i), {}).get(int(j))
        if val is None:
            return default
        return {"weight": val}

    def number_of_nodes(self) -> int:
        return len(self._adj)

    def edges(self, data: bool = False) -> list[Any]:
        out: list[Any] = []
        for i, neighbors in self._adj.items():
            for j, w in neighbors.items():
                if i < j:
                    out.append((i, j, {"weight": w}) if data else (i, j))
        return out

    def nodes(self) -> tuple[int, ...]:
        return tuple(self._adj.keys())

    def shortest_path_length(self, source: int, target: int, weight: str | None = None) -> float:
        if source == target:
            return 0.0
        use_weight = weight is not None
        heap: list[tuple[float, int]] = [(0.0, int(source))]
        distances: dict[int, float] = {int(source): 0.0}
        while heap:
            dist, node = heapq.heappop(heap)
            if node == target:
                return dist
            if dist > distances.get(node, float("inf")):
                continue
            for nbr, edge_weight in self._adj.get(node, {}).items():
                step = edge_weight if use_weight else 1.0
                cand = dist + float(step)
                if cand < distances.get(nbr, float("inf")):
                    distances[nbr] = cand
                    heapq.heappush(heap, (cand, nbr))
        return float("inf")


@dataclass(slots=True)
class KuramotoRicciFlowResult(KuramotoResult):
    """Extended Kuramoto result with curvature/coupling diagnostics."""

    coupling_matrix_history: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros((0, 0, 0), dtype=np.float64)
    )
    curvature_history: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros((0, 0), dtype=np.float64)
    )
    curvature_timestamps: NDArray[np.int64] = field(
        default_factory=lambda: np.zeros(0, dtype=np.int64)
    )
    mean_curvature_trajectory: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(0, dtype=np.float64)
    )
    geometric_phase_transitions: list[int] = field(default_factory=list)
    herding_index: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(0, dtype=np.float64)
    )
    fragility_index: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(0, dtype=np.float64)
    )
    geometric_momentum: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(0, dtype=np.float64)
    )
    coupling_entropy: NDArray[np.float64] = field(
        default_factory=lambda: np.zeros(0, dtype=np.float64)
    )

    def __post_init__(self) -> None:
        KuramotoResult.__post_init__(self)
        n_updates = self.curvature_timestamps.shape[0]
        if self.coupling_matrix_history.ndim != 3:
            raise ValueError("coupling_matrix_history must be rank-3.")
        if self.coupling_matrix_history.shape[:1] not in {(n_updates,), (0,)}:
            raise ValueError(
                "coupling_matrix_history first dimension must match curvature updates."
            )
        if (
            self.coupling_matrix_history.shape[1:] != (self.config.N, self.config.N)
            and n_updates != 0
        ):
            raise ValueError("coupling_matrix_history has invalid matrix shape.")
        if self.mean_curvature_trajectory.shape != (n_updates,):
            raise ValueError("mean_curvature_trajectory length must match curvature updates.")
        for arr_name, arr in (
            ("herding_index", self.herding_index),
            ("fragility_index", self.fragility_index),
            ("geometric_momentum", self.geometric_momentum),
            ("coupling_entropy", self.coupling_entropy),
        ):
            if arr.shape != (n_updates,):
                raise ValueError(f"{arr_name} length must match curvature updates.")
            if not np.isfinite(arr).all():
                raise ValueError(f"{arr_name} contains non-finite values.")


class KuramotoRicciFlowEngine:
    """Kuramoto engine with Ricci-curvature-modulated matrix coupling."""

    def __init__(
        self,
        config: KuramotoConfig,
        *,
        K_base: float | None = None,
        alpha: float = 4.0,
        sigma: float = 2.0,
        ricci_update_interval: int = 50,
        correlation_window: int = 64,
        curvature_method: str = "ollivier",
        graph_threshold: float = 0.2,
        damping: float = 0.3,
        coupling_history_enabled: bool = True,
        enable_discrete_flow: bool = False,
        enable_neckpinch_surgery: bool = False,
        ricci_flow_config: RicciFlowConfig | None = None,
    ) -> None:
        self._cfg = config
        self._omega, self._theta0 = self._resolve_initial_conditions(config)

        self.K_base = float(config.K if K_base is None else K_base)
        self.alpha = float(alpha)
        self.sigma = float(sigma)
        self.ricci_update_interval = int(max(1, ricci_update_interval))
        self.correlation_window = int(max(4, correlation_window))
        self.curvature_method = str(curvature_method).lower()
        self.graph_threshold = float(
            np.clip(graph_threshold, 0.0, 1.0)
        )  # bounds: graph threshold normalized to [0,1]
        self.damping = float(np.clip(damping, 0.0, 1.0))  # bounds: damping coefficient ∈ [0,1]
        self.coupling_history_enabled = bool(coupling_history_enabled)
        # Opt-in research extension flags. Defaults preserve byte-identical behavior.
        self.enable_discrete_flow = bool(enable_discrete_flow)
        self.enable_neckpinch_surgery = bool(enable_neckpinch_surgery)
        self._ricci_flow_config: RicciFlowConfig = (
            ricci_flow_config if ricci_flow_config is not None else RicciFlowConfig()
        )
        self._surgery_events_buffer: list[NeckpinchEvent] = []
        self._surgery_mass_before: list[float] = []
        self._surgery_mass_after: list[float] = []
        if OllivierRicciCurvatureLite is not None:
            self._lite_ricci: Any = OllivierRicciCurvatureLite(alpha=0.5)
        else:
            self._lite_ricci = _LocalOllivierRicciCurvatureLite(alpha=0.5)

        if self.curvature_method not in {"ollivier", "forman"}:
            raise ValueError("curvature_method must be 'ollivier' or 'forman'.")
        if not np.isfinite(self.K_base) or self.K_base < 0.0:
            raise ValueError("K_base must be finite and >= 0.")
        if not np.isfinite(self.alpha):
            raise ValueError("alpha must be finite.")
        if not np.isfinite(self.sigma) or self.sigma <= 0.0:
            raise ValueError("sigma must be finite and > 0.")

        self._K_max = self.K_base * self.sigma

    def run(self) -> KuramotoRicciFlowResult:
        cfg = self._cfg
        n = cfg.N
        steps = cfg.steps
        dt = cfg.dt

        phases = np.empty((steps + 1, n), dtype=np.float64)
        order = np.empty(steps + 1, dtype=np.float64)
        time_arr = np.arange(steps + 1, dtype=np.float64) * dt

        coupling = self._baseline_coupling(n)
        theta = self._theta0.copy()

        phases[0] = theta
        order[0] = _order_parameter(theta)

        corr_buffer: list[NDArray[np.float64]] = [theta.copy()]
        coupling_history: list[NDArray[np.float64]] = []
        curvature_updates: list[NDArray[np.float64]] = []
        timestamps: list[int] = []
        mean_kappa: list[float] = []
        herding: list[float] = []
        fragility: list[float] = []
        momentum: list[float] = []
        entropy: list[float] = []

        for k in range(steps):
            if k % self.ricci_update_interval == 0:
                coupling, kappa_vec = self._recompute_coupling(corr_buffer, coupling, n)
                if self.coupling_history_enabled:
                    coupling_history.append(coupling.copy())
                curvature_updates.append(kappa_vec)
                timestamps.append(k)

                mk = float(np.mean(kappa_vec)) if kappa_vec.size else 0.0
                mean_kappa.append(mk)
                herding.append(float(np.mean(kappa_vec > 0.0)) if kappa_vec.size else 0.0)
                fragility.append(float(-mk))
                if len(mean_kappa) < 2:
                    momentum.append(0.0)
                else:
                    delta_steps = max(
                        1, timestamps[-1] - timestamps[-2]
                    )  # bounds: minimum 1 step between timestamps
                    momentum.append(float((mean_kappa[-1] - mean_kappa[-2]) / delta_steps))
                entropy.append(self._coupling_entropy(coupling))

            theta = _rk4_step(theta, self._omega, coupling, dt)
            if not np.isfinite(theta).all():
                raise FloatingPointError(f"Non-finite phase values encountered at step={k + 1}.")
            phases[k + 1] = theta
            order[k + 1] = _order_parameter(theta)
            if not (0.0 <= order[k + 1] <= 1.0):
                raise ValueError(
                    f"Order parameter invariant violated at step={k + 1}: {order[k + 1]:.6f}"
                )

            corr_buffer.append(theta.copy())
            if len(corr_buffer) > self.correlation_window:
                corr_buffer.pop(0)

        transitions = self._detect_transitions(mean_kappa, timestamps)
        if self.coupling_history_enabled:
            coupling_arr = np.asarray(coupling_history, dtype=np.float64)
        else:
            coupling_arr = np.zeros((0, n, n), dtype=np.float64)
        curv_hist = self._pad_curvatures(curvature_updates)

        return KuramotoRicciFlowResult(
            phases=phases,
            order_parameter=order,
            time=time_arr,
            config=cfg,
            coupling_matrix_history=coupling_arr,
            curvature_history=curv_hist,
            curvature_timestamps=np.asarray(timestamps, dtype=np.int64),
            mean_curvature_trajectory=np.asarray(mean_kappa, dtype=np.float64),
            geometric_phase_transitions=transitions,
            herding_index=np.asarray(herding, dtype=np.float64),
            fragility_index=np.asarray(fragility, dtype=np.float64),
            geometric_momentum=np.asarray(momentum, dtype=np.float64),
            coupling_entropy=np.asarray(entropy, dtype=np.float64),
        )

    def _recompute_coupling(
        self,
        corr_buffer: list[NDArray[np.float64]],
        prev_coupling: NDArray[np.float64],
        n: int,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        corr = self._correlation_matrix(corr_buffer, n)
        graph, edges = self._build_correlation_graph(corr)

        try:
            edge_curvatures = self._compute_edge_curvature_map(graph, edges)
            curvatures = np.array([edge_curvatures[e] for e in edges], dtype=np.float64)
            target = self._baseline_coupling(n)
            for idx, (i, j) in enumerate(edges):
                kij = (self.K_base / n) * self._phi(curvatures[idx])
                target[i, j] = kij
                target[j, i] = kij
            coupling = self.damping * prev_coupling + (1.0 - self.damping) * target
            if self.enable_discrete_flow or self.enable_neckpinch_surgery:
                coupling = self._apply_flow_surgery(coupling, edges, edge_curvatures)
            self._validate_coupling(coupling)
            return coupling, curvatures
        except Exception as exc:
            _logger.warning("Ricci computation failed; falling back to baseline coupling: %s", exc)
            fallback = self._baseline_coupling(n)
            self._validate_coupling(fallback)
            return fallback, np.zeros(0, dtype=np.float64)

    def _apply_flow_surgery(
        self,
        coupling: NDArray[np.float64],
        edges: list[tuple[int, int]],
        edge_curvatures: dict[tuple[int, int], float],
    ) -> NDArray[np.float64]:
        """Run one discrete Ricci flow + surgery step on the coupling matrix.

        Records diagnostics on the engine for later retrieval via
        :meth:`run_with_surgery`. Caps the post-surgery coupling at
        ``self._K_max`` and re-symmetrises so that
        :meth:`_validate_coupling` continues to hold.
        """
        # Build a curvature dict keyed only on active edges.
        curvature: dict[tuple[int, int], float] = {
            (int(i), int(j)): float(edge_curvatures[(i, j)]) for (i, j) in edges
        }
        result = ricci_flow_with_surgery(
            coupling.astype(np.float64, copy=True),
            curvature,
            self._ricci_flow_config,
        )
        new_coupling = result.weights_after
        # Re-clip to the K_max envelope to satisfy _validate_coupling (the flow can
        # only shrink active weights, but rescaling for total-edge-mass preservation
        # may push them up; clipping is therefore conservative).
        # INV-RC-FLOW: post-surgery coupling stays in [0, K_max].
        np.clip(new_coupling, 0.0, self._K_max, out=new_coupling)
        np.fill_diagonal(new_coupling, 0.0)
        new_coupling = 0.5 * (new_coupling + new_coupling.T)
        if self.enable_neckpinch_surgery:
            self._surgery_events_buffer.extend(result.surgery_events)
            self._surgery_mass_before.append(result.total_edge_mass_before)
            self._surgery_mass_after.append(result.total_edge_mass_after)
        return new_coupling.astype(np.float64, copy=False)

    def run_with_surgery(
        self,
    ) -> tuple[KuramotoRicciFlowResult, KuramotoRicciFlowSurgeryDiagnostics]:
        """Run the engine and return both the standard result and surgery diagnostics.

        Requires ``enable_discrete_flow=True`` or ``enable_neckpinch_surgery=True``
        in the constructor; otherwise raises :class:`RuntimeError` because the
        diagnostics object would be empty by construction.
        """
        if not (self.enable_discrete_flow or self.enable_neckpinch_surgery):
            raise RuntimeError(
                "run_with_surgery requires enable_discrete_flow or "
                "enable_neckpinch_surgery to be True."
            )
        # Reset diagnostic buffers for a fresh run.
        self._surgery_events_buffer = []
        self._surgery_mass_before = []
        self._surgery_mass_after = []
        result = self.run()
        diagnostics = KuramotoRicciFlowSurgeryDiagnostics(
            surgery_event_count=len(self._surgery_events_buffer),
            neckpinch_edges=tuple(e.edge for e in self._surgery_events_buffer),
            events=tuple(self._surgery_events_buffer),
            total_edge_mass_before=tuple(self._surgery_mass_before),
            total_edge_mass_after=tuple(self._surgery_mass_after),
        )
        return result, diagnostics

    def _compute_edge_curvature_map(
        self,
        graph: Any,
        edges: list[tuple[int, int]],
    ) -> dict[tuple[int, int], float]:
        method = self.curvature_method
        if graph.number_of_nodes() > 200 and method == "ollivier":
            method = "forman"

        if method == "forman":
            lite = self._to_light_graph(graph)
            return {
                edge: float(self._lite_ricci.compute_edge_curvature(lite, edge)) for edge in edges
            }

        try:
            from ..indicators.ricci import RicciCurvature  # type: ignore[attr-defined]

            rc = RicciCurvature()
            return {edge: float(rc.compute_edge_curvature(graph, edge)) for edge in edges}
        except Exception:
            try:
                from ..indicators.ricci import (
                    compute_node_distributions,
                    ricci_curvature_edge,
                )

                distributions = compute_node_distributions(graph)
                return {
                    edge: float(
                        ricci_curvature_edge(graph, edge[0], edge[1], distributions=distributions)
                    )
                    for edge in edges
                }
            except Exception:
                lite = self._to_light_graph(graph)
                return {
                    edge: float(self._lite_ricci.compute_edge_curvature(lite, edge))
                    for edge in edges
                }

    @staticmethod
    def _to_light_graph(graph: Any) -> Any:
        lite: Any
        if LightGraph is None:
            lite = _SimpleUndirectedGraph(int(graph.number_of_nodes()))
        else:
            lite = LightGraph(int(graph.number_of_nodes()))
        for i, j, data in graph.edges(data=True):
            w = float(data.get("weight", 1.0)) if hasattr(data, "get") else 1.0
            lite.add_edge(int(i), int(j), weight=w)
        return lite

    @staticmethod
    def _resolve_initial_conditions(
        cfg: KuramotoConfig,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        rng = np.random.default_rng(cfg.seed)
        omega = (
            cfg.omega.astype(np.float64, copy=False)
            if cfg.omega is not None
            else rng.standard_normal(cfg.N)
        )
        theta0 = (
            cfg.theta0.astype(np.float64, copy=False)
            if cfg.theta0 is not None
            else rng.uniform(0.0, 2.0 * np.pi, cfg.N)
        )
        return omega, theta0

    def _baseline_coupling(self, n: int) -> NDArray[np.float64]:
        base = np.full((n, n), self.K_base / n, dtype=np.float64)
        np.fill_diagonal(base, 0.0)
        self._validate_coupling(base)
        return base

    def _phi(self, kappa: float) -> float:
        return float(self.sigma * (1.0 + np.tanh(self.alpha * kappa)) / 2.0)

    def _correlation_matrix(self, buffer: list[NDArray[np.float64]], n: int) -> NDArray[np.float64]:
        if len(buffer) < 2:
            return np.eye(n, dtype=np.float64)
        mat = np.vstack(buffer)
        diff = mat[:, :, np.newaxis] - mat[:, np.newaxis, :]
        corr = np.abs(np.mean(np.exp(1j * diff), axis=0)).astype(np.float64)
        corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
        corr = np.clip(
            corr, 0.0, 1.0
        )  # INV-RC1: correlation clipped to [0,1] for valid graph weights
        if corr.shape != (n, n):
            raise ValueError(
                f"Correlation shape invariant violated: expected {(n, n)} got {corr.shape}"
            )
        np.fill_diagonal(corr, 1.0)
        out: NDArray[np.float64] = corr.astype(np.float64, copy=False)
        return out

    def _build_correlation_graph(
        self, corr: NDArray[np.float64]
    ) -> tuple[Any, list[tuple[int, int]]]:
        n = corr.shape[0]
        graph = _SimpleUndirectedGraph(n)
        graph.add_nodes_from(range(n))
        edges: list[tuple[int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                w = float(abs(corr[i, j]))
                if w >= self.graph_threshold:
                    graph.add_edge(i, j, weight=w)
                    edges.append((i, j))
        return graph, edges

    def _validate_coupling(self, coupling: NDArray[np.float64]) -> None:
        if not np.isfinite(coupling).all():
            raise ValueError("K_ij invariant violated: non-finite coupling values.")
        if not np.allclose(coupling, coupling.T, atol=1e-12):
            raise ValueError("K_ij invariant violated: coupling matrix must be symmetric.")
        if not np.allclose(np.diag(coupling), 0.0, atol=1e-12):
            raise ValueError("K_ii invariant violated: self-coupling must remain zero.")
        if np.any(coupling < -1e-12) or np.any(coupling > self._K_max + 1e-12):
            raise ValueError(
                f"K_ij invariant violated: values must be in [0, {self._K_max:.6f}] but got "
                f"[{coupling.min():.6f}, {coupling.max():.6f}]"
            )

    @staticmethod
    def _coupling_entropy(coupling: NDArray[np.float64]) -> float:
        upper = np.triu(coupling, k=1)
        vals = upper[upper > 0.0]
        if vals.size == 0:
            return 0.0
        p = vals / np.sum(vals)
        return float(-np.sum(p * np.log(p + 1e-16)))

    @staticmethod
    def _detect_transitions(mean_kappa: list[float], timestamps: list[int]) -> list[int]:
        if len(mean_kappa) < 3:
            return []
        arr = np.asarray(mean_kappa, dtype=np.float64)
        diff = np.diff(arr)
        signs = np.sign(diff)
        out: list[int] = []
        for idx in range(1, len(signs)):
            if signs[idx] != 0.0 and signs[idx - 1] != 0.0 and signs[idx] != signs[idx - 1]:
                out.append(int(timestamps[idx]))
        return out

    @staticmethod
    def _pad_curvatures(curvatures: list[NDArray[np.float64]]) -> NDArray[np.float64]:
        if not curvatures:
            return np.zeros((0, 0), dtype=np.float64)
        max_len = max((arr.size for arr in curvatures), default=0)
        out = np.full((len(curvatures), max_len), np.nan, dtype=np.float64)
        for i, arr in enumerate(curvatures):
            if arr.size:
                out[i, : arr.size] = arr
        return out
