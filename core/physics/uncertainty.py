# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Heisenberg's Uncertainty Principle applied to market dynamics.

The uncertainty principle states fundamental limits on simultaneous
measurement precision:
- ΔxΔp ≥ ℏ/2 (position-momentum uncertainty)

In markets, this models the tradeoff between:
- Price precision vs momentum precision
- Short-term accuracy vs long-term predictability
- Provides theoretical bounds on prediction capability
"""

from __future__ import annotations

import numpy as np

from .constants import PhysicsConstants


def heisenberg_uncertainty(
    position_uncertainty: float | np.ndarray,
    momentum_uncertainty: float | np.ndarray,
    hbar: float = PhysicsConstants.PLANCK_REDUCED,
) -> float | np.ndarray:
    """Compute uncertainty product ΔxΔp.
    
    The uncertainty principle states: ΔxΔp ≥ ℏ/2
    
    This is a fundamental limit on simultaneous measurement precision.
    
    Args:
        position_uncertainty: Uncertainty in position (price level)
        momentum_uncertainty: Uncertainty in momentum (price velocity)
        hbar: Reduced Planck constant
        
    Returns:
        Uncertainty product (should be ≥ ℏ/2 for valid measurements)
        
    Example:
        >>> delta_x = 0.1  # $0.10 price uncertainty
        >>> delta_p = 0.01  # 1% momentum uncertainty
        >>> product = heisenberg_uncertainty(delta_x, delta_p)
        >>> min_product = minimum_uncertainty_product()
        >>> if product < min_product:
        ...     print("Warning: Violates uncertainty principle!")
    """
    return position_uncertainty * momentum_uncertainty


def minimum_uncertainty_product(
    hbar: float = PhysicsConstants.PLANCK_REDUCED,
) -> float:
    """Compute minimum allowed uncertainty product ℏ/2.
    
    No measurement can achieve uncertainty product below this value.
    
    Args:
        hbar: Reduced Planck constant
        
    Returns:
        Minimum uncertainty product
        
    Example:
        >>> min_product = minimum_uncertainty_product()
        >>> print(f"Cannot predict better than: {min_product}")
    """
    return hbar / 2.0


def position_momentum_uncertainty(
    position_data: np.ndarray,
    momentum_data: np.ndarray,
) -> tuple[float, float, float]:
    """Compute position and momentum uncertainties from data.
    
    Estimates uncertainties from data using standard deviation,
    then computes the uncertainty product.
    
    Args:
        position_data: Array of position values (prices)
        momentum_data: Array of momentum values (price velocities)
        
    Returns:
        Tuple of (position_uncertainty, momentum_uncertainty, product)
        
    Example:
        >>> prices = np.array([100, 102, 101, 103, 102])
        >>> velocities = np.diff(prices)
        >>> dx, dp, product = position_momentum_uncertainty(prices, velocities)
        >>> print(f"Position uncertainty: {dx:.3f}")
        >>> print(f"Momentum uncertainty: {dp:.3f}")
        >>> print(f"Uncertainty product: {product:.3f}")
    """
    pos_arr = np.asarray(position_data, dtype=float)
    mom_arr = np.asarray(momentum_data, dtype=float)
    
    # Use standard deviation as uncertainty measure
    delta_x = float(np.std(pos_arr))
    delta_p = float(np.std(mom_arr))
    
    # Ensure minimum uncertainties
    delta_x = max(delta_x, PhysicsConstants.MIN_POSITION_UNCERTAINTY)
    delta_p = max(delta_p, PhysicsConstants.MIN_MOMENTUM_UNCERTAINTY)
    
    # Compute product
    product = heisenberg_uncertainty(delta_x, delta_p)
    
    return delta_x, delta_p, product


def check_uncertainty_principle(
    position_uncertainty: float,
    momentum_uncertainty: float,
    hbar: float = PhysicsConstants.PLANCK_REDUCED,
) -> tuple[bool, float]:
    """Check if uncertainties satisfy Heisenberg's principle.
    
    Args:
        position_uncertainty: Uncertainty in position
        momentum_uncertainty: Uncertainty in momentum
        hbar: Reduced Planck constant
        
    Returns:
        Tuple of (is_valid, violation_factor)
        - is_valid: True if principle is satisfied
        - violation_factor: How much principle is violated (< 1 if violated)
        
    Example:
        >>> valid, factor = check_uncertainty_principle(0.1, 0.01)
        >>> if not valid:
        ...     print(f"Uncertainty principle violated by {factor:.2f}x")
    """
    product = heisenberg_uncertainty(position_uncertainty, momentum_uncertainty, hbar)
    min_product = minimum_uncertainty_product(hbar)
    
    is_valid = product >= min_product
    
    if min_product > 0:
        violation_factor = product / min_product
    else:
        violation_factor = float('inf')
    
    return is_valid, float(violation_factor)


def optimal_measurement_tradeoff(
    total_uncertainty: float,
    hbar: float = PhysicsConstants.PLANCK_REDUCED,
) -> tuple[float, float]:
    """Compute optimal uncertainty allocation.
    
    Given a total uncertainty budget, find the optimal split between
    position and momentum uncertainties that minimizes the maximum
    individual uncertainty while satisfying the uncertainty principle.
    
    Optimal split: Δx = Δp = sqrt(ℏ/2)
    
    Args:
        total_uncertainty: Total uncertainty budget
        hbar: Reduced Planck constant
        
    Returns:
        Tuple of (optimal_position_unc, optimal_momentum_unc)
        
    Example:
        >>> budget = 1.0
        >>> dx, dp = optimal_measurement_tradeoff(budget)
        >>> print(f"Optimal position uncertainty: {dx:.4f}")
        >>> print(f"Optimal momentum uncertainty: {dp:.4f}")
    """
    min_product = minimum_uncertainty_product(hbar)
    
    # Optimal split is when Δx = Δp (equal allocation)
    # Constrained by ΔxΔp ≥ ℏ/2
    optimal_unc = np.sqrt(min_product)
    
    return optimal_unc, optimal_unc


def information_limit(
    measurement_time: float,
    hbar: float = PhysicsConstants.PLANCK_REDUCED,
) -> float:
    """Compute fundamental information limit for market prediction.
    
    Based on uncertainty principle, there's a fundamental limit to
    how accurately we can predict future states given finite
    measurement time.
    
    Args:
        measurement_time: Time available for measurement
        hbar: Reduced Planck constant
        
    Returns:
        Minimum achievable uncertainty in prediction
        
    Example:
        >>> t_measure = 1.0  # 1 day
        >>> limit = information_limit(t_measure)
        >>> print(f"Best possible prediction uncertainty: {limit:.4f}")
    """
    # Energy-time uncertainty relation: ΔEΔt ≥ ℏ/2
    # Converts to position-momentum form
    if measurement_time <= 0:
        return float('inf')
    
    return minimum_uncertainty_product(hbar) / measurement_time


__all__ = [
    "heisenberg_uncertainty",
    "minimum_uncertainty_product",
    "position_momentum_uncertainty",
    "check_uncertainty_principle",
    "optimal_measurement_tradeoff",
    "information_limit",
]
