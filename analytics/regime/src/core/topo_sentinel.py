# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Topology-aware sentinel features for streaming anomaly detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

__all__ = [
    "TopoSentinelConfig",
    "TopoSentinelResult",
    "TopoSentinel",
]


@dataclass(frozen=True)
class TopoSentinelConfig:
    """Configuration for the :class:`TopoSentinel` feature extractor."""

    persistence_thresholds: tuple[float, ...] = (0.05, 0.1, 0.2, 0.3, 0.4)
    max_dimension: int = 1


@dataclass(frozen=True)
class TopoSentinelResult:
    """Container for the computed topological metrics."""

    topo_score: float
    tda_count_long: int
    tda_entropy: float
    euler_curve: pd.Series


class TopoSentinel:
    """Compute lightweight topological descriptors of the market state."""

    def __init__(self, config: TopoSentinelConfig | None = None) -> None:
        self._config = config or TopoSentinelConfig()

    @property
    def config(self) -> TopoSentinelConfig:
        return self._config

    def compute(
        self,
        returns: Mapping[str, Iterable[float]] | pd.DataFrame,
    ) -> TopoSentinelResult:
        frame = _ensure_frame(returns)
        if frame.empty:
            raise ValueError("TopoSentinel requires non-empty returns frame.")

        dist = _correlation_distance(frame)

        thresholds = self._config.persistence_thresholds
        euler_values = []
        barcode_lengths = []
        for threshold in thresholds:
            adjacency = dist <= threshold
            edges = np.triu(adjacency, k=1)
            edge_count = int(edges.sum())
            node_count = dist.shape[0]
            components = _estimate_components(adjacency)
            euler = node_count - edge_count + components
            euler_values.append(euler)
            barcode_lengths.append(
                max(threshold - dist[edges].mean() if edge_count > 0 else 0.0, 0.0)
            )

        euler_curve = pd.Series(
            euler_values, index=pd.Index(thresholds, name="threshold"), name="euler"
        )
        barcode_array = np.array(barcode_lengths)
        entropy = _entropy(barcode_array)
        count_long = int(np.sum(barcode_array > np.median(barcode_array)))
        euler_area = float(np.trapezoid(euler_curve.values, thresholds))
        topo_score = float((count_long / max(len(thresholds), 1)) + entropy + euler_area)

        return TopoSentinelResult(
            topo_score=topo_score,
            tda_count_long=count_long,
            tda_entropy=float(entropy),
            euler_curve=euler_curve,
        )


def _ensure_frame(data: Mapping[str, Iterable[float]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def _correlation_distance(returns: pd.DataFrame) -> np.ndarray:
    corr = returns.corr().to_numpy()
    corr = np.clip(corr, -1.0, 1.0)
    return np.sqrt(0.5 * (1.0 - corr))


def _estimate_components(adjacency: np.ndarray) -> int:
    visited = np.zeros(adjacency.shape[0], dtype=bool)
    components = 0
    for node in range(adjacency.shape[0]):
        if visited[node]:
            continue
        components += 1
        stack = [node]
        visited[node] = True
        while stack:
            current = stack.pop()
            neighbors = np.nonzero(adjacency[current])[0]
            for neighbor in neighbors:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    stack.append(neighbor)
    return components


def _entropy(lengths: np.ndarray) -> float:
    values = lengths[lengths > 0]
    if values.size == 0:
        return 0.0
    probs = values / values.sum()
    return float(-np.sum(probs * np.log(probs)))
