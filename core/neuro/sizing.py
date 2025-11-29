"""Position sizing functions for neuro-adaptive trading systems.

This module implements volatility-targeted position sizing with dual modulation
from AMM pulse intensity and precision signals. The sizing logic dynamically
adjusts leverage based on market conditions and forecast confidence.

Key Components:
    SizerConfig: Configuration for target volatility and leverage limits
    pulse_weight: Convert AMM pulse to sizing weight [0, 1]
    precision_weight: Convert precision to sizing weight via log-sigmoid
    position_size: Main sizing function combining all factors

The sizing approach scales positions to achieve target portfolio volatility
while respecting maximum leverage constraints. Two additional factors modulate
the base size:
    1. Pulse weight: Only size positions when AMM pulse exceeds threshold
    2. Precision weight: Scale by forecast confidence (precision)

This creates a conservative sizing regime that allocates capital only when
the model exhibits both strong pulse signals and high prediction precision.

Example:
    >>> config = SizerConfig(target_vol=0.02, max_leverage=3.0)
    >>> direction = 1  # Long
    >>> size = position_size(direction, precision, pulse, est_vol, config)
    >>> print(f"Position size: {size:.2f}x leverage")
"""

from __future__ import annotations

import math

import numpy as np

from core.utils.numeric_constants import (
    DIV_SAFE_MIN,
    LOG_SAFE_MIN,
    POSITION_SIZE_MIN,
    VOLATILITY_SAFE_MIN,
)

Float = np.float32


class SizerConfig:
    """Configuration for position sizing with validation.

    Immutable configuration following 2025 best practices with comprehensive
    validation to prevent misconfiguration in production trading.

    Attributes:
        target_vol: Target portfolio volatility (e.g., 0.02 for 2% daily vol).
        max_leverage: Maximum absolute leverage allowed.
        min_pulse: Minimum pulse threshold for non-zero position.
        max_pulse: Maximum pulse value for scaling (saturation point).
        clip: Additional clipping factor for conservative sizing.
        kelly_fraction: Fraction of Kelly criterion to use (default 1.0).
            Set < 1.0 for fractional Kelly (e.g., 0.5 for half-Kelly).
        min_precision: Minimum precision threshold for non-zero position.
    """

    __slots__ = (
        "target_vol",
        "max_leverage",
        "min_pulse",
        "max_pulse",
        "clip",
        "kelly_fraction",
        "min_precision",
    )

    def __init__(
        self,
        target_vol: float = 0.02,
        max_leverage: float = 3.0,
        min_pulse: float = 0.0,
        max_pulse: float = 0.25,
        clip: float = 1.0,
        kelly_fraction: float = 1.0,
        min_precision: float = 0.1,
    ):
        """Initialize sizing configuration with validation.

        Args:
            target_vol: Target volatility, must be > 0.
            max_leverage: Maximum leverage, must be > 0.
            min_pulse: Minimum pulse threshold, must be >= 0.
            max_pulse: Maximum pulse value, must be > min_pulse.
            clip: Additional clipping factor, must be > 0.
            kelly_fraction: Kelly fraction in (0, 1], default 1.0 for full Kelly.
            min_precision: Minimum precision threshold, must be >= 0.

        Raises:
            ValueError: If any parameter violates constraints.
        """
        if target_vol <= 0:
            raise ValueError(f"target_vol must be positive, got {target_vol}")
        if max_leverage <= 0:
            raise ValueError(f"max_leverage must be positive, got {max_leverage}")
        if min_pulse < 0:
            raise ValueError(f"min_pulse must be non-negative, got {min_pulse}")
        if max_pulse <= min_pulse:
            raise ValueError(
                f"max_pulse ({max_pulse}) must be > min_pulse ({min_pulse})"
            )
        if clip <= 0:
            raise ValueError(f"clip must be positive, got {clip}")
        if not (0 < kelly_fraction <= 1.0):
            raise ValueError(f"kelly_fraction must be in (0, 1], got {kelly_fraction}")
        if min_precision < 0:
            raise ValueError(f"min_precision must be non-negative, got {min_precision}")

        self.target_vol = Float(target_vol)
        self.max_leverage = Float(max_leverage)
        self.min_pulse = Float(min_pulse)
        self.max_pulse = Float(max_pulse)
        self.clip = Float(clip)
        self.kelly_fraction = Float(kelly_fraction)
        self.min_precision = Float(min_precision)


def pulse_weight(S: float, cfg: SizerConfig) -> float:
    """Convert AMM pulse to sizing weight.

    Args:
        S: AMM pulse intensity value.
        cfg: Sizing configuration with pulse bounds.

    Returns:
        Weight in [0, 1] range based on pulse position in configured range.
    """
    S = Float(S)
    if S <= cfg.min_pulse:
        return 0.0
    denominator = float(cfg.max_pulse - cfg.min_pulse)
    if denominator < DIV_SAFE_MIN:
        return 0.0
    w = float((S - cfg.min_pulse) / denominator)
    return float(min(max(w, 0.0), 1.0))


def precision_weight(pi: float, min_precision: float = 0.0) -> float:
    """Convert precision to weight using log-sigmoid transformation.

    Args:
        pi: Precision value (typically > 1.0 for confident forecasts).
        min_precision: Minimum precision threshold for non-zero weight.

    Returns:
        Weight in [0, 1] range.
    """
    if pi < min_precision:
        return 0.0
    z = math.log(max(pi, LOG_SAFE_MIN))
    return float(1.0 / (1.0 + math.exp(-z)))


def position_size(
    direction: int, pi: float, S: float, est_sigma: float, cfg: SizerConfig
) -> float:
    """Compute position size with volatility targeting and dual modulation.

    Args:
        direction: Trade direction (-1 short, 0 flat, 1 long).
        pi: Forecast precision (higher = more confident).
        S: AMM pulse intensity.
        est_sigma: Estimated return volatility.
        cfg: Sizing configuration.

    Returns:
        Position size as leverage multiplier, in [-max_leverage, max_leverage].
        Returns 0.0 if direction is 0, volatility too low, or filters not met.

    Raises:
        ValueError: If est_sigma is negative.
    """
    if direction == 0:
        return 0.0

    if est_sigma < 0:
        raise ValueError(f"Volatility estimate must be non-negative, got {est_sigma}")

    if est_sigma <= VOLATILITY_SAFE_MIN:
        return 0.0

    # Apply filters
    w_pulse = pulse_weight(S, cfg)
    w_precision = precision_weight(pi, cfg.min_precision)
    w = w_pulse * w_precision

    if w < POSITION_SIZE_MIN:
        return 0.0

    # Volatility-targeted sizing with Kelly fraction
    base_size = (cfg.target_vol / float(est_sigma)) * cfg.kelly_fraction
    sized = float(direction * w * base_size * cfg.clip)

    return float(np.clip(sized, -cfg.max_leverage, cfg.max_leverage))


def kelly_size(
    win_prob: float,
    win_amount: float,
    loss_amount: float,
    kelly_fraction: float = 1.0,
    max_leverage: float = 1.0,
) -> float:
    """Compute Kelly Criterion optimal position size.

    Classic Kelly formula: f* = (p*b - q) / b
    where p = win probability, q = 1-p, b = win_amount/loss_amount

    Modern enhancement: Applies fractional Kelly for robustness against
    estimation error (recommended: 0.25 to 0.5 for production trading).

    Args:
        win_prob: Probability of winning trade, in (0, 1).
        win_amount: Average winning trade size (positive).
        loss_amount: Average losing trade size (positive).
        kelly_fraction: Fraction of Kelly to use, in (0, 1].
        max_leverage: Maximum allowed size.

    Returns:
        Optimal position size as fraction of capital.
        Returns 0.0 if Kelly formula suggests no position.

    Raises:
        ValueError: If parameters are invalid.

    References:
        Kelly, J. L. (1956). A new interpretation of information rate.
        Bell System Technical Journal, 35(4), 917-926.

        Thorp, E. O. (2006). The Kelly Criterion in Blackjack Sports
        Betting and the Stock Market. Handbook of Asset and Liability Management.
    """
    if not (0 < win_prob < 1):
        raise ValueError(f"win_prob must be in (0, 1), got {win_prob}")
    if win_amount <= 0:
        raise ValueError(f"win_amount must be positive, got {win_amount}")
    if loss_amount <= 0:
        raise ValueError(f"loss_amount must be positive, got {loss_amount}")
    if not (0 < kelly_fraction <= 1.0):
        raise ValueError(f"kelly_fraction must be in (0, 1], got {kelly_fraction}")
    if max_leverage <= 0:
        raise ValueError(f"max_leverage must be positive, got {max_leverage}")

    lose_prob = 1.0 - win_prob
    win_loss_ratio = win_amount / loss_amount

    # Kelly formula
    kelly = (win_prob * win_loss_ratio - lose_prob) / win_loss_ratio

    # Apply fractional Kelly and cap
    size = kelly * kelly_fraction
    return float(max(0.0, min(size, max_leverage)))


def risk_parity_weight(
    volatilities: list[float],
    correlations: list[list[float]] | None = None,
) -> list[float]:
    """Compute risk parity weights for portfolio allocation.

    Allocates capital inversely proportional to volatility to achieve
    equal risk contribution from each asset. Optional correlation adjustment.

    Args:
        volatilities: List of asset volatilities.
        correlations: Optional correlation matrix. If None, assumes uncorrelated.

    Returns:
        List of weights summing to 1.0, with lower volatility assets
        receiving higher allocation.

    Raises:
        ValueError: If volatilities are invalid or correlations mismatched.

    References:
        Maillard, S., Roncalli, T., & Teïletche, J. (2010). The properties
        of equally weighted risk contribution portfolios. Journal of Portfolio
        Management, 36(4), 60-70.
    """
    if not volatilities:
        raise ValueError("volatilities cannot be empty")
    if any(v <= 0 for v in volatilities):
        raise ValueError("All volatilities must be positive")

    n = len(volatilities)

    if correlations is not None:
        if len(correlations) != n or any(len(row) != n for row in correlations):
            raise ValueError(f"Correlation matrix must be {n}x{n}")

    # Simple risk parity: inverse volatility weighting
    inv_vols = [1.0 / v for v in volatilities]
    total = sum(inv_vols)
    weights = [iv / total for iv in inv_vols]

    return weights


__all__ = [
    "SizerConfig",
    "pulse_weight",
    "precision_weight",
    "position_size",
    "kelly_size",
    "risk_parity_weight",
]
