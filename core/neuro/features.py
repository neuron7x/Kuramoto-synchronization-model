"""Streaming feature extractors for neurobiologically-inspired market analysis.

This module provides efficient, numerically stable implementations of common
time-series features used throughout the neuro-economic trading framework.
All functions operate in O(1) time with float32 precision for real-time streaming.

Key Components:
    ema_update: Single-step exponential moving average update
    ewvar_update: EWMA variance estimation for residuals
    EWEntropyConfig: Configuration for entropy estimator
    EWEntropy: Streaming Shannon entropy with exponential decay

The entropy estimator uses a fixed-bin histogram approach with exponential
weighting to capture non-stationarity in market distributions. This provides
a computationally efficient measure of predictability that can be updated
in real-time without storing historical data.

All implementations prioritize numerical stability and minimal memory footprint,
making them suitable for high-frequency trading applications.

Example:
    >>> prev_ema = 100.0
    >>> new_price = 101.5
    >>> updated = ema_update(prev_ema, new_price, span=20)
    >>>
    >>> entropy = EWEntropy(EWEntropyConfig())
    >>> H = entropy.update(return_value)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Float = np.float32


def ema_update(prev: float, x: float, span: int) -> float:
    """One-step EMA update (float32, O(1))."""
    alpha = Float(2.0 / (1.0 + span))
    return Float((1.0 - alpha) * Float(prev) + alpha * Float(x))


def ewvar_update(prev_var: float, pe: float, lam: float, eps: float = 1e-12) -> float:
    """EWMA variance update for residuals (float32, O(1))."""
    lam = Float(lam)
    return Float(
        lam * Float(prev_var) + (1.0 - lam) * (Float(pe) * Float(pe)) + Float(eps)
    )


@dataclass
class EWEntropyConfig:
    bins: int = 32
    xmin: float = -0.05
    xmax: float = 0.05
    decay: float = 0.975
    eps: float = 1e-12


class EWEntropy:
    """Exponentially-weighted discrete Shannon entropy over fixed bins.
    Streaming, O(1), float32."""

    def __init__(self, cfg: EWEntropyConfig):
        self.cfg = cfg
        self._counts = np.full(cfg.bins, Float(1e-6), dtype=Float)  # small prior
        self._sum = Float(np.sum(self._counts))
        self._p = self._counts / self._sum
        self._H = Float(0.0)
        self._update_entropy()

    def _bin_index(self, x: float) -> int:
        r = (Float(x) - self.cfg.xmin) / (self.cfg.xmax - self.cfg.xmin + 1e-12)
        idx = int(np.floor(float(r) * self.cfg.bins))
        return max(0, min(self.cfg.bins - 1, idx))

    def _update_entropy(self) -> None:
        p = self._p + Float(self.cfg.eps)
        self._H = Float(-np.sum(p * np.log(p)))

    def update(self, x: float) -> float:
        self._counts *= Float(self.cfg.decay)
        self._counts[self._bin_index(x)] += Float(1.0)
        self._sum = Float(np.sum(self._counts))
        self._p = self._counts / self._sum
        self._update_entropy()
        return float(self._H)

    @property
    def value(self) -> float:
        return float(self._H)


class EWMomentum:
    """Exponentially-weighted momentum with dual time-scale filtering.

    Computes momentum as the difference between fast and slow EMAs, providing
    a smoothed directional signal that adapts to recent price changes while
    filtering noise. O(1) updates, float32 stable.

    Modern enhancement: Dual time-scale design reduces false signals compared
    to single-EMA momentum, especially during ranging markets.
    """

    __slots__ = ("_fast_span", "_slow_span", "_fast", "_slow", "_initialized")

    def __init__(self, fast_span: int = 12, slow_span: int = 26) -> None:
        """Initialize momentum tracker.

        Args:
            fast_span: Span for fast EMA (lower = more responsive).
            slow_span: Span for slow EMA (higher = more stable).

        Raises:
            ValueError: If fast_span >= slow_span or either <= 0.
        """
        if fast_span >= slow_span:
            raise ValueError(
                f"fast_span ({fast_span}) must be < slow_span ({slow_span})"
            )
        if fast_span <= 0 or slow_span <= 0:
            raise ValueError("Spans must be positive")

        self._fast_span = fast_span
        self._slow_span = slow_span
        self._fast = Float(0.0)
        self._slow = Float(0.0)
        self._initialized = False

    def update(self, x: float) -> float:
        """Update with new observation and return momentum.

        Args:
            x: New price or return observation.

        Returns:
            Momentum signal (fast EMA - slow EMA).
        """
        x_f = Float(x)

        if not self._initialized:
            self._fast = x_f
            self._slow = x_f
            self._initialized = True
            return 0.0

        self._fast = ema_update(self._fast, x_f, self._fast_span)
        self._slow = ema_update(self._slow, x_f, self._slow_span)

        return float(self._fast - self._slow)

    @property
    def momentum(self) -> float:
        """Current momentum signal."""
        return float(self._fast - self._slow) if self._initialized else 0.0

    def reset(self) -> None:
        """Reset to initial state."""
        self._fast = Float(0.0)
        self._slow = Float(0.0)
        self._initialized = False


class EWZScore:
    """Exponentially-weighted z-score for online standardization.

    Computes running z-score using EWMA mean and variance, enabling online
    detection of outliers and regime shifts. O(1) updates, float32 stable.

    The z-score indicates how many standard deviations the current observation
    is from the exponential mean. Useful for threshold-based trading signals
    and anomaly detection in real-time systems.
    """

    __slots__ = ("_span", "_lambda", "_mean", "_var", "_initialized", "_eps")

    def __init__(
        self, span: int = 50, lambda_var: float = 0.94, eps: float = 1e-8
    ) -> None:
        """Initialize z-score tracker.

        Args:
            span: EMA span for mean calculation.
            lambda_var: Decay for variance EWMA (higher = more stable).
            eps: Small constant for numerical stability.

        Raises:
            ValueError: If parameters are invalid.
        """
        if span <= 0:
            raise ValueError(f"span must be positive, got {span}")
        if not (0 < lambda_var < 1):
            raise ValueError(f"lambda_var must be in (0, 1), got {lambda_var}")
        if eps <= 0:
            raise ValueError(f"eps must be positive, got {eps}")

        self._span = span
        self._lambda = Float(lambda_var)
        self._mean = Float(0.0)
        self._var = Float(1.0)
        self._initialized = False
        self._eps = Float(eps)

    def update(self, x: float) -> float:
        """Update with new observation and return z-score.

        Args:
            x: New observation.

        Returns:
            Z-score (standardized value).
        """
        x_f = Float(x)

        if not self._initialized:
            self._mean = x_f
            self._var = Float(1.0)
            self._initialized = True
            return 0.0

        # Update mean
        prev_mean = self._mean
        self._mean = ema_update(self._mean, x_f, self._span)

        # Update variance using prediction error
        pe = x_f - prev_mean
        self._var = ewvar_update(
            self._var, float(pe), float(self._lambda), float(self._eps)
        )

        # Compute z-score
        std = Float(np.sqrt(self._var))
        z = (x_f - self._mean) / (std + self._eps)

        return float(z)

    @property
    def mean(self) -> float:
        """Current EWMA mean."""
        return float(self._mean)

    @property
    def std(self) -> float:
        """Current EWMA standard deviation."""
        return float(np.sqrt(self._var))

    def reset(self) -> None:
        """Reset to initial state."""
        self._mean = Float(0.0)
        self._var = Float(1.0)
        self._initialized = False


class EWSkewness:
    """Exponentially-weighted skewness for distribution asymmetry detection.

    Tracks the third standardized moment to detect asymmetry in return
    distributions. Positive skew indicates tail risk on upside, negative
    skew indicates downside tail risk. O(1) updates, float32 stable.

    Critical for risk management: negative skewness in returns signals
    potential for large drawdowns (common in equity markets).
    """

    __slots__ = ("_span", "_lambda", "_mean", "_m2", "_m3", "_n", "_eps")

    def __init__(
        self, span: int = 50, lambda_decay: float = 0.94, eps: float = 1e-8
    ) -> None:
        """Initialize skewness tracker.

        Args:
            span: EMA span for mean.
            lambda_decay: Decay for moment updates.
            eps: Numerical stability constant.
        """
        if span <= 0:
            raise ValueError(f"span must be positive, got {span}")
        if not (0 < lambda_decay < 1):
            raise ValueError(f"lambda_decay must be in (0, 1), got {lambda_decay}")

        self._span = span
        self._lambda = Float(lambda_decay)
        self._mean = Float(0.0)
        self._m2 = Float(0.0)  # Second central moment
        self._m3 = Float(0.0)  # Third central moment
        self._n = 0
        self._eps = Float(eps)

    def update(self, x: float) -> float:
        """Update with new observation and return skewness.

        Args:
            x: New observation.

        Returns:
            Skewness estimate (NaN if insufficient data).
        """
        x_f = Float(x)
        self._n += 1

        if self._n == 1:
            self._mean = x_f
            return 0.0

        # Update moments using exponential weighting
        delta = x_f - self._mean
        self._mean = ema_update(self._mean, x_f, self._span)
        delta2 = x_f - self._mean

        # Update second and third central moments
        lam = self._lambda
        self._m2 = lam * self._m2 + (1.0 - lam) * delta * delta2
        self._m3 = lam * self._m3 + (1.0 - lam) * delta * delta * delta2

        # Compute skewness
        if self._m2 < self._eps:
            return 0.0

        skew = self._m3 / (Float(np.power(self._m2, 1.5)) + self._eps)
        return float(skew)

    @property
    def skewness(self) -> float:
        """Current skewness estimate."""
        if self._n < 2 or self._m2 < self._eps:
            return 0.0
        return float(self._m3 / (Float(np.power(self._m2, 1.5)) + self._eps))

    def reset(self) -> None:
        """Reset to initial state."""
        self._mean = Float(0.0)
        self._m2 = Float(0.0)
        self._m3 = Float(0.0)
        self._n = 0


__all__ = [
    "ema_update",
    "ewvar_update",
    "EWEntropyConfig",
    "EWEntropy",
    "EWMomentum",
    "EWZScore",
    "EWSkewness",
]
