# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Conservation laws applied to market dynamics.

Conservation principles provide stability constraints:
- Energy conservation: Total market energy remains constant in closed systems
- Momentum conservation: Total momentum is preserved absent external forces
- These provide sanity checks and noise reduction for market models
"""

from __future__ import annotations

import numpy as np

from .constants import PhysicsConstants


def compute_market_energy(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    velocities: np.ndarray | None = None,
) -> float:
    """Compute total market energy (kinetic + potential).
    
    E_total = E_kinetic + E_potential
    
    Where:
    - E_kinetic = (1/2) * m * v² (energy of price movement)
    - E_potential = m * g * h (energy of position, using VWAP as reference)
    
    Args:
        prices: Array of price values
        volumes: Volume weights (mass analog)
        velocities: Price velocities (if None, computed from prices)
        
    Returns:
        Total market energy
        
    Example:
        >>> prices = np.array([100, 102, 105, 104, 107])
        >>> volumes = np.array([1000, 800, 1200, 900, 1100])
        >>> energy = compute_market_energy(prices, volumes)
    """
    prices_arr = np.asarray(prices, dtype=float)
    n = prices_arr.size
    
    if n == 0:
        return 0.0
    
    # Use uniform volumes if not provided
    if volumes is None:
        volumes_arr = np.ones(n, dtype=float)
    else:
        volumes_arr = np.asarray(volumes, dtype=float)
    
    # Compute velocities if not provided
    if velocities is None:
        if n < 2:
            velocities_arr = np.zeros(n, dtype=float)
        else:
            velocities_arr = np.zeros(n, dtype=float)
            velocities_arr[1:] = np.diff(prices_arr)
    else:
        velocities_arr = np.asarray(velocities, dtype=float)
    
    # Kinetic energy: (1/2) * m * v²
    kinetic_energy = 0.5 * np.sum(volumes_arr * velocities_arr ** 2)
    
    # Potential energy: m * g * h (height = distance from VWAP)
    vwap = np.average(prices_arr, weights=volumes_arr)
    heights = prices_arr - vwap
    potential_energy = np.sum(volumes_arr * heights)
    
    return float(kinetic_energy + potential_energy)


def compute_market_momentum(
    prices: np.ndarray,
    volumes: np.ndarray | None = None,
    velocities: np.ndarray | None = None,
) -> float:
    """Compute total market momentum (p = Σ m*v).
    
    Args:
        prices: Array of price values
        volumes: Volume weights (mass analog)
        velocities: Price velocities (if None, computed from prices)
        
    Returns:
        Total market momentum
        
    Example:
        >>> prices = np.array([100, 102, 105, 104, 107])
        >>> volumes = np.array([1000, 800, 1200, 900, 1100])
        >>> momentum = compute_market_momentum(prices, volumes)
    """
    prices_arr = np.asarray(prices, dtype=float)
    n = prices_arr.size
    
    if n == 0:
        return 0.0
    
    # Use uniform volumes if not provided
    if volumes is None:
        volumes_arr = np.ones(n, dtype=float)
    else:
        volumes_arr = np.asarray(volumes, dtype=float)
    
    # Compute velocities if not provided
    if velocities is None:
        if n < 2:
            velocities_arr = np.zeros(n, dtype=float)
        else:
            velocities_arr = np.zeros(n, dtype=float)
            velocities_arr[1:] = np.diff(prices_arr)
    else:
        velocities_arr = np.asarray(velocities, dtype=float)
    
    # Total momentum
    momentum = np.sum(volumes_arr * velocities_arr)
    
    return float(momentum)


def check_energy_conservation(
    energy_before: float,
    energy_after: float,
    tolerance: float = 0.01,
) -> tuple[bool, float]:
    """Check if energy is conserved within tolerance.
    
    In a closed market system (no external news/events), total energy
    should be approximately conserved. Large deviations indicate
    external forces or regime changes.
    
    Args:
        energy_before: Energy at time t
        energy_after: Energy at time t+1
        tolerance: Relative tolerance (default: 1%)
        
    Returns:
        Tuple of (is_conserved, relative_change)
        
    Example:
        >>> E1 = compute_market_energy(prices1, volumes1)
        >>> E2 = compute_market_energy(prices2, volumes2)
        >>> conserved, change = check_energy_conservation(E1, E2)
        >>> if not conserved:
        ...     print(f"Energy violation: {change:.2%}")
    """
    if abs(energy_before) < 1e-10:
        # Handle near-zero energy case
        absolute_change = abs(energy_after - energy_before)
        return absolute_change < tolerance, absolute_change
    
    relative_change = abs(energy_after - energy_before) / abs(energy_before)
    is_conserved = relative_change <= tolerance
    
    return is_conserved, float(relative_change)


def check_momentum_conservation(
    momentum_before: float,
    momentum_after: float,
    tolerance: float = 0.01,
) -> tuple[bool, float]:
    """Check if momentum is conserved within tolerance.
    
    Args:
        momentum_before: Momentum at time t
        momentum_after: Momentum at time t+1
        tolerance: Relative tolerance (default: 1%)
        
    Returns:
        Tuple of (is_conserved, relative_change)
        
    Example:
        >>> p1 = compute_market_momentum(prices1, volumes1)
        >>> p2 = compute_market_momentum(prices2, volumes2)
        >>> conserved, change = check_momentum_conservation(p1, p2)
    """
    if abs(momentum_before) < 1e-10:
        absolute_change = abs(momentum_after - momentum_before)
        return absolute_change < tolerance, absolute_change
    
    relative_change = abs(momentum_after - momentum_before) / abs(momentum_before)
    is_conserved = relative_change <= tolerance
    
    return is_conserved, float(relative_change)


__all__ = [
    "compute_market_energy",
    "compute_market_momentum",
    "check_energy_conservation",
    "check_momentum_conservation",
]
