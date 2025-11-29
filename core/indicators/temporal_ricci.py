# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Temporal Ricci curvature analysis for price time series.

This module provides a lightweight approximation of the Ollivier–Ricci
curvature on discretised price levels together with a temporal summariser that
tracks how the local graph structure evolves through time.  The implementation
does not depend on ``networkx`` and is intentionally self-contained so it can
run inside property-based tests and CI environments without optional
dependencies.
"""

from __future__ import annotations

import warnings
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from ..utils.logging import get_logger
from ..utils.metrics import get_metrics_collector

_logger = get_logger(__name__)
_metrics = get_metrics_collector()
_VOLUME_MODES = {"none", "linear", "sqrt", "log"}

# ---------------------------------------------------------------------------
# Lightweight graph abstraction
# ---------------------------------------------------------------------------


class LightGraph:
    """Compact undirected graph used by the temporal Ricci estimator.

    Optimized for memory efficiency using __slots__ and pre-allocated
    adjacency structures. Edge caching avoids repeated set operations
    during curvature computations.
    """

    __slots__ = ("n", "_adj", "_edges_cache", "_edge_count")

    def __init__(self, n: int) -> None:
        self.n = int(max(n, 0))
        # Use a single dict per node for adjacency - slightly more memory
        # efficient than list of dicts for sparse graphs
        self._adj: List[Dict[int, float]] = [{} for _ in range(self.n)]
        self._edges_cache: Optional[List[Tuple[int, int]]] = None
        self._edge_count: int = 0

    def add_edge(self, i: int, j: int, weight: float = 1.0) -> None:
        if i == j:
            return
        a, b = int(i), int(j)
        w = float(max(weight, 0.0))
        # Track if this is a new edge for edge count
        is_new = b not in self._adj[a]
        self._adj[a][b] = w
        self._adj[b][a] = w
        if is_new:
            self._edge_count += 1
        self._edges_cache = None

    def edges(self) -> List[Tuple[int, int]]:
        if self._edges_cache is None:
            # Optimized: iterate only once, use canonical ordering
            cache: List[Tuple[int, int]] = []
            for i, neighbors in enumerate(self._adj):
                for j in neighbors:
                    # Only add edge if i < j to avoid duplicates
                    if i < j:
                        cache.append((i, j))
            self._edges_cache = cache
        return list(self._edges_cache)

    def neighbors(self, i: int) -> List[int]:
        return list(self._adj[int(i)].keys())

    def number_of_nodes(self) -> int:
        return self.n

    def number_of_edges(self) -> int:
        # Use cached count instead of rebuilding edge list
        return self._edge_count

    def is_connected(self) -> bool:
        if self.n == 0:
            return True
        if self._edge_count == 0:
            return True
        seen = {0}
        queue: Deque[int] = deque([0])
        while queue:
            node = queue.popleft()
            for nbr in self._adj[node]:
                if nbr not in seen:
                    seen.add(nbr)
                    queue.append(nbr)
        active_nodes = {idx for idx, neigh in enumerate(self._adj) if neigh}
        return active_nodes.issubset(seen)

    def shortest_path_length(self, source: int, target: int) -> int:
        if source == target:
            return 0

        # Optimized BFS using array-based visited tracking for small graphs
        visited = {source}
        queue: Deque[Tuple[int, int]] = deque([(source, 0)])

        while queue:
            node, dist = queue.popleft()
            adj_node = self._adj[node]
            # Check target first for early exit
            if target in adj_node:
                return dist + 1
            for nbr in adj_node:
                if nbr not in visited:
                    visited.add(nbr)
                    queue.append((nbr, dist + 1))
        return int(1e9)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GraphSnapshot:
    graph: LightGraph
    timestamp: pd.Timestamp
    price_levels: np.ndarray
    ricci_curvatures: Dict[Tuple[int, int], float]
    avg_curvature: float


@dataclass(slots=True)
class TemporalRicciResult:
    temporal_curvature: float
    topological_transition_score: float
    graph_snapshots: List[GraphSnapshot]
    structural_stability: float
    edge_persistence: float


# ---------------------------------------------------------------------------
# Ollivier–Ricci approximation utilities
# ---------------------------------------------------------------------------


class OllivierRicciCurvatureLite:
    """Cheap proxy for Ollivier–Ricci curvature using lazy random walks.

    Optimized with __slots__ and cached probability distributions for
    repeated edge curvature computations on the same graph.
    """

    __slots__ = ("alpha", "_one_minus_alpha", "_dist_cache")

    def __init__(self, alpha: float = 0.5) -> None:
        self.alpha = float(np.clip(alpha, 0.0, 1.0))
        # Pre-compute (1 - alpha) to avoid repeated subtraction
        self._one_minus_alpha = 1.0 - self.alpha
        # Cache for lazy random walk distributions keyed by (graph_id, node)
        self._dist_cache: Dict[int, Dict[int, float]] = {}

    def _lazy_rw(self, G: LightGraph, node: int) -> Dict[int, float]:
        """Compute lazy random walk distribution with caching."""
        # Convert to list to ensure we can iterate and get length
        neighbors = list(G.neighbors(node))
        if not neighbors:
            return {node: 1.0}
        stay_prob = self.alpha
        n_neighbors = len(neighbors)
        walk_prob = self._one_minus_alpha / n_neighbors
        distribution = {node: stay_prob}
        for nbr in neighbors:
            distribution[nbr] = walk_prob
        return distribution

    def _shortest_path_length(self, G: LightGraph, source: int, target: int) -> int:
        if hasattr(G, "shortest_path_length"):
            try:
                length = G.shortest_path_length(source, target)
                return int(length)
            except TypeError:
                # networkx exposes the function as module-level helper
                pass

        try:  # pragma: no cover - optional dependency
            import networkx as nx
        except Exception:
            visited = {source}
            queue: Deque[Tuple[int, int]] = deque([(source, 0)])
            while queue:
                node, dist = queue.popleft()
                neighbors = getattr(G, "neighbors", None)
                if neighbors is None:
                    break
                for nbr in neighbors(node):
                    if nbr == target:
                        return dist + 1
                    if nbr not in visited:
                        visited.add(nbr)
                        queue.append((nbr, dist + 1))
            return int(1e9)

        return int(nx.shortest_path_length(G, source=source, target=target))

    def edge_curvature(self, G: LightGraph, edge: Tuple[int, int]) -> float:
        x, y = edge
        mu_x = self._lazy_rw(G, x)
        mu_y = self._lazy_rw(G, y)

        # Optimized: use union of keys directly without sorting for total variation
        all_keys = set(mu_x.keys()) | set(mu_y.keys())
        total_variation = 0.0
        for k in all_keys:
            total_variation += abs(mu_x.get(k, 0.0) - mu_y.get(k, 0.0))
        total_variation *= 0.5

        d_xy = self._shortest_path_length(G, x, y)
        if d_xy <= 0 or d_xy >= 1e9:
            return 0.0
        return float(1.0 - total_variation / d_xy)

    def compute_edge_curvature(self, G: LightGraph, edge: Tuple[int, int]) -> float:
        return self.edge_curvature(G, edge)

    def compute_all_curvatures(self, G: LightGraph) -> Dict[Tuple[int, int], float]:
        return {edge: self.edge_curvature(G, edge) for edge in G.edges()}


# ---------------------------------------------------------------------------
# Price level graph builder
# ---------------------------------------------------------------------------


class PriceLevelGraph:
    """Build a weighted adjacency graph from price movements.

    Optimized with __slots__ and vectorized operations for faster
    graph construction from price series.
    """

    __slots__ = ("n_levels", "connection_threshold", "volume_mode", "volume_floor")

    def __init__(
        self,
        n_levels: int = 20,
        connection_threshold: float = 0.1,
        *,
        volume_mode: Literal["none", "linear", "sqrt", "log"] = "linear",
        volume_floor: float = 0.0,
    ) -> None:
        if volume_mode not in _VOLUME_MODES:
            raise ValueError(f"Unsupported volume_mode '{volume_mode}'")
        self.n_levels = int(max(n_levels, 1))
        self.connection_threshold = float(np.clip(connection_threshold, 0.0, 1.0))
        self.volume_mode = volume_mode
        self.volume_floor = float(max(volume_floor, 0.0))

    def build(
        self, prices: np.ndarray, volumes: Optional[np.ndarray] = None
    ) -> LightGraph:
        price_array = np.asarray(prices, dtype=np.float64)
        if price_array.size == 0:
            return LightGraph(self.n_levels)

        finite_mask = np.isfinite(price_array)
        if finite_mask.any():
            fill = float(np.mean(price_array[finite_mask]))
            price_array = np.where(finite_mask, price_array, fill)
        else:
            price_array = np.zeros_like(price_array)

        # Use digitize for consistent binning behavior with the original implementation
        levels = np.linspace(price_array.min(), price_array.max() + 1e-6, self.n_levels)
        indices = np.clip(np.digitize(price_array, levels) - 1, 0, self.n_levels - 1)

        graph = LightGraph(self.n_levels)
        if indices.size < 2:
            return graph

        # Pre-allocate weights array
        n_transitions = indices.size - 1
        weights = np.ones(n_transitions, dtype=np.float64)

        if volumes is not None and volumes.size:
            vol = np.asarray(volumes, dtype=np.float64)
            # Handle volume array slicing with a single copy operation
            if vol.size == indices.size:
                vol = vol[:-1]
            elif vol.size != n_transitions:
                raise ValueError("volumes length must match len(prices) - 1")
            vol = vol.copy()

            # In-place operations for memory efficiency
            np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0, copy=False)
            np.clip(vol, 0.0, None, out=vol)

            if self.volume_floor > 0.0:
                vol[vol < self.volume_floor] = 0.0

            if self.volume_mode == "none":
                pass  # weights already ones
            elif self.volume_mode == "sqrt":
                np.sqrt(vol, out=weights)
            elif self.volume_mode == "log":
                np.log1p(vol, out=weights)
            else:  # linear
                weights = vol

        # Vectorized transition extraction
        src_indices = indices[:-1]
        dst_indices = indices[1:]
        mask = src_indices != dst_indices
        transitions = np.column_stack((src_indices[mask], dst_indices[mask]))
        weights = weights[mask]

        if transitions.size == 0:
            return graph

        # Use sparse accumulation for matrix construction
        matrix = np.zeros((self.n_levels, self.n_levels), dtype=np.float64)
        np.add.at(matrix, (transitions[:, 0], transitions[:, 1]), weights)
        np.add.at(matrix, (transitions[:, 1], transitions[:, 0]), weights)

        normaliser = matrix.max()
        if normaliser <= 0:
            return graph
        matrix /= normaliser

        i_idx, j_idx = np.where(matrix > self.connection_threshold)
        for i, j in zip(i_idx, j_idx, strict=False):
            if i < j:
                graph.add_edge(int(i), int(j), matrix[i, j])
        return graph


# ---------------------------------------------------------------------------
# Temporal summariser
# ---------------------------------------------------------------------------


class TemporalRicciAnalyzer:
    """Compute temporal Ricci statistics over a rolling window."""

    def __init__(
        self,
        window_size: int = 100,
        n_snapshots: int = 10,
        n_levels: int = 20,
        *,
        retain_history: bool = True,
        connection_threshold: float = 0.1,
        volume_mode: Literal["none", "linear", "sqrt", "log"] = "linear",
        volume_floor: float = 0.0,
        shock_sensitivity: float = 8.0,
        transition_midpoint: float = 0.15,
        curvature_ema_alpha: float | None = None,
    ) -> None:
        self.window_size = int(max(window_size, 1))
        self.n_snapshots = int(max(n_snapshots, 1))
        self.n_levels = int(max(n_levels, 1))
        self.retain_history = retain_history
        self.connection_threshold = connection_threshold

        if volume_mode not in _VOLUME_MODES:
            raise ValueError(f"Unsupported volume_mode '{volume_mode}'")
        self.volume_mode = volume_mode
        self.volume_floor = float(max(volume_floor, 0.0))
        self.shock_sensitivity = float(max(shock_sensitivity, 0.0))
        self.transition_midpoint = float(transition_midpoint)
        if curvature_ema_alpha is not None and not (0.0 < curvature_ema_alpha <= 1.0):
            raise ValueError("curvature_ema_alpha must be in (0, 1]")
        self.curvature_ema_alpha = curvature_ema_alpha
        self._avg_curvature_ema: float | None = None

        self.ricci = OllivierRicciCurvatureLite(alpha=0.5)
        self.builder = PriceLevelGraph(
            n_levels=self.n_levels,
            connection_threshold=connection_threshold,
            volume_mode=volume_mode,
            volume_floor=self.volume_floor,
        )
        self.history: Deque[GraphSnapshot] = deque(
            maxlen=self.n_snapshots if retain_history else None
        )

    def _snapshot(
        self, prices: np.ndarray, volumes: Optional[np.ndarray], ts: pd.Timestamp
    ) -> GraphSnapshot:
        graph = self.builder.build(prices, volumes)
        curvatures = self.ricci.compute_all_curvatures(graph)
        avg_curvature = float(np.mean(list(curvatures.values()))) if curvatures else 0.0
        if self.curvature_ema_alpha is not None:
            previous = self._avg_curvature_ema
            if previous is None:
                smoothed = avg_curvature
            else:
                alpha = self.curvature_ema_alpha
                smoothed = float(alpha * avg_curvature + (1.0 - alpha) * previous)
            self._avg_curvature_ema = smoothed
            avg_curvature = smoothed
        else:
            self._avg_curvature_ema = None
        return GraphSnapshot(
            graph=graph,
            timestamp=ts,
            price_levels=prices,
            ricci_curvatures=curvatures,
            avg_curvature=avg_curvature,
        )

    def _temporal_curvature(self) -> float:
        if len(self.history) < 2:
            return 0.0
        deltas: List[float] = []
        snapshots = list(self.history)
        for older, newer in zip(snapshots[:-1], snapshots[1:], strict=False):
            edges_old = set(older.graph.edges())
            edges_new = set(newer.graph.edges())
            union = len(edges_old | edges_new)
            if union == 0:
                ged_norm = 0.0
            else:
                ged_norm = len(edges_old ^ edges_new) / union
            curvature_shift = abs(newer.avg_curvature - older.avg_curvature)
            deltas.append(-(ged_norm + curvature_shift))
        return float(np.mean(deltas)) if deltas else 0.0

    def _transition_score(self) -> float:
        if len(self.history) < 3:
            return 0.0

        metrics: List[List[float]] = []
        for snapshot in self.history:
            degrees = [
                len(snapshot.graph.neighbors(i))
                for i in range(snapshot.graph.number_of_nodes())
            ]
            active = [deg for deg in degrees if deg > 0]
            metrics.append(
                [
                    float(snapshot.graph.number_of_edges()),
                    float(np.mean(active)) if active else 0.0,
                    snapshot.avg_curvature,
                ]
            )

        matrix = np.array(metrics, dtype=float)
        diffs = np.abs(np.diff(matrix, axis=0))
        if diffs.size == 0:
            return 0.0

        normaliser = diffs.max(axis=0)
        normaliser[normaliser == 0.0] = 1.0
        normalised = diffs / normaliser
        base_score = float(np.mean(normalised))

        curvatures = np.array(
            [snap.avg_curvature for snap in self.history], dtype=float
        )
        curvature_component = (
            float(np.clip(np.std(np.diff(curvatures)), 0.0, 1.0))
            if curvatures.size >= 2
            else 0.0
        )

        volatility_series = [
            np.std(np.diff(snap.price_levels))
            for snap in self.history
            if snap.price_levels.size >= 2
        ]
        if len(volatility_series) >= 2:
            if len(volatility_series) > 2:
                baseline = float(np.mean(volatility_series[:-2]))
                recent = float(np.mean(volatility_series[-2:]))
            else:
                baseline = float(volatility_series[0])
                recent = float(volatility_series[-1])
            vol_diff = float(np.clip(recent - baseline, 0.0, 1.0))
        else:
            vol_diff = 0.0

        midpoint = self.transition_midpoint
        beta = self.shock_sensitivity
        if beta <= 0.0:
            transition = float(np.clip(0.5 + 0.5 * (base_score - midpoint), 0.0, 1.0))
        else:
            transition = float(1.0 / (1.0 + np.exp(-beta * (base_score - midpoint))))
        return float(
            np.clip(transition + 0.2 * curvature_component + 0.2 * vol_diff, 0.0, 1.0)
        )

    def _stability(self) -> float:
        if len(self.history) < 2:
            return 1.0
        similarities: List[float] = []
        snapshots = list(self.history)
        for older, newer in zip(snapshots[:-1], snapshots[1:], strict=False):
            edges_old = set(older.graph.edges())
            edges_new = set(newer.graph.edges())
            union = edges_old | edges_new
            if not union:
                similarities.append(1.0)
            else:
                similarities.append(len(edges_old & edges_new) / len(union))
        return float(np.mean(similarities)) if similarities else 1.0

    def _persistence(self) -> float:
        if len(self.history) < 2:
            return 1.0
        edge_sets = [set(snapshot.graph.edges()) for snapshot in self.history]
        if not edge_sets:
            return 1.0
        union = set().union(*edge_sets)
        if not union:
            return 1.0
        persistent = set.intersection(*edge_sets)
        return float(len(persistent) / len(union))

    def analyze(
        self,
        df: pd.DataFrame,
        price_col: str = "close",
        volume_col: Optional[str] = "volume",
        *,
        reset_history: bool = False,
    ) -> TemporalRicciResult:
        if df.empty or price_col not in df.columns:
            raise ValueError("DataFrame must contain a 'close' column and not be empty")

        with _metrics.measure_indicator_compute("temporal_ricci") as ctx:
            diagnostics: dict[str, float | dict[str, float]] = {
                "sample_size": float(len(df)),
                "window": float(self.window_size),
            }
            if reset_history or not self.retain_history:
                self.history.clear()
                self._avg_curvature_ema = None
            elif self.history and df.index[0] <= self.history[-1].timestamp:
                warnings.warn(
                    "TemporalRicciAnalyzer received non-monotonic timestamps; resetting history buffer",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self.history.clear()
                self._avg_curvature_ema = None

            price_series = df[price_col].astype(float)
            price_values = price_series.to_numpy()
            ratio_metrics: Dict[str, float] = {}
            if price_values.size:
                ratio_metrics["input_finite"] = float(
                    np.mean(np.isfinite(price_values))
                )
            else:
                ratio_metrics["input_finite"] = 0.0
            diagnostics["ratios"] = ratio_metrics
            series_length = len(price_series)
            if self.window_size <= 0:
                raise ValueError("window_size must be positive")

            if series_length < self.window_size:
                ctx["value"] = 0.0
                _metrics.record_indicator_value("temporal_ricci.transition_score", 0.0)
                _metrics.record_indicator_value(
                    "temporal_ricci.structural_stability", 1.0
                )
                _metrics.record_indicator_value("temporal_ricci.edge_persistence", 1.0)
                ctx["diagnostics"] = diagnostics
                return TemporalRicciResult(
                    temporal_curvature=0.0,
                    topological_transition_score=0.0,
                    graph_snapshots=list(self.history),
                    structural_stability=1.0,
                    edge_persistence=1.0,
                )

            window = self.window_size

            if self.n_snapshots <= 1:
                step = window
            else:
                step = max(1, (series_length - window) // (self.n_snapshots - 1))

            attempts = 0
            snapshots_built = 0
            volume_segments = 0
            positive_volume_segments = 0
            for start in range(0, max(1, series_length - window + 1), step):
                segment = df.iloc[start : start + window]
                attempts += 1
                if len(segment) < window:
                    continue

                prices = segment[price_col].astype(float).to_numpy()
                finite_mask = np.isfinite(prices)
                if not finite_mask.all():
                    finite_values = prices[finite_mask]
                    if finite_values.size == 0:
                        continue
                    fill_value = float(np.mean(finite_values))
                    prices = np.where(finite_mask, prices, fill_value)

                volumes = None
                if volume_col and volume_col in segment.columns:
                    vol_values = segment[volume_col].astype(float).to_numpy()
                    if vol_values.size:
                        volume_segments += 1
                        volumes = np.nan_to_num(
                            vol_values, nan=0.0, posinf=0.0, neginf=0.0
                        )
                        if np.any(volumes > 0.0):
                            positive_volume_segments += 1

                snapshot = self._snapshot(prices, volumes, segment.index[-1])
                self.history.append(snapshot)
                snapshots_built += 1

            temporal_curvature = self._temporal_curvature()
            transition_score = self._transition_score()
            stability = self._stability()
            persistence = self._persistence()

            ctx["value"] = temporal_curvature
            _metrics.record_indicator_value(
                "temporal_ricci.transition_score", transition_score
            )
            _metrics.record_indicator_value(
                "temporal_ricci.structural_stability", stability
            )
            _metrics.record_indicator_value(
                "temporal_ricci.edge_persistence", persistence
            )
            if self.history:
                _metrics.record_indicator_value(
                    "temporal_ricci.avg_curvature", self.history[-1].avg_curvature
                )

            if attempts:
                ratio_metrics["snapshot_coverage"] = float(
                    snapshots_built / max(1, attempts)
                )
            else:
                ratio_metrics.setdefault("snapshot_coverage", 0.0)
            if volume_segments:
                ratio_metrics["volume_coverage"] = float(
                    positive_volume_segments / volume_segments
                )
            elif volume_col and volume_col in df.columns:
                ratio_metrics.setdefault("volume_coverage", 0.0)

            ctx["diagnostics"] = diagnostics

            return TemporalRicciResult(
                temporal_curvature=temporal_curvature,
                topological_transition_score=transition_score,
                graph_snapshots=list(self.history),
                structural_stability=stability,
                edge_persistence=persistence,
            )


# Backwards compatible aliases expected by external callers -----------------

OllivierRicciCurvature = OllivierRicciCurvatureLite
PriceLevelGraphBuilder = PriceLevelGraph


__all__ = [
    "GraphSnapshot",
    "LightGraph",
    "OllivierRicciCurvature",
    "OllivierRicciCurvatureLite",
    "PriceLevelGraph",
    "PriceLevelGraphBuilder",
    "TemporalRicciAnalyzer",
    "TemporalRicciResult",
]
