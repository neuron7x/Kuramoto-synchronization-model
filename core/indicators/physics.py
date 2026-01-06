# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Physics-inspired market indicators.

This module provides indicator implementations based on fundamental physics laws:
- Momentum indicators (Newton's Laws)
- Market gravity indicators (Universal Gravitation)
- Energy/momentum conservation checks
- Thermodynamic equilibrium detection
- Wave propagation indicators (Maxwell)
- Reference frame transformations (Relativity)
- Uncertainty quantification (Heisenberg)

These indicators ground market analysis in physical principles, reducing noise
and improving interpretability.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from core.indicators.base import BaseFeature, FeatureResult
from core.physics.conservation import (
    check_energy_conservation,
    check_momentum_conservation,
    compute_market_energy,
    compute_market_momentum,
)
from core.physics.gravity import compute_market_gravity, market_gravity_center
from core.physics.maxwell import (
    compute_market_field_divergence,
    propagate_price_wave,
)
from core.physics.newton import compute_price_acceleration, compute_price_velocity
from core.physics.relativity import relativistic_momentum
from core.physics.thermodynamics import (
    compute_market_temperature,
    is_thermodynamic_equilibrium,
)
from core.physics.uncertainty import position_momentum_uncertainty


class MarketMomentumIndicator(BaseFeature):
    """Market momentum indicator based on Newton's Laws.
    
    Computes price momentum p = m*v, where:
    - Mass (m) represents market liquidity/volume
    - Velocity (v) represents rate of price change
    
    Higher momentum indicates stronger price trends with more "inertia".
    
    Attributes:
        window: Lookback window for velocity calculation
        name: Feature identifier
    
    Example:
        >>> indicator = MarketMomentumIndicator(window=20)
        >>> result = indicator.transform(prices, volumes=volumes)
        >>> print(f"Momentum: {result.value:.2f}")
    """
    
    def __init__(self, window: int = 20, *, name: str | None = None) -> None:
        super().__init__(name or "market_momentum")
        self.window = window
    
    def transform(self, data: np.ndarray, **kwargs: Any) -> FeatureResult:
        """Compute market momentum from price and volume data.
        
        Args:
            data: Price array
            **kwargs: Optional volumes array
            
        Returns:
            FeatureResult with momentum value
        """
        prices = np.asarray(data, dtype=float)
        volumes = kwargs.get("volumes")
        
        if prices.size < 2:
            return FeatureResult(
                name=self.name,
                value=0.0,
                metadata={"window": self.window, "samples": prices.size}
            )
        
        # Use window for calculation
        window_prices = prices[-self.window:] if prices.size >= self.window else prices
        
        # Compute velocity
        velocities = compute_price_velocity(window_prices)
        
        # Compute momentum (use volumes if provided)
        if volumes is not None:
            volumes_arr = np.asarray(volumes, dtype=float)
            window_volumes = volumes_arr[-self.window:] if volumes_arr.size >= self.window else volumes_arr
            momentum = compute_market_momentum(window_prices, window_volumes, velocities)
        else:
            # Use uniform mass if no volumes
            momentum = compute_market_momentum(window_prices, None, velocities)
        
        return FeatureResult(
            name=self.name,
            value=float(momentum),
            metadata={
                "window": self.window,
                "samples": len(window_prices),
                "has_volumes": volumes is not None
            }
        )


class MarketGravityIndicator(BaseFeature):
    """Market gravity indicator based on Universal Gravitation.
    
    Computes gravitational "pull" exerted by volume-weighted price levels.
    High gravity points indicate strong support/resistance levels.
    
    Attributes:
        name: Feature identifier
    
    Example:
        >>> indicator = MarketGravityIndicator()
        >>> result = indicator.transform(prices, volumes=volumes)
        >>> # Positive gravity = upward pull, Negative = downward pull
    """
    
    def __init__(self, *, name: str | None = None) -> None:
        super().__init__(name or "market_gravity")
    
    def transform(self, data: np.ndarray, **kwargs: Any) -> FeatureResult:
        """Compute market gravity field.
        
        Args:
            data: Price array
            **kwargs: Optional volumes array
            
        Returns:
            FeatureResult with gravity field array
        """
        prices = np.asarray(data, dtype=float)
        volumes = kwargs.get("volumes")
        
        if prices.size == 0:
            return FeatureResult(
                name=self.name,
                value=np.array([]),
                metadata={}
            )
        
        volumes_arr = np.asarray(volumes, dtype=float) if volumes is not None else None
        
        # Compute gravity field
        gravity = compute_market_gravity(prices, volumes_arr)
        
        # Return current (last) gravity value
        current_gravity = float(gravity[-1]) if gravity.size > 0 else 0.0
        
        # Also compute center of gravity (VWAP)
        center = market_gravity_center(prices, volumes_arr)
        
        return FeatureResult(
            name=self.name,
            value=current_gravity,
            metadata={
                "center_of_gravity": float(center),
                "samples": prices.size,
                "has_volumes": volumes is not None
            }
        )


class EnergyConservationIndicator(BaseFeature):
    """Energy conservation check for market stability.
    
    Monitors total market energy (kinetic + potential) to detect regime changes.
    Energy conservation violations indicate external forces (news, events).
    
    Attributes:
        tolerance: Relative tolerance for conservation check
        name: Feature identifier
    
    Example:
        >>> indicator = EnergyConservationIndicator(tolerance=0.05)
        >>> result = indicator.transform(prices, volumes=volumes)
        >>> if not result.metadata["conserved"]:
        ...     print("Energy violation: regime change detected!")
    """
    
    def __init__(self, tolerance: float = 0.05, *, name: str | None = None) -> None:
        super().__init__(name or "energy_conservation")
        self.tolerance = tolerance
    
    def transform(self, data: np.ndarray, **kwargs: Any) -> FeatureResult:
        """Check energy conservation between consecutive windows.
        
        Args:
            data: Price array
            **kwargs: Optional volumes array
            
        Returns:
            FeatureResult with conservation status
        """
        prices = np.asarray(data, dtype=float)
        volumes = kwargs.get("volumes")
        
        if prices.size < 4:
            return FeatureResult(
                name=self.name,
                value=0.0,
                metadata={"conserved": True, "insufficient_data": True}
            )
        
        # Split into two windows
        mid = prices.size // 2
        prices1 = prices[:mid]
        prices2 = prices[mid:]
        
        volumes1 = None
        volumes2 = None
        if volumes is not None:
            volumes_arr = np.asarray(volumes, dtype=float)
            volumes1 = volumes_arr[:mid]
            volumes2 = volumes_arr[mid:]
        
        # Compute energy for each window
        energy1 = compute_market_energy(prices1, volumes1)
        energy2 = compute_market_energy(prices2, volumes2)
        
        # Check conservation
        conserved, relative_change = check_energy_conservation(
            energy1, energy2, tolerance=self.tolerance
        )
        
        return FeatureResult(
            name=self.name,
            value=float(relative_change),
            metadata={
                "conserved": bool(conserved),
                "energy_before": float(energy1),
                "energy_after": float(energy2),
                "tolerance": self.tolerance
            }
        )


class ThermodynamicEquilibriumIndicator(BaseFeature):
    """Thermodynamic equilibrium detector for regime identification.
    
    Compares market "temperature" (volatility) across time windows to detect
    equilibrium vs transitional states.
    
    Attributes:
        window: Size of each window for temperature calculation
        tolerance: Relative tolerance for equilibrium
        name: Feature identifier
    
    Example:
        >>> indicator = ThermodynamicEquilibriumIndicator(window=50)
        >>> result = indicator.transform(returns)
        >>> if result.metadata["equilibrium"]:
        ...     print("Market in stable regime")
    """
    
    def __init__(
        self,
        window: int = 50,
        tolerance: float = 0.1,
        *,
        name: str | None = None
    ) -> None:
        super().__init__(name or "thermodynamic_equilibrium")
        self.window = window
        self.tolerance = tolerance
    
    def transform(self, data: np.ndarray, **kwargs: Any) -> FeatureResult:
        """Detect thermodynamic equilibrium from returns.
        
        Args:
            data: Returns array (not prices)
            **kwargs: Unused
            
        Returns:
            FeatureResult with equilibrium status
        """
        returns = np.asarray(data, dtype=float)
        
        if returns.size < 2 * self.window:
            return FeatureResult(
                name=self.name,
                value=0.0,
                metadata={"equilibrium": True, "insufficient_data": True}
            )
        
        # Split into two windows
        returns1 = returns[-2*self.window:-self.window]
        returns2 = returns[-self.window:]
        
        # Compute temperatures (from volatility)
        vol1 = float(np.std(returns1))
        vol2 = float(np.std(returns2))
        
        temp1 = compute_market_temperature(vol1)
        temp2 = compute_market_temperature(vol2)
        
        # Check equilibrium
        equilibrium = is_thermodynamic_equilibrium(
            temp1, temp2, tolerance=self.tolerance
        )
        
        # Distance from equilibrium
        temp_diff = abs(temp1 - temp2)
        
        return FeatureResult(
            name=self.name,
            value=float(temp_diff),
            metadata={
                "equilibrium": bool(equilibrium),
                "temperature_1": float(temp1),
                "temperature_2": float(temp2),
                "window": self.window,
                "tolerance": self.tolerance
            }
        )


class MarketFieldDivergenceIndicator(BaseFeature):
    """Market field divergence indicator based on Maxwell's equations.
    
    Computes divergence of order flow field to detect accumulation/distribution.
    - Positive divergence: Accumulation (buying pressure)
    - Negative divergence: Distribution (selling pressure)
    
    Attributes:
        name: Feature identifier
    
    Example:
        >>> indicator = MarketFieldDivergenceIndicator()
        >>> result = indicator.transform(order_flow)
        >>> if result.value > 0:
        ...     print("Accumulation detected")
    """
    
    def __init__(self, *, name: str | None = None) -> None:
        super().__init__(name or "market_field_divergence")
    
    def transform(self, data: np.ndarray, **kwargs: Any) -> FeatureResult:
        """Compute field divergence.
        
        Args:
            data: Field array (e.g., order flow, volume)
            **kwargs: Unused
            
        Returns:
            FeatureResult with current divergence value
        """
        field = np.asarray(data, dtype=float)
        
        if field.size < 2:
            return FeatureResult(
                name=self.name,
                value=0.0,
                metadata={"samples": field.size}
            )
        
        # Compute divergence
        divergence = compute_market_field_divergence(field)
        
        # Return current value
        current_div = float(divergence[-1])
        
        return FeatureResult(
            name=self.name,
            value=current_div,
            metadata={
                "mean_divergence": float(np.mean(divergence)),
                "samples": field.size
            }
        )


class UncertaintyQuantificationIndicator(BaseFeature):
    """Uncertainty quantification based on Heisenberg's principle.
    
    Computes position-momentum uncertainty product to quantify fundamental
    prediction limits in the market.
    
    Attributes:
        name: Feature identifier
    
    Example:
        >>> indicator = UncertaintyQuantificationIndicator()
        >>> result = indicator.transform(prices)
        >>> print(f"Uncertainty: {result.value:.4f}")
    """
    
    def __init__(self, *, name: str | None = None) -> None:
        super().__init__(name or "uncertainty_quantification")
    
    def transform(self, data: np.ndarray, **kwargs: Any) -> FeatureResult:
        """Compute uncertainty product.
        
        Args:
            data: Price array
            **kwargs: Unused
            
        Returns:
            FeatureResult with uncertainty product
        """
        prices = np.asarray(data, dtype=float)
        
        if prices.size < 2:
            return FeatureResult(
                name=self.name,
                value=0.0,
                metadata={"samples": prices.size}
            )
        
        # Compute momentum (velocity)
        velocities = compute_price_velocity(prices)
        
        # Compute uncertainties
        delta_x, delta_p, product = position_momentum_uncertainty(
            prices, velocities
        )
        
        return FeatureResult(
            name=self.name,
            value=float(product),
            metadata={
                "position_uncertainty": float(delta_x),
                "momentum_uncertainty": float(delta_p),
                "samples": prices.size
            }
        )


__all__ = [
    "MarketMomentumIndicator",
    "MarketGravityIndicator",
    "EnergyConservationIndicator",
    "ThermodynamicEquilibriumIndicator",
    "MarketFieldDivergenceIndicator",
    "UncertaintyQuantificationIndicator",
]
