# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FPM-A (Fractal Portfolio Management - Analytics) core module.

This module serves as the main entry point for the FPM-A analytics framework,
which implements hexagonal architecture principles for portfolio management
analysis. The framework uses ports and adapters to maintain clean separation
between business logic and infrastructure concerns.

FPM-A provides fractal-inspired portfolio optimization that operates across
multiple time scales and market regimes. Key features include:
    - Multi-scale regime detection using wavelet decomposition
    - Fractal portfolio weighting based on Hurst exponent
    - Risk parity across multiple time horizons
    - Adaptive rebalancing with regime-aware triggers

Example:
    >>> from analytics.fpma.src.core.main import FractalPortfolioAnalyzer
    >>> analyzer = FractalPortfolioAnalyzer(scales=[5, 21, 63])
    >>> weights = analyzer.compute_fractal_weights(returns_df)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


class MarketRegime(Enum):
    """Classification of market regime states."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    REGIME_TRANSITION = "regime_transition"


@dataclass(slots=True)
class RegimeSnapshot:
    """Snapshot of detected market regime at a point in time."""

    regime: MarketRegime
    confidence: float
    hurst_exponent: float
    volatility_percentile: float
    scale_contributions: Dict[int, float] = field(default_factory=dict)


@dataclass(slots=True)
class FractalWeights:
    """Portfolio weights computed using fractal analysis."""

    weights: Dict[str, float]
    effective_scale: int
    regime: MarketRegime
    risk_contribution: Dict[str, float] = field(default_factory=dict)


def add(a: int, b: int) -> int:
    """Legacy placeholder function maintained for backward compatibility."""
    return a + b


def compute_hurst_exponent(
    returns: np.ndarray, min_lag: int = 2, max_lag: int | None = None
) -> float:
    """Compute Hurst exponent using Rescaled Range (R/S) analysis.

    The Hurst exponent H is estimated using the classical R/S method introduced
    by H.E. Hurst (1951) and later formalized by Mandelbrot & Wallis (1969).
    For each lag τ, the algorithm computes the rescaled range R/S over non-
    overlapping subseries and performs linear regression on log(τ) vs log(R/S)
    to estimate H as the slope.

    The interpretation of the Hurst exponent:
    - H > 0.5: Persistent/trending behavior (positive autocorrelation)
    - H = 0.5: Random walk / no memory (Brownian motion)
    - H < 0.5: Anti-persistent/mean-reverting behavior (negative autocorrelation)

    References:
        - Hurst, H.E. (1951). "Long-term storage capacity of reservoirs"
        - Mandelbrot, B.B. & Wallis, J.R. (1969). "Robustness of the rescaled
          range R/S in the measurement of noncyclic long run statistical
          dependence"

    Args:
        returns: Array of returns or price changes
        min_lag: Minimum lag for R/S computation (default: 2)
        max_lag: Maximum lag (defaults to len(returns)//4)

    Returns:
        Estimated Hurst exponent in range [0, 1]. Returns 0.5 for
        insufficient data (assumes random walk).
    """
    returns = np.asarray(returns, dtype=np.float64)
    n = len(returns)

    if n < min_lag * 2:
        return 0.5  # Insufficient data, assume random walk

    if max_lag is None:
        max_lag = max(min_lag + 1, n // 4)

    max_lag = min(max_lag, n // 2)

    lags = []
    rs_values = []

    for lag in range(min_lag, max_lag + 1):
        subseries_count = n // lag
        if subseries_count < 1:
            continue

        rs_list = []
        for i in range(subseries_count):
            subseries = returns[i * lag : (i + 1) * lag]
            if len(subseries) < 2:
                continue

            mean_val = np.mean(subseries)
            cumulative_deviation = np.cumsum(subseries - mean_val)
            r = np.max(cumulative_deviation) - np.min(cumulative_deviation)
            s = np.std(subseries, ddof=1)

            if s > 1e-10:
                rs_list.append(r / s)

        if rs_list:
            lags.append(lag)
            rs_values.append(np.mean(rs_list))

    if len(lags) < 2:
        return 0.5

    log_lags = np.log(lags)
    log_rs = np.log(rs_values)

    # Linear regression to estimate Hurst exponent
    slope, _ = np.polyfit(log_lags, log_rs, 1)
    return float(np.clip(slope, 0.0, 1.0))


def wavelet_decomposition(series: np.ndarray, scales: Sequence[int]) -> Dict[int, np.ndarray]:
    """Perform multi-scale wavelet-like decomposition using moving averages.

    This simplified wavelet approximation decomposes the series into
    components at different time scales using exponential moving averages.

    Args:
        series: Input time series
        scales: List of scale periods for decomposition

    Returns:
        Dictionary mapping scale to decomposed component
    """
    series = np.asarray(series, dtype=np.float64)
    components: Dict[int, np.ndarray] = {}

    for scale in sorted(scales):
        alpha = 2.0 / (scale + 1)
        ema = np.zeros_like(series)
        ema[0] = series[0]

        for i in range(1, len(series)):
            ema[i] = alpha * series[i] + (1 - alpha) * ema[i - 1]

        components[scale] = ema

    return components


def detect_regime(
    returns: np.ndarray,
    volatility_window: int = 21,
    trend_window: int = 63,
) -> RegimeSnapshot:
    """Detect current market regime from returns series.

    Combines Hurst exponent analysis with volatility percentile ranking
    to classify the market regime.

    Args:
        returns: Array of returns
        volatility_window: Window for volatility estimation
        trend_window: Window for trend analysis

    Returns:
        RegimeSnapshot with detected regime and confidence
    """
    returns = np.asarray(returns, dtype=np.float64)
    n = len(returns)

    # Compute Hurst exponent
    hurst = compute_hurst_exponent(returns)

    # Compute rolling volatility
    if n >= volatility_window:
        recent_vol = np.std(returns[-volatility_window:])
        historical_vols = [
            np.std(returns[i : i + volatility_window])
            for i in range(max(0, n - volatility_window * 4), n - volatility_window + 1)
        ]
        if historical_vols:
            vol_percentile = float(
                np.sum(np.array(historical_vols) <= recent_vol) / len(historical_vols)
            )
        else:
            vol_percentile = 0.5
    else:
        vol_percentile = 0.5

    # Compute trend direction
    if n >= trend_window:
        trend_returns = np.sum(returns[-trend_window:])
    else:
        trend_returns = np.sum(returns)

    # Classify regime
    confidence = 0.5
    scale_contributions: Dict[int, float] = {}

    if hurst > 0.6:
        # Trending behavior
        if trend_returns > 0:
            regime = MarketRegime.TRENDING_UP
            confidence = min(0.95, 0.5 + (hurst - 0.5) * 0.9)
        else:
            regime = MarketRegime.TRENDING_DOWN
            confidence = min(0.95, 0.5 + (hurst - 0.5) * 0.9)
    elif hurst < 0.4:
        # Mean-reverting behavior
        regime = MarketRegime.MEAN_REVERTING
        confidence = min(0.95, 0.5 + (0.5 - hurst) * 0.9)
    elif vol_percentile > 0.8:
        regime = MarketRegime.HIGH_VOLATILITY
        confidence = vol_percentile
    elif vol_percentile < 0.2:
        regime = MarketRegime.LOW_VOLATILITY
        confidence = 1.0 - vol_percentile
    else:
        regime = MarketRegime.REGIME_TRANSITION
        confidence = 0.5

    return RegimeSnapshot(
        regime=regime,
        confidence=confidence,
        hurst_exponent=hurst,
        volatility_percentile=vol_percentile,
        scale_contributions=scale_contributions,
    )


class FractalPortfolioAnalyzer:
    """Multi-scale fractal portfolio analyzer.

    Implements fractal-inspired portfolio optimization that adapts to
    market regimes across multiple time scales.

    Example:
        >>> analyzer = FractalPortfolioAnalyzer(scales=[5, 21, 63])
        >>> weights = analyzer.compute_fractal_weights(returns_df)
        >>> print(weights.weights)
    """

    def __init__(
        self,
        scales: Sequence[int] | None = None,
        risk_free_rate: float = 0.0,
        target_volatility: float | None = None,
    ) -> None:
        """Initialize the fractal portfolio analyzer.

        Args:
            scales: Time scales for multi-scale analysis (default: [5, 21, 63])
            risk_free_rate: Annualized risk-free rate for Sharpe calculations
            target_volatility: Target portfolio volatility (optional)
        """
        self.scales = list(scales) if scales else [5, 21, 63]
        self.risk_free_rate = risk_free_rate
        self.target_volatility = target_volatility
        self._regime_history: List[RegimeSnapshot] = []

    def compute_fractal_weights(
        self,
        returns: pd.DataFrame,
        constraints: Dict[str, tuple[float, float]] | None = None,
    ) -> FractalWeights:
        """Compute portfolio weights using fractal analysis.

        Combines multi-scale decomposition with regime detection to
        produce adaptive portfolio weights.

        Args:
            returns: DataFrame of asset returns with assets as columns
            constraints: Optional min/max weight constraints per asset

        Returns:
            FractalWeights with computed allocations
        """
        if returns.empty:
            return FractalWeights(
                weights={},
                effective_scale=self.scales[0],
                regime=MarketRegime.REGIME_TRANSITION,
            )

        assets = list(returns.columns)
        n_assets = len(assets)

        # Detect regime from portfolio returns
        portfolio_returns = returns.mean(axis=1).values
        regime_snapshot = detect_regime(portfolio_returns)
        self._regime_history.append(regime_snapshot)

        # Compute Hurst exponent for each asset
        asset_hurst: Dict[str, float] = {}
        for asset in assets:
            asset_returns = returns[asset].dropna().values
            if len(asset_returns) >= 20:
                asset_hurst[asset] = compute_hurst_exponent(asset_returns)
            else:
                asset_hurst[asset] = 0.5

        # Determine effective scale based on regime
        if regime_snapshot.regime in (
            MarketRegime.TRENDING_UP,
            MarketRegime.TRENDING_DOWN,
        ):
            # Use longer scale for trending markets
            effective_scale = max(self.scales)
        elif regime_snapshot.regime == MarketRegime.MEAN_REVERTING:
            # Use shorter scale for mean-reverting markets
            effective_scale = min(self.scales)
        else:
            # Use medium scale for uncertain regimes
            effective_scale = self.scales[len(self.scales) // 2]

        # Compute covariance at effective scale
        if len(returns) >= effective_scale:
            cov_returns = returns.iloc[-effective_scale:]
        else:
            cov_returns = returns

        cov_matrix = cov_returns.cov().values
        variances = np.diag(cov_matrix)

        # Risk parity weights with Hurst adjustment
        inverse_vol = 1.0 / np.sqrt(np.maximum(variances, 1e-10))

        # Adjust weights based on Hurst exponent
        hurst_adjustment = np.array([asset_hurst.get(a, 0.5) for a in assets])

        # Favor trending assets in trending regime, mean-reverting in MR regime
        if regime_snapshot.regime in (
            MarketRegime.TRENDING_UP,
            MarketRegime.TRENDING_DOWN,
        ):
            hurst_weight = hurst_adjustment
        elif regime_snapshot.regime == MarketRegime.MEAN_REVERTING:
            hurst_weight = 1.0 - hurst_adjustment
        else:
            hurst_weight = np.ones(n_assets)

        raw_weights = inverse_vol * hurst_weight
        raw_weights = raw_weights / np.sum(raw_weights)

        # Apply constraints if provided
        if constraints:
            for i, asset in enumerate(assets):
                if asset in constraints:
                    min_w, max_w = constraints[asset]
                    raw_weights[i] = np.clip(raw_weights[i], min_w, max_w)
            # Renormalize
            raw_weights = raw_weights / np.sum(raw_weights)

        # Compute risk contribution
        marginal_contrib = cov_matrix @ raw_weights
        risk_contrib = raw_weights * marginal_contrib
        total_risk = np.sqrt(raw_weights @ cov_matrix @ raw_weights)
        if total_risk > 1e-10:
            risk_contrib = risk_contrib / total_risk

        weights_dict = {asset: float(w) for asset, w in zip(assets, raw_weights)}
        risk_contrib_dict = {asset: float(r) for asset, r in zip(assets, risk_contrib)}

        return FractalWeights(
            weights=weights_dict,
            effective_scale=effective_scale,
            regime=regime_snapshot.regime,
            risk_contribution=risk_contrib_dict,
        )

    def compute_rebalance_signal(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        threshold: float = 0.05,
    ) -> Dict[str, float]:
        """Compute rebalance trades based on regime-aware threshold.

        Args:
            current_weights: Current portfolio weights
            target_weights: Target portfolio weights
            threshold: Minimum deviation to trigger rebalance

        Returns:
            Dictionary of required weight changes per asset
        """
        trades: Dict[str, float] = {}

        for asset in set(current_weights.keys()) | set(target_weights.keys()):
            current = current_weights.get(asset, 0.0)
            target = target_weights.get(asset, 0.0)
            deviation = target - current

            if abs(deviation) >= threshold:
                trades[asset] = deviation

        return trades

    def get_regime_history(self) -> List[RegimeSnapshot]:
        """Return the history of detected regimes."""
        return list(self._regime_history)


__all__ = [
    "MarketRegime",
    "RegimeSnapshot",
    "FractalWeights",
    "FractalPortfolioAnalyzer",
    "add",
    "compute_hurst_exponent",
    "wavelet_decomposition",
    "detect_regime",
]
