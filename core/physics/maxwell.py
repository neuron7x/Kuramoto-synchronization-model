# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Maxwell's Equations applied to market dynamics.

Maxwell's equations describe electromagnetic fields, providing analogies for:
- Market field theory (order flow as "electric" field)
- Wave propagation (information/price wave travel)
- Divergence/curl analysis (source/sink and rotation detection)
"""

from __future__ import annotations

import numpy as np

from .constants import PhysicsConstants


def compute_market_field_divergence(
    field: np.ndarray,
    dx: float = 1.0,
) -> np.ndarray:
    """Compute divergence of a market field (∇·F).
    
    Divergence measures "sources" and "sinks" in the field:
    - Positive divergence: source (buying pressure)
    - Negative divergence: sink (selling pressure)
    - Zero divergence: conservation (no net flow)
    
    Uses finite differences to approximate the spatial derivative.
    
    Args:
        field: 1D array representing market field (e.g., order flow)
        dx: Spatial step size (default: 1.0)
        
    Returns:
        Array of divergence values (same length as field)
        
    Example:
        >>> order_flow = np.array([100, 150, 200, 180, 160])
        >>> divergence = compute_market_field_divergence(order_flow)
        >>> # Positive = accumulation, Negative = distribution
    """
    field_arr = np.asarray(field, dtype=float)
    n = field_arr.size
    
    if n < 2:
        return np.zeros_like(field_arr)
    
    # Compute gradient using central differences
    divergence = np.zeros_like(field_arr)
    
    # Forward difference for first point
    divergence[0] = (field_arr[1] - field_arr[0]) / dx
    
    # Central differences for interior points
    if n > 2:
        divergence[1:-1] = (field_arr[2:] - field_arr[:-2]) / (2 * dx)
    
    # Backward difference for last point
    divergence[-1] = (field_arr[-1] - field_arr[-2]) / dx
    
    return divergence


def compute_market_field_curl(
    field_x: np.ndarray,
    field_y: np.ndarray,
    dx: float = 1.0,
    dy: float = 1.0,
) -> np.ndarray:
    """Compute curl of a 2D market field (∇×F).
    
    Curl measures "rotation" or circulation in the field:
    - Non-zero curl indicates rotational patterns (cycles)
    - Useful for detecting market regimes with cyclical behavior
    
    For 2D field F = (Fx, Fy), curl is: ∂Fy/∂x - ∂Fx/∂y
    
    Args:
        field_x: X-component of field (e.g., price momentum)
        field_y: Y-component of field (e.g., volume momentum)
        dx: Spatial step in x direction
        dy: Spatial step in y direction
        
    Returns:
        Array of curl values (perpendicular to xy-plane)
        
    Example:
        >>> price_mom = np.array([1.0, 1.5, 2.0, 1.8, 1.6])
        >>> vol_mom = np.array([100, 120, 110, 130, 125])
        >>> curl = compute_market_field_curl(price_mom, vol_mom)
    """
    fx = np.asarray(field_x, dtype=float)
    fy = np.asarray(field_y, dtype=float)
    
    if fx.size != fy.size:
        raise ValueError("field_x and field_y must have same length")
    
    n = fx.size
    if n < 2:
        return np.zeros_like(fx)
    
    # Compute partial derivatives
    dfy_dx = np.zeros_like(fy)
    dfx_dy = np.zeros_like(fx)
    
    # Approximate ∂Fy/∂x using finite differences
    dfy_dx[0] = (fy[1] - fy[0]) / dx
    if n > 2:
        dfy_dx[1:-1] = (fy[2:] - fy[:-2]) / (2 * dx)
    dfy_dx[-1] = (fy[-1] - fy[-2]) / dx
    
    # Approximate ∂Fx/∂y (treating index as y-direction)
    dfx_dy[0] = (fx[1] - fx[0]) / dy
    if n > 2:
        dfx_dy[1:-1] = (fx[2:] - fx[:-2]) / (2 * dy)
    dfx_dy[-1] = (fx[-1] - fx[-2]) / dy
    
    # Curl (z-component) = ∂Fy/∂x - ∂Fx/∂y
    curl = dfy_dx - dfx_dy
    
    return curl


def propagate_price_wave(
    initial_price: float,
    wave_amplitude: float,
    wave_frequency: float,
    time: float | np.ndarray,
    speed: float = PhysicsConstants.SPEED_OF_INFORMATION,
    damping: float = 0.0,
) -> float | np.ndarray:
    """Propagate a price wave using wave equation.
    
    Models price as a damped wave propagating through the market:
    P(t) = P₀ + A * exp(-γt) * cos(ωt)
    
    Where:
    - P₀ = initial price level
    - A = wave amplitude
    - ω = angular frequency
    - γ = damping coefficient
    - c = wave speed (information propagation)
    
    Args:
        initial_price: Base price level
        wave_amplitude: Wave amplitude (price oscillation size)
        wave_frequency: Wave frequency (oscillations per unit time)
        time: Time value(s) at which to evaluate
        speed: Wave propagation speed
        damping: Damping coefficient (0 = no damping)
        
    Returns:
        Price value(s) at given time(s)
        
    Example:
        >>> t = np.linspace(0, 10, 100)
        >>> prices = propagate_price_wave(
        ...     initial_price=100.0,
        ...     wave_amplitude=5.0,
        ...     wave_frequency=0.5,
        ...     time=t,
        ...     damping=0.1
        ... )
    """
    # Angular frequency
    omega = 2 * np.pi * wave_frequency
    
    # Wave propagation with damping
    time_arr = np.asarray(time)
    damping_factor = np.exp(-damping * time_arr)
    wave = wave_amplitude * damping_factor * np.cos(omega * time_arr)
    
    price = initial_price + wave
    
    return price if isinstance(time, np.ndarray) else float(price)


def wave_energy(
    amplitude: float,
    frequency: float,
    mass: float = 1.0,
) -> float:
    """Compute energy of a price wave.
    
    E = (1/2) * m * A² * ω²
    
    Higher energy waves have stronger impact on market.
    
    Args:
        amplitude: Wave amplitude
        frequency: Wave frequency
        mass: Effective mass (market size/liquidity)
        
    Returns:
        Wave energy
        
    Example:
        >>> energy = wave_energy(amplitude=5.0, frequency=0.5, mass=1000.0)
    """
    omega = 2 * np.pi * frequency
    return 0.5 * mass * (amplitude ** 2) * (omega ** 2)


__all__ = [
    "compute_market_field_divergence",
    "compute_market_field_curl",
    "propagate_price_wave",
    "wave_energy",
]
