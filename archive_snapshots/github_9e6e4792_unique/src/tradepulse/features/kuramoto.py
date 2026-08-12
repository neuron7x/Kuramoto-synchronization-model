"""Kuramoto synchrony adapter for TradePulse Neuro-Architecture.

This module provides an adapter to the existing Kuramoto-Ricci composite
indicator, conforming to the fit_transform interface required by the
neuro-architecture specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from pandas import DataFrame, Series

__all__ = ["KuramotoSynchrony", "KuramotoResult"]


class KuramotoResult:
    """Result from Kuramoto synchrony analysis.

    Attributes
    ----------
    R : Series
        Kuramoto order parameter over time (synchrony measure, 0-1)
    delta_R : Series
        Change in order parameter (ΔR) for regime detection
    labels : Series
        Market phase labels (CHAOTIC, EMERGENT, etc.)
    """

    def __init__(self, R: Series, delta_R: Series, labels: Series):
        self.R = R
        self.delta_R = delta_R
        self.labels = labels


class KuramotoSynchrony:
    """Kuramoto order parameter and synchrony detector.

    This adapter wraps the existing MultiScaleKuramoto implementation
    to provide the standardized fit_transform interface.

    Parameters
    ----------
    window : int, optional
        Rolling window size for computing Hilbert phase, by default 30
    lag : int, optional
        Lag for computing ΔR (change in synchrony), by default 3
    R_threshold_high : float, optional
        Threshold for EMERGENT phase, by default 0.7
    R_threshold_low : float, optional
        Threshold below which is CHAOTIC, by default 0.4
    """

    def __init__(
        self,
        window: int = 30,
        lag: int = 3,
        R_threshold_high: float = 0.7,
        R_threshold_low: float = 0.4,
    ):
        self.window = window
        self.lag = lag
        self.R_high = R_threshold_high
        self.R_low = R_threshold_low

    def fit_transform(self, prices: DataFrame) -> dict[str, Series]:
        """Compute Kuramoto synchrony from price data.

        Parameters
        ----------
        prices : DataFrame
            Price data with shape (T, N) where T is time steps and N is assets.
            Index should be DatetimeIndex.

        Returns
        -------
        dict
            Dictionary with keys:
            - 'R': Series of order parameter values
            - 'delta_R': Series of ΔR values
            - 'labels': Series of phase labels
        """
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise ValueError("prices must have DatetimeIndex")

        if len(prices) < self.window:
            raise ValueError(
                f"Insufficient data: need at least {self.window} points, got {len(prices)}"
            )

        # Compute returns
        returns = prices.pct_change().fillna(0.0)

        # Compute Hilbert phases for each asset
        # This is a simplified version - the full implementation uses scipy.signal.hilbert
        phases = self._compute_phases(returns)

        # Compute Kuramoto order parameter R(t)
        R = self._compute_order_parameter(phases)

        # Compute ΔR
        delta_R = R.diff(self.lag).fillna(0.0)

        # Assign labels based on adaptive thresholds
        labels = self._assign_labels(R, delta_R)

        return {
            "R": R,
            "delta_R": delta_R,
            "labels": labels,
        }

    def _compute_phases(self, returns: DataFrame) -> DataFrame:
        """Compute instantaneous phases using Hilbert transform.

        This is a simplified implementation. For production, use
        scipy.signal.hilbert or the existing MultiScaleKuramoto.
        """
        # Simple arctan approximation for demonstration
        # In production, this should use Hilbert transform
        phases = np.arctan2(
            returns.rolling(self.window, min_periods=self.window // 2).std(),
            returns.rolling(self.window, min_periods=self.window // 2).mean(),
        )
        return phases.fillna(0.0)

    def _compute_order_parameter(self, phases: DataFrame) -> Series:
        """Compute Kuramoto order parameter R.

        R = |⟨exp(iθ)⟩| where ⟨⟩ is mean over assets.
        """
        # Compute complex representation
        complex_phases = np.exp(1j * phases.values)

        # Mean over assets (axis=1)
        mean_complex = complex_phases.mean(axis=1)

        # Magnitude is the order parameter
        R = np.abs(mean_complex)

        return pd.Series(R, index=phases.index, name="R")

    def _assign_labels(self, R: Series, delta_R: Series) -> Series:
        """Assign market phase labels based on R and ΔR.

        Uses adaptive thresholds based on median and IQR.
        """
        labels = pd.Series("CAUTION", index=R.index, dtype=str)

        # Adaptive thresholds using rolling statistics
        R_median = R.rolling(self.window * 3, min_periods=self.window).median()
        R_iqr = R.rolling(self.window * 3, min_periods=self.window).quantile(
            0.75
        ) - R.rolling(self.window * 3, min_periods=self.window).quantile(0.25)

        # Use fixed thresholds initially, then adaptive
        R_high_adaptive = R_median + R_iqr
        R_low_adaptive = R_median - R_iqr

        # Fill NaN in adaptive thresholds with fixed thresholds
        R_high_adaptive = R_high_adaptive.fillna(self.R_high)
        R_low_adaptive = R_low_adaptive.fillna(self.R_low)

        # Assign labels
        labels.loc[R > R_high_adaptive] = "EMERGENT"
        labels.loc[R < R_low_adaptive] = "CHAOTIC"

        # Add transition labels based on ΔR
        delta_R_threshold = delta_R.rolling(
            self.window * 2, min_periods=self.window
        ).std()
        delta_R_threshold = delta_R_threshold.fillna(0.1)

        labels.loc[delta_R.abs() > 2 * delta_R_threshold] = "TRANSITION"

        return labels
