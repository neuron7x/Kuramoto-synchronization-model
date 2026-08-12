# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Topology sentinel adapter for GeoSync Neuro-Architecture.

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
        "Install with: pip install 'geosync[neuro_advanced]'"
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
        numeric = returns.select_dtypes(include=[np.number]).copy()
        if numeric.empty:
            logger.warning("TopoSentinel received no numeric columns; returning 0.0")
            return {"topo_score": 0.0}

        numeric.replace([np.inf, -np.inf], np.nan, inplace=True)
        numeric.dropna(axis=1, how="all", inplace=True)
        numeric.dropna(axis=0, how="all", inplace=True)

        if numeric.empty:
            logger.warning(
                "TopoSentinel found no usable data after removing empty rows/columns; returning 0.0"
            )
            return {"topo_score": 0.0}

        usable_counts = numeric.count()
        numeric = numeric.loc[:, usable_counts >= 2]

        if numeric.shape[1] < 2:
            logger.warning(
                "TopoSentinel requires at least two assets with sufficient observations; "
                "returning 0.0"
            )
            return {"topo_score": 0.0}

        variances = numeric.var(skipna=True)
        numeric = numeric.loc[:, (variances > 0.0) & variances.notna()]

        if numeric.shape[1] < 2:
            logger.warning(
                "TopoSentinel found fewer than two assets with non-zero variance; returning 0.0"
            )
            return {"topo_score": 0.0}

        effective_rows = numeric.dropna(how="all")
        if len(effective_rows) < self.window:
            logger.warning(
                "Insufficient usable data for TopoSentinel after cleaning: "
                f"got {len(effective_rows)}, need {self.window}. Returning topo_score=0.0"
            )
            return {"topo_score": 0.0}

        if HAS_GUDHI:
            topo_score = self._compute_tda_score(effective_rows)
        else:
            # Fallback to graph-based proxy
            topo_score = self._compute_proxy_score(effective_rows)

        return {"topo_score": topo_score}

    def _compute_tda_score(self, returns: DataFrame) -> float:
        """Compute topological score using persistent homology.

        Uses Vietoris-Rips complex on correlation distance matrix.
        """
        # Get recent window
        recent = returns.tail(self.window)

        # Compute correlation matrix
        corr = recent.corr()
        corr = self._clean_correlation_matrix(corr)

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
        corr = self._clean_correlation_matrix(corr)

        # Compute eigenvalue spectrum
        eigenvalues = np.linalg.eigvalsh(corr.values)
        eigenvalues_sum = float(np.sum(eigenvalues))
        if not np.isfinite(eigenvalues_sum) or eigenvalues_sum <= 0:
            logger.warning("Correlation matrix produced invalid eigenvalue sum; returning 0.0")
            return 0.0

        # Participation ratio (inverse of normalized eigenvalue variance)
        # High PR = uniform eigenvalues = complex topology
        eigenvalues_norm = eigenvalues / eigenvalues_sum
        denom = float(np.sum(eigenvalues_norm**2))
        if not np.isfinite(denom) or denom <= 0:
            logger.warning("Eigenvalue spectrum is degenerate; returning 0.0")
            return 0.0
        participation_ratio = 1.0 / denom

        # Normalize by number of assets
        n_assets = len(recent.columns)
        pr_normalized = participation_ratio / n_assets

        # Compute clustering coefficient proxy from correlation structure
        # High correlations in small groups = low score
        # Uniform correlations = high score
        upper_triangle = np.abs(corr.values[np.triu_indices_from(corr.values, k=1)])
        if upper_triangle.size == 0:
            corr_std = 0.0
        else:
            corr_std = float(np.nanstd(upper_triangle))

        # Combine metrics
        topo_score = float(pr_normalized * (1.0 + corr_std))

        # Clip to reasonable range
        topo_score = float(np.clip(topo_score, 0.0, 1.0))

        if not np.isfinite(topo_score):
            return 0.0

        return topo_score

    def _clean_correlation_matrix(self, corr: DataFrame) -> DataFrame:
        """Return a numeric correlation matrix with NaNs replaced by safe defaults."""

        if corr.empty:
            return corr

        cleaned = corr.fillna(0.0)
        # pandas 3 Copy-on-Write returns ``.values`` as a read-only view;
        # ``np.fill_diagonal`` writes in place. Build a writable buffer,
        # set the diagonal there, then assign back via the input frame's own
        # constructor (avoids a runtime import of the pandas top-level name).
        values = np.array(cleaned.values, copy=True)
        np.fill_diagonal(values, 1.0)
        cleaned = type(cleaned)(values, index=cleaned.index, columns=cleaned.columns)
        cleaned = (cleaned + cleaned.T) / 2.0
        return cleaned
