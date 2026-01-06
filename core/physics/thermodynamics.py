# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Thermodynamics applied to market dynamics.

Thermodynamic principles model market equilibrium and disorder:
- Entropy measures market randomness/uncertainty (already exists in entropy.py)
- Temperature represents market activity level
- Free energy indicates system stability
- Equilibrium detection for regime identification
"""

from __future__ import annotations

import numpy as np

from .constants import PhysicsConstants


def boltzmann_entropy(
    probabilities: np.ndarray,
    k_B: float = PhysicsConstants.BOLTZMANN_CONSTANT,
) -> float:
    """Compute Boltzmann entropy S = k_B * Σ p_i * ln(p_i).
    
    This is equivalent to Shannon entropy scaled by Boltzmann constant.
    Already implemented in core/indicators/entropy.py, included here
    for completeness of the physics framework.
    
    Args:
        probabilities: Array of probability values (must sum to 1)
        k_B: Boltzmann constant
        
    Returns:
        Boltzmann entropy value
        
    Example:
        >>> probs = np.array([0.25, 0.25, 0.25, 0.25])
        >>> entropy = boltzmann_entropy(probs)
    """
    probs = np.asarray(probabilities, dtype=float)
    
    # Filter out zero probabilities
    probs_nonzero = probs[probs > 0]
    
    if probs_nonzero.size == 0:
        return 0.0
    
    # S = -k_B * Σ p * ln(p)
    entropy = -k_B * np.sum(probs_nonzero * np.log(probs_nonzero))
    
    return float(entropy)


def compute_market_temperature(
    volatility: float | np.ndarray,
    reference_vol: float = 0.01,
    T_ref: float = PhysicsConstants.REFERENCE_TEMPERATURE,
) -> float | np.ndarray:
    """Compute market temperature from volatility.
    
    Temperature represents market activity level, with higher temperature
    indicating more volatile/active markets.
    
    T = T_ref * (σ / σ_ref)²
    
    Args:
        volatility: Market volatility (standard deviation of returns)
        reference_vol: Reference volatility for normalization
        T_ref: Reference temperature
        
    Returns:
        Market temperature value(s)
        
    Example:
        >>> volatility = 0.02  # 2% daily volatility
        >>> temp = compute_market_temperature(volatility)
        >>> print(f"Market temperature: {temp:.1f}K")
    """
    vol_ratio = volatility / reference_vol
    temperature = T_ref * (vol_ratio ** 2)
    
    return temperature


def compute_free_energy(
    internal_energy: float,
    temperature: float,
    entropy: float,
) -> float:
    """Compute Helmholtz free energy F = U - T*S.
    
    Free energy indicates system stability:
    - Lower free energy = more stable configuration
    - Free energy minimization drives system evolution
    
    Args:
        internal_energy: Internal energy of the system
        temperature: System temperature
        entropy: System entropy
        
    Returns:
        Helmholtz free energy
        
    Note:
        This is the same formulation used in tacl/energy_model.py
        
    Example:
        >>> U = 1.0  # Internal energy
        >>> T = 300.0  # Temperature
        >>> S = 0.5  # Entropy
        >>> F = compute_free_energy(U, T, S)
    """
    return internal_energy - temperature * entropy


def gibbs_free_energy(
    enthalpy: float,
    temperature: float,
    entropy: float,
) -> float:
    """Compute Gibbs free energy G = H - T*S.
    
    Gibbs free energy is used for systems at constant pressure,
    relevant for market systems with external constraints.
    
    Args:
        enthalpy: Enthalpy (internal energy + pressure*volume work)
        temperature: System temperature
        entropy: System entropy
        
    Returns:
        Gibbs free energy
        
    Example:
        >>> H = 1.2  # Enthalpy
        >>> T = 300.0
        >>> S = 0.5
        >>> G = gibbs_free_energy(H, T, S)
    """
    return enthalpy - temperature * entropy


def thermal_equilibrium_distance(
    temperature1: float,
    temperature2: float,
) -> float:
    """Compute distance from thermal equilibrium.
    
    In equilibrium, two systems should have equal temperature.
    This measures how far from equilibrium they are.
    
    Args:
        temperature1: Temperature of first system
        temperature2: Temperature of second system
        
    Returns:
        Absolute temperature difference (0 = equilibrium)
        
    Example:
        >>> T1 = compute_market_temperature(vol1)
        >>> T2 = compute_market_temperature(vol2)
        >>> distance = thermal_equilibrium_distance(T1, T2)
        >>> if distance < 10.0:
        ...     print("Markets near thermal equilibrium")
    """
    return abs(temperature1 - temperature2)


def is_thermodynamic_equilibrium(
    temperature1: float,
    temperature2: float,
    tolerance: float = 0.05,
) -> bool:
    """Check if two systems are in thermal equilibrium.
    
    Args:
        temperature1: Temperature of first system
        temperature2: Temperature of second system
        tolerance: Relative tolerance (default: 5%)
        
    Returns:
        True if systems are in equilibrium within tolerance
        
    Example:
        >>> if is_thermodynamic_equilibrium(T_market, T_reference):
        ...     print("Market in stable regime")
    """
    if temperature1 == 0 and temperature2 == 0:
        return True
    
    max_temp = max(abs(temperature1), abs(temperature2))
    if max_temp < 1e-10:
        return True
    
    relative_diff = abs(temperature1 - temperature2) / max_temp
    return relative_diff <= tolerance


__all__ = [
    "boltzmann_entropy",
    "compute_market_temperature",
    "compute_free_energy",
    "gibbs_free_energy",
    "thermal_equilibrium_distance",
    "is_thermodynamic_equilibrium",
]
