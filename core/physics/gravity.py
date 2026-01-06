# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Universal Gravitation applied to market dynamics.

The law of universal gravitation provides an analogy for market attraction:
- Large market entities (high liquidity) attract smaller ones
- Force decreases with distance (price separation)
- Used for correlation, cluster detection, and market regime analysis
"""

from __future__ import annotations

import numpy as np

from .constants import PhysicsConstants


def gravitational_force(
    mass1: float | np.ndarray,
    mass2: float | np.ndarray,
    distance: float | np.ndarray,
    G: float = PhysicsConstants.GRAVITATIONAL_CONSTANT,
) -> float | np.ndarray:
    """Compute gravitational force between two market entities.
    
    F = G * (m1 * m2) / r²
    
    In market context:
    - mass represents market cap, volume, or liquidity
    - distance represents price separation or correlation distance
    - force represents attraction/correlation strength
    
    Args:
        mass1: Mass of first market entity
        mass2: Mass of second market entity
        distance: Distance between entities (price or correlation space)
        G: Gravitational constant (default: normalized to 1.0)
        
    Returns:
        Gravitational force value(s)
        
    Example:
        >>> mass1 = 1000.0  # Large cap stock
        >>> mass2 = 100.0   # Small cap stock
        >>> distance = 50.0  # Price separation
        >>> force = gravitational_force(mass1, mass2, distance)
    """
    # Prevent division by zero with minimum distance
    distance_safe = np.maximum(
        np.abs(distance),
        PhysicsConstants.MIN_DISTANCE
    )
    
    return G * (mass1 * mass2) / (distance_safe ** 2)


def gravitational_potential(
    mass: float | np.ndarray,
    distance: float | np.ndarray,
    G: float = PhysicsConstants.GRAVITATIONAL_CONSTANT,
) -> float | np.ndarray:
    """Compute gravitational potential energy.
    
    U = -G * m / r
    
    Negative sign indicates attractive potential (energy decreases as
    entities move closer).
    
    Args:
        mass: Mass of market entity
        distance: Distance from the entity
        G: Gravitational constant
        
    Returns:
        Gravitational potential value(s)
        
    Example:
        >>> mass = 1000.0
        >>> distance = 50.0
        >>> potential = gravitational_potential(mass, distance)
    """
    distance_safe = np.maximum(
        np.abs(distance),
        PhysicsConstants.MIN_DISTANCE
    )
    
    return -G * mass / distance_safe


def compute_market_gravity(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    G: float = PhysicsConstants.GRAVITATIONAL_CONSTANT,
) -> np.ndarray:
    """Compute gravitational field strength at each price point.
    
    This represents the "pull" exerted by volume-weighted price levels,
    useful for identifying support/resistance and mean reversion levels.
    
    Args:
        prices: Array of price values
        volumes: Optional volume weights (defaults to uniform)
        G: Gravitational constant
        
    Returns:
        Array of gravitational field strength at each point
        
    Example:
        >>> prices = np.array([100, 102, 105, 104, 107])
        >>> volumes = np.array([1000, 800, 1200, 900, 1100])
        >>> gravity = compute_market_gravity(prices, volumes)
    """
    prices_arr = np.asarray(prices, dtype=float)
    n = prices_arr.size
    
    if n == 0:
        return np.array([])
    
    # Use uniform volumes if not provided
    if volumes is None:
        volumes_arr = np.ones(n, dtype=float)
    else:
        volumes_arr = np.asarray(volumes, dtype=float)
        if volumes_arr.size != n:
            raise ValueError("prices and volumes must have same length")
    
    # Compute gravitational field at each point as sum of forces
    # from all other points
    gravity = np.zeros(n, dtype=float)
    
    for i in range(n):
        for j in range(n):
            if i != j:
                distance = abs(prices_arr[i] - prices_arr[j])
                force = gravitational_force(
                    volumes_arr[j],
                    1.0,  # Test mass
                    distance,
                    G
                )
                # Add contribution with sign based on direction
                direction = np.sign(prices_arr[j] - prices_arr[i])
                gravity[i] += force * direction
    
    return gravity


def market_gravity_center(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
) -> float:
    """Compute the center of gravity for market prices.
    
    This is the volume-weighted average price (VWAP), representing the
    equilibrium point around which prices are "pulled".
    
    Args:
        prices: Array of price values
        volumes: Optional volume weights
        
    Returns:
        Center of gravity (VWAP)
        
    Example:
        >>> prices = np.array([100, 102, 105])
        >>> volumes = np.array([1000, 800, 1200])
        >>> center = market_gravity_center(prices, volumes)
    """
    prices_arr = np.asarray(prices, dtype=float)
    
    if prices_arr.size == 0:
        return 0.0
    
    if volumes is None:
        return float(np.mean(prices_arr))
    
    volumes_arr = np.asarray(volumes, dtype=float)
    total_volume = np.sum(volumes_arr)
    
    if total_volume == 0:
        return float(np.mean(prices_arr))
    
    return float(np.sum(prices_arr * volumes_arr) / total_volume)


__all__ = [
    "gravitational_force",
    "gravitational_potential",
    "compute_market_gravity",
    "market_gravity_center",
]
