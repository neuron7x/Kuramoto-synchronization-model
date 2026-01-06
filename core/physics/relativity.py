# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Relativity applied to market dynamics.

Relativity concepts provide reference frame transformations:
- Different observers (traders, algorithms) see markets differently
- Time dilation: fast trading vs slow investing perspectives
- Lorentz transformations for coordinate system changes
- Relativistic effects appear at high velocities (rapid price changes)
"""

from __future__ import annotations

import numpy as np

from .constants import PhysicsConstants


def lorentz_factor(
    velocity: float | np.ndarray,
    c: float = PhysicsConstants.MAX_VELOCITY,
) -> float | np.ndarray:
    """Compute Lorentz factor γ = 1 / sqrt(1 - v²/c²).
    
    The Lorentz factor describes time dilation and length contraction
    effects. In markets, it models how different timeframes perceive
    the same price movements.
    
    Args:
        velocity: Relative velocity (price change rate)
        c: Maximum velocity (speed of information)
        
    Returns:
        Lorentz factor value(s) (≥ 1)
        
    Example:
        >>> velocity = 0.5  # 50% of max velocity
        >>> gamma = lorentz_factor(velocity)
        >>> print(f"Time dilation factor: {gamma:.3f}")
    """
    v_ratio = velocity / c
    
    # Clip to prevent numerical issues
    v_ratio_sq = np.minimum(v_ratio ** 2, 0.9999)
    
    gamma = 1.0 / np.sqrt(1.0 - v_ratio_sq)
    
    return gamma


def lorentz_transform(
    position: float | np.ndarray,
    time: float | np.ndarray,
    velocity: float,
    c: float = PhysicsConstants.MAX_VELOCITY,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Apply Lorentz transformation to position and time coordinates.
    
    Transforms coordinates from one reference frame to another moving
    at constant velocity. In markets, this changes perspective from
    one trading timeframe to another.
    
    x' = γ(x - vt)
    t' = γ(t - vx/c²)
    
    Args:
        position: Position in original frame (e.g., price level)
        time: Time in original frame
        velocity: Relative velocity between frames
        c: Maximum velocity
        
    Returns:
        Tuple of (transformed_position, transformed_time)
        
    Example:
        >>> # Transform from daily to intraday perspective
        >>> pos, t = lorentz_transform(position=100.0, time=1.0, velocity=0.3)
    """
    gamma = lorentz_factor(velocity, c)
    
    # Lorentz transformation
    x_prime = gamma * (position - velocity * time)
    t_prime = gamma * (time - velocity * position / (c ** 2))
    
    return x_prime, t_prime


def relativistic_momentum(
    mass: float | np.ndarray,
    velocity: float | np.ndarray,
    c: float = PhysicsConstants.MAX_VELOCITY,
) -> float | np.ndarray:
    """Compute relativistic momentum p = γmv.
    
    At high velocities, momentum increases more than linearly with
    velocity. In markets, this models momentum amplification during
    rapid price movements.
    
    Args:
        mass: Rest mass (market liquidity)
        velocity: Velocity (price change rate)
        c: Maximum velocity
        
    Returns:
        Relativistic momentum value(s)
        
    Example:
        >>> mass = 1000.0
        >>> velocity = 0.8  # 80% of max velocity
        >>> p_rel = relativistic_momentum(mass, velocity)
        >>> p_classical = mass * velocity
        >>> print(f"Momentum amplification: {p_rel / p_classical:.2f}x")
    """
    gamma = lorentz_factor(velocity, c)
    return gamma * mass * velocity


def compute_relative_time(
    proper_time: float | np.ndarray,
    velocity: float | np.ndarray,
    c: float = PhysicsConstants.MAX_VELOCITY,
) -> float | np.ndarray:
    """Compute relative time with time dilation t = γτ.
    
    Time dilation: moving clocks run slower. In markets, this models
    how different trading speeds perceive time differently.
    
    Args:
        proper_time: Time in moving frame (fast trading perspective)
        velocity: Relative velocity
        c: Maximum velocity
        
    Returns:
        Time in stationary frame (slow trading perspective)
        
    Example:
        >>> # 1 hour in HFT perspective
        >>> proper_time = 1.0
        >>> velocity = 0.9  # Very high velocity
        >>> observed_time = compute_relative_time(proper_time, velocity)
        >>> print(f"Appears as {observed_time:.2f} hours to slow traders")
    """
    gamma = lorentz_factor(velocity, c)
    return gamma * proper_time


def velocity_addition(
    v1: float,
    v2: float,
    c: float = PhysicsConstants.MAX_VELOCITY,
) -> float:
    """Compute relativistic velocity addition.
    
    In relativity, velocities don't add linearly. This prevents
    exceeding the speed of information.
    
    v = (v1 + v2) / (1 + v1*v2/c²)
    
    Args:
        v1: First velocity
        v2: Second velocity
        c: Maximum velocity
        
    Returns:
        Combined velocity (always < c)
        
    Example:
        >>> v1 = 0.8 * c  # 80% of max
        >>> v2 = 0.8 * c  # 80% of max
        >>> v_total = velocity_addition(v1, v2)
        >>> # v_total < c (information speed limit preserved)
    """
    numerator = v1 + v2
    denominator = 1.0 + (v1 * v2) / (c ** 2)
    
    # Handle division by zero
    if abs(denominator) < 1e-10:
        return c
    
    v_combined = numerator / denominator
    
    # Ensure doesn't exceed speed of information
    return min(abs(v_combined), c) * np.sign(v_combined)


def time_dilation_factor(
    velocity: float | np.ndarray,
    c: float = PhysicsConstants.MAX_VELOCITY,
) -> float | np.ndarray:
    """Compute time dilation factor (same as Lorentz factor).
    
    Convenience function for clarity when specifically computing
    time dilation effects.
    
    Args:
        velocity: Relative velocity
        c: Maximum velocity
        
    Returns:
        Time dilation factor (≥ 1)
    """
    return lorentz_factor(velocity, c)


__all__ = [
    "lorentz_factor",
    "lorentz_transform",
    "relativistic_momentum",
    "compute_relative_time",
    "velocity_addition",
    "time_dilation_factor",
]
