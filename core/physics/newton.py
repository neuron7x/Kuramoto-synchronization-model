# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Newton's Laws of Motion applied to market dynamics.

Newton's Laws provide a framework for understanding market momentum, forces,
and inertia:

1. First Law (Inertia): Prices tend to maintain their momentum unless acted
   upon by external forces (news, orders, etc.)

2. Second Law (F=ma): Market force equals the rate of change of momentum,
   relating order flow to price acceleration

3. Third Law: For every market action, there's an equal and opposite reaction
   (buy pressure creates sell pressure)
"""

from __future__ import annotations

import numpy as np


def compute_momentum(
    mass: float | np.ndarray,
    velocity: float | np.ndarray,
) -> float | np.ndarray:
    """Compute market momentum (p = mv).

    In market context:
    - mass represents liquidity, market cap, or trading volume
    - velocity represents rate of price change
    - momentum represents the "strength" of a price movement

    Args:
        mass: Market mass (liquidity, volume, or capitalization)
        velocity: Price velocity (rate of change)

    Returns:
        Market momentum value(s)

    Example:
        >>> mass = 1000.0  # Market cap in millions
        >>> velocity = 0.05  # 5% price change per day
        >>> momentum = compute_momentum(mass, velocity)
        >>> print(f"Momentum: {momentum}")
    """
    return mass * velocity


def compute_force(
    mass: float | np.ndarray,
    acceleration: float | np.ndarray,
) -> float | np.ndarray:
    """Compute market force using Newton's 2nd Law (F = ma).

    In market context:
    - force represents order flow pressure
    - mass represents market liquidity
    - acceleration represents rate of change of price velocity

    Args:
        mass: Market mass (liquidity or volume)
        acceleration: Price acceleration (rate of velocity change)

    Returns:
        Market force value(s)

    Example:
        >>> mass = 1000.0
        >>> acceleration = 0.01  # Accelerating price change
        >>> force = compute_force(mass, acceleration)
    """
    return mass * acceleration


def compute_acceleration(
    force: float | np.ndarray,
    mass: float | np.ndarray,
) -> float | np.ndarray:
    """Compute market acceleration from force (a = F/m).

    In market context, this shows how order flow (force) affects
    price movement given market liquidity (mass).

    Args:
        force: Market force (order flow pressure)
        mass: Market mass (liquidity)

    Returns:
        Market acceleration value(s)

    Example:
        >>> force = 50.0  # Buy pressure
        >>> mass = 1000.0  # Market liquidity
        >>> acceleration = compute_acceleration(force, mass)
    """
    # Protect against division by zero
    mass_safe = (
        np.where(np.abs(mass) < 1e-10, 1e-10, mass)
        if isinstance(mass, np.ndarray)
        else (mass if abs(mass) >= 1e-10 else 1e-10)
    )

    return force / mass_safe


def compute_price_velocity(
    prices: np.ndarray,
    dt: float = 1.0,
) -> np.ndarray:
    """Compute price velocity as rate of price change.

    Velocity is computed as the first derivative of price with respect to time,
    using finite differences for discrete price series.

    Args:
        prices: Array of price values over time
        dt: Time step between observations (default: 1.0)

    Returns:
        Array of velocity values (same length as prices, first value is 0)

    Example:
        >>> prices = np.array([100, 102, 105, 104, 107])
        >>> velocity = compute_price_velocity(prices)
        >>> print(velocity)
        [0.  2.  3. -1.  3.]
    """
    prices_arr = np.asarray(prices, dtype=float)

    if prices_arr.size < 2:
        return np.zeros_like(prices_arr)

    # Compute forward differences
    velocity = np.zeros_like(prices_arr)
    velocity[1:] = np.diff(prices_arr) / dt

    return velocity


def compute_price_acceleration(
    prices: np.ndarray,
    dt: float = 1.0,
) -> np.ndarray:
    """Compute price acceleration as rate of velocity change.

    Acceleration is the second derivative of price, showing how quickly
    momentum is building or dissipating.

    Args:
        prices: Array of price values over time
        dt: Time step between observations (default: 1.0)

    Returns:
        Array of acceleration values (first two values are 0)

    Example:
        >>> prices = np.array([100, 102, 105, 104, 107])
        >>> acceleration = compute_price_acceleration(prices)
    """
    velocity = compute_price_velocity(prices, dt)

    if velocity.size < 2:
        return np.zeros_like(velocity)

    # Compute acceleration as change in velocity
    acceleration = np.zeros_like(velocity)
    acceleration[1:] = np.diff(velocity) / dt

    return acceleration


__all__ = [
    "compute_momentum",
    "compute_force",
    "compute_acceleration",
    "compute_price_velocity",
    "compute_price_acceleration",
]
