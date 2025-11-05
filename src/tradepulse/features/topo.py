"""Topology sentinel adapter for TradePulse Neuro-Architecture.

This module provides topological data analysis features for market anomaly
detection, with optional gudhi integration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pandas import DataFrame

__all__ = ["TopoSentinel", "TopoResult"]

logger = logging.getLogger(__name__)

# Try to import gudhi for full TDA functionality
try:
    import gudhi

    HAS_GUDHI = True
except ImportError:
    HAS_GUDHI = False
    logger.warning(
        "gudhi not available - TopoSentinel will use simplified proxy metrics. "
        "Install with: pip install 'tradepulse[neuro_advanced]'"
    )


class TopoResult:
    """Result from topological analysis.

    Attributes
    ----------
    topo_score : float
        Topological complexity score (higher = more anomalous)
    """

    def __init__(self, topo_score: float):
        self.topo_score = topo_score


class TopoSentinel:
    """Topological Data Analysis sentinel for market anomalies.

    Computes topological features from correlation structure to detect
    anomalous market conditions. Uses persistent homology when gudhi
    is available, otherwise falls back to simpler graph metrics.

    Parameters
    ----------
    window : int, optional
        Rolling window for computation, by default 50
    persistence_threshold : float, optional
        Threshold for persistent features, by default 0.1
    """

    def __init__(
        self,
        window: int = 50,
        persistence_threshold: float = 0.1,
    ):
        self.window = window
        self.persistence_threshold = persistence_threshold

    def fit_transform(self, returns: DataFrame) -> dict[str, float]:
        """Compute topological score from returns.

        Parameters
        ----------
        returns : DataFrame
            Return data with shape (T, N) where T is time steps and N is assets.

        Returns
        -------
        dict
            Dictionary with key 'topo_score': float
        """
        if len(returns) < self.window:
            logger.warning(
                f"Insufficient data for TopoSentinel: got {len(returns)}, "
                f"need {self.window}. Returning topo_score=0.0"
            )
            return {"topo_score": 0.0}

        if HAS_GUDHI:
            topo_score = self._compute_tda_score(returns)
        else:
            # Fallback to graph-based proxy
            topo_score = self._compute_proxy_score(returns)

        return {"topo_score": topo_score}

    def _compute_tda_score(self, returns: DataFrame) -> float:
        """Compute topological score using persistent homology.

        Uses Vietoris-Rips complex on correlation distance matrix.
        """
        # Get recent window
        recent = returns.tail(self.window)

        # Compute correlation matrix
        corr = recent.corr()

        # Convert to distance matrix (1 - |correlation|)
        dist_matrix = 1.0 - np.abs(corr.values)

        # Ensure distance matrix is symmetric and non-negative
        dist_matrix = np.maximum(dist_matrix, 0.0)
        dist_matrix = (dist_matrix + dist_matrix.T) / 2.0
        np.fill_diagonal(dist_matrix, 0.0)

        # Compute Rips complex
        rips_complex = gudhi.RipsComplex(distance_matrix=dist_matrix, max_edge_length=2.0)
        simplex_tree = rips_complex.create_simplex_tree(max_dimension=2)

        # Compute persistence
        simplex_tree.compute_persistence()

        # Get persistence diagram
        persistence = simplex_tree.persistence()

        # Count long-lived features (persistence > threshold)
        long_lived = 0
        total_persistence = 0.0

        for dim, (birth, death) in persistence:
            if death < np.inf:
                pers = death - birth
                if pers > self.persistence_threshold:
                    long_lived += 1
                total_persistence += pers

        # Normalize score by number of assets
        n_assets = len(recent.columns)
        topo_score = float(long_lived / max(n_assets, 1))

        return topo_score

    def _compute_proxy_score(self, returns: DataFrame) -> float:
        """Compute proxy topological score without gudhi.

        Uses correlation matrix eigenvalue spectrum and clustering coefficient.
        """
        # Get recent window
        recent = returns.tail(self.window)

        # Compute correlation matrix
        corr = recent.corr()

        # Compute eigenvalue spectrum
        eigenvalues = np.linalg.eigvalsh(corr.values)

        # Participation ratio (inverse of normalized eigenvalue variance)
        # High PR = uniform eigenvalues = complex topology
        eigenvalues_norm = eigenvalues / eigenvalues.sum()
        participation_ratio = 1.0 / (eigenvalues_norm**2).sum()

        # Normalize by number of assets
        n_assets = len(recent.columns)
        pr_normalized = participation_ratio / n_assets

        # Compute clustering coefficient proxy from correlation structure
        # High correlations in small groups = low score
        # Uniform correlations = high score
        corr_std = np.std(np.abs(corr.values[np.triu_indices_from(corr.values, k=1)]))

        # Combine metrics
        topo_score = float(pr_normalized * (1.0 + corr_std))

        # Clip to reasonable range
        topo_score = float(np.clip(topo_score, 0.0, 1.0))

        return topo_score
