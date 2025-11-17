"""Ricci curvature graph adapter for TradePulse Neuro-Architecture.

This module provides an adapter for computing Ollivier-Ricci curvature
on correlation graphs, conforming to the neuro-architecture specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from pandas import DataFrame

__all__ = ["RicciCurvatureGraph", "RicciResult"]


class RicciResult:
    """Result from Ricci curvature analysis.

    Attributes
    ----------
    kappa_min : float
        Minimum edge curvature (most negative = most fragile)
    edge_kappa : dict
        Dictionary mapping edge tuples to curvature values
    """

    def __init__(self, kappa_min: float, edge_kappa: dict[tuple[str, str], float]):
        self.kappa_min = kappa_min
        self.edge_kappa = edge_kappa


class RicciCurvatureGraph:
    """Ollivier-Ricci curvature on correlation graphs.

    This adapter computes discrete Ricci curvature on graphs constructed
    from asset return correlations. Negative curvature indicates network
    fragility and potential regime breaks.

    Parameters
    ----------
    correlation_threshold : float, optional
        Minimum correlation to create an edge, by default 0.3
    window : int, optional
        Rolling window for correlation computation, by default 30
    alpha : float, optional
        Transport mass parameter (0 = shortest path, 1 = Ollivier-Ricci),
        by default 0.5
    """

    def __init__(
        self,
        correlation_threshold: float = 0.3,
        window: int = 30,
        alpha: float = 0.5,
    ):
        self.corr_threshold = correlation_threshold
        self.window = window
        self.alpha = alpha

    def fit_transform(self, returns: DataFrame) -> dict[str, float | dict]:
        """Compute Ricci curvature from returns.

        Parameters
        ----------
        returns : DataFrame
            Return data with shape (T, N) where T is time steps and N is assets.
            Index should be DatetimeIndex.

        Returns
        -------
        dict
            Dictionary with keys:
            - 'kappa_min': float, minimum edge curvature
            - 'edge_kappa': dict, edge curvatures
        """
        if len(returns) < self.window:
            raise ValueError(
                f"Insufficient data: need at least {self.window} points, got {len(returns)}"
            )

        # Compute correlation matrix from recent window
        corr_matrix = returns.tail(self.window).corr()

        # Build correlation graph
        G = self._build_correlation_graph(corr_matrix)

        if G.number_of_edges() == 0:
            # No edges - return neutral curvature
            return {
                "kappa_min": 0.0,
                "edge_kappa": {},
            }

        # Compute Ricci curvature for each edge
        edge_kappa = self._compute_edge_curvatures(G)

        # Find minimum curvature (most negative = most fragile)
        kappa_min = min(edge_kappa.values()) if edge_kappa else 0.0

        return {
            "kappa_min": kappa_min,
            "edge_kappa": edge_kappa,
        }

    def _build_correlation_graph(self, corr_matrix: DataFrame) -> nx.Graph:
        """Build undirected graph from correlation matrix.

        Edges are created between assets with correlation above threshold.
        Edge weights are set to correlation strength.
        """
        G = nx.Graph()

        # Add nodes
        G.add_nodes_from(corr_matrix.columns)

        # Add edges for correlations above threshold
        n = len(corr_matrix)
        for i in range(n):
            for j in range(i + 1, n):
                corr = corr_matrix.iloc[i, j]
                if abs(corr) >= self.corr_threshold:
                    # Use absolute correlation as weight
                    G.add_edge(
                        corr_matrix.columns[i],
                        corr_matrix.columns[j],
                        weight=abs(corr),
                    )

        return G

    def _compute_edge_curvatures(self, G: nx.Graph) -> dict[tuple[str, str], float]:
        """Compute Ollivier-Ricci curvature for each edge.

        Uses simplified Wasserstein distance approximation based on
        shortest path distances and local neighborhood structure.
        """
        edge_kappa = {}

        # Compute all-pairs shortest paths
        try:
            shortest_paths = dict(nx.all_pairs_shortest_path_length(G))
        except nx.NetworkXNoPath:
            # Graph is disconnected
            shortest_paths = {}

        for u, v in G.edges():
            # Compute curvature for edge (u, v)
            kappa = self._edge_curvature(G, u, v, shortest_paths)
            edge_kappa[(u, v)] = kappa

        return edge_kappa

    def _edge_curvature(
        self,
        G: nx.Graph,
        u: str,
        v: str,
        shortest_paths: dict,
    ) -> float:
        """Compute Ollivier-Ricci curvature for a single edge.

        κ(u,v) ≈ 1 - W(μ_u, μ_v) / d(u,v)

        where W is Wasserstein distance between probability measures
        on neighborhoods and d(u,v) is graph distance.
        """
        # Get neighbors
        neighbors_u = set(G.neighbors(u))
        neighbors_v = set(G.neighbors(v))

        # Add self-loops with mass alpha
        neighbors_u.add(u)
        neighbors_v.add(v)

        # Compute local probability distributions
        # Uniform distribution over neighbors with self-loop weight alpha
        mass_self = self.alpha
        mass_neighbor = (1.0 - self.alpha) / max(len(neighbors_u) - 1, 1)

        # Compute approximate Wasserstein distance
        # using shortest path distances
        W_dist = 0.0

        for nu in neighbors_u:
            for nv in neighbors_v:
                # Mass contribution
                if nu == u:
                    mu_u = mass_self
                else:
                    mu_u = mass_neighbor

                if nv == v:
                    mu_v = mass_self
                else:
                    mu_v = mass_neighbor

                # Distance contribution
                if nu in shortest_paths and nv in shortest_paths[nu]:
                    dist = shortest_paths[nu][nv]
                else:
                    # Disconnected - use large distance
                    dist = 10.0

                W_dist += mu_u * mu_v * dist

        # Normalize by edge distance (1 for adjacent nodes)
        d_uv = 1.0

        # Curvature formula: κ = 1 - W/d
        kappa = 1.0 - W_dist / d_uv

        return kappa
