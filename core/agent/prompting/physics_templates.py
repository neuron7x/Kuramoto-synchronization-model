# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics-inspired prompt templates for AI-driven trading strategies.

This module extends the core prompt library with templates that incorporate
physical principles and constraints to guide strategy generation.
"""

from __future__ import annotations

from typing import Final

# Physics-inspired strategy templates
PHYSICS_MOMENTUM_STRATEGY: Final[str] = """
Generate a trading strategy based on Newton's Laws of Motion applied to market dynamics.

## Physical Principles
1. **Inertia**: Prices in motion tend to stay in motion (trend continuation)
2. **Force**: Order flow creates force that accelerates prices (F = ma)
3. **Momentum**: Strong trends have high momentum (p = mv) that resists reversals

## Strategy Requirements
- Use market momentum indicators to identify trend strength
- Apply force analysis (order flow) to predict acceleration
- Implement momentum-based position sizing
- Include inertia-based hold periods (don't fight the trend)

## Risk Controls
- Maximum momentum threshold: {max_momentum}
- Minimum force required for entry: {min_force}
- Momentum decay detection for exits

Market Context: {market_context}
Timeframe: {timeframe}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

PHYSICS_GRAVITY_STRATEGY: Final[str] = """
Generate a mean reversion strategy based on Universal Gravitation principles.

## Physical Principles
1. **Gravitational Attraction**: Prices are attracted to volume-weighted centers
2. **Inverse Square Law**: Attraction strength decreases with distance from VWAP
3. **Multiple Centers**: High-volume nodes act as gravitational "masses"

## Strategy Requirements
- Identify gravitational centers (VWAP, high-volume nodes)
- Measure distance from current price to centers
- Calculate gravitational "force" pulling price back
- Trade mean reversion when price is far from center

## Risk Controls
- Maximum distance from center: {max_distance}
- Minimum gravitational force for entry: {min_gravity}
- Center of gravity stop-loss: {cog_stop}

Market Context: {market_context}
Timeframe: {timeframe}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

PHYSICS_CONSERVATION_STRATEGY: Final[str] = """
Generate a strategy that monitors conservation laws for regime detection.

## Physical Principles
1. **Energy Conservation**: Total market energy should be conserved in stable regimes
2. **Momentum Conservation**: Total momentum preserved absent external forces
3. **Violations**: Conservation violations signal regime changes or external events

## Strategy Requirements
- Monitor total market energy over time
- Track total momentum across multiple assets/timeframes
- Detect conservation violations (regime changes)
- Adjust position sizing based on regime stability

## Risk Controls
- Energy conservation tolerance: {energy_tolerance}
- Momentum conservation tolerance: {momentum_tolerance}
- Regime change emergency exit: {regime_exit}

Market Context: {market_context}
Assets: {assets}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

PHYSICS_THERMODYNAMIC_STRATEGY: Final[str] = """
Generate a volatility strategy based on Thermodynamic principles.

## Physical Principles
1. **Temperature**: Market temperature proportional to volatility (T ∝ σ²)
2. **Equilibrium**: Markets seek thermodynamic equilibrium (stable vol regimes)
3. **Entropy**: High entropy indicates chaos; low entropy indicates structure
4. **Free Energy**: System stability measured by free energy F = U - TS

## Strategy Requirements
- Compute market temperature from volatility
- Detect equilibrium vs transitional states
- Trade volatility expansion/contraction
- Use free energy for stability assessment

## Risk Controls
- Maximum temperature threshold: {max_temperature}
- Equilibrium tolerance: {equilibrium_tolerance}
- Minimum free energy for stability: {min_free_energy}

Market Context: {market_context}
Timeframe: {timeframe}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

PHYSICS_WAVE_STRATEGY: Final[str] = """
Generate a wave-based strategy using Maxwell's Equations principles.

## Physical Principles
1. **Wave Propagation**: Information propagates through market as waves
2. **Field Theory**: Order flow creates fields with divergence and curl
3. **Interference**: Multiple waves create constructive/destructive interference
4. **Wave Energy**: Wave amplitude and frequency determine impact

## Strategy Requirements
- Detect wave patterns in price and volume
- Compute field divergence (accumulation/distribution)
- Identify wave interference patterns
- Trade wave energy momentum

## Risk Controls
- Maximum wave amplitude: {max_amplitude}
- Minimum wave frequency for signal: {min_frequency}
- Wave damping detection for exits: {damping_threshold}

Market Context: {market_context}
Timeframe: {timeframe}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

PHYSICS_RELATIVITY_STRATEGY: Final[str] = """
Generate a multi-timeframe strategy based on Relativity principles.

## Physical Principles
1. **Reference Frames**: Different timeframes are different reference frames
2. **Time Dilation**: Fast trading sees time differently than slow trading
3. **Lorentz Transformation**: Transform signals between timeframes
4. **Relativistic Effects**: Signals amplify at high "velocities" (rapid changes)

## Strategy Requirements
- Analyze same asset across multiple timeframes (reference frames)
- Apply Lorentz transformations to align signals
- Detect relativistic momentum amplification
- Use time dilation for position timing

## Risk Controls
- Maximum velocity threshold: {max_velocity}
- Reference frame alignment tolerance: {alignment_tolerance}
- Time dilation factor limit: {max_time_dilation}

Market Context: {market_context}
Timeframes: {timeframes}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

PHYSICS_UNCERTAINTY_STRATEGY: Final[str] = """
Generate a strategy incorporating Heisenberg's Uncertainty Principle.

## Physical Principles
1. **Uncertainty Principle**: ΔxΔp ≥ ℏ/2 (fundamental prediction limits)
2. **Position-Momentum Tradeoff**: Can't simultaneously know exact price and trend
3. **Information Limits**: Fundamental bounds on prediction accuracy
4. **Optimal Allocation**: Balance precision between price and momentum

## Strategy Requirements
- Quantify position and momentum uncertainties
- Respect fundamental prediction limits
- Optimize measurement allocation (price vs momentum precision)
- Use uncertainty bounds for position sizing

## Risk Controls
- Minimum uncertainty product: {min_uncertainty}
- Position uncertainty limit: {position_limit}
- Momentum uncertainty limit: {momentum_limit}

Market Context: {market_context}
Timeframe: {timeframe}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""

# Composite physics strategy
PHYSICS_COMPOSITE_STRATEGY: Final[str] = """
Generate a comprehensive strategy integrating multiple physics principles.

## Integrated Physical Framework

### 1. Newton's Laws (Momentum & Force)
- Track price momentum and force (order flow)
- Apply inertia principle for trend following

### 2. Gravitation (Mean Reversion)
- Identify gravitational centers (VWAP, volume nodes)
- Trade gravitational attraction/repulsion

### 3. Conservation Laws (Regime Detection)
- Monitor energy and momentum conservation
- Detect regime changes from violations

### 4. Thermodynamics (Volatility & Stability)
- Compute market temperature from volatility
- Assess stability via free energy

### 5. Maxwell's Equations (Waves & Fields)
- Detect wave patterns and field structures
- Analyze accumulation/distribution via divergence

### 6. Relativity (Multi-Timeframe)
- Transform signals across timeframes
- Apply relativistic momentum corrections

### 7. Uncertainty Principle (Risk Management)
- Quantify fundamental prediction limits
- Size positions based on uncertainty bounds

## Strategy Requirements
- Combine physics indicators into unified framework
- Weight each principle based on market regime
- Apply physics-based risk controls
- Ensure deterministic, falsifiable signals

## Risk Controls
{risk_controls}

Market Context: {market_context}
Assets: {assets}
Timeframes: {timeframes}
Risk Tolerance: {risk_tolerance}

Generate the strategy code following GeoSync conventions.
"""


# Parameter constraints based on physics
PHYSICS_PARAMETER_CONSTRAINTS: Final[dict[str, tuple[float, float]]] = {
    # Newton's Laws
    "max_momentum": (0.0, 1000.0),
    "min_force": (0.0, 100.0),
    # Gravitation
    "max_distance": (0.0, 100.0),
    "min_gravity": (0.0, 10.0),
    # Conservation
    "energy_tolerance": (0.01, 0.2),
    "momentum_tolerance": (0.01, 0.2),
    # Thermodynamics
    "max_temperature": (100.0, 1000.0),
    "equilibrium_tolerance": (0.01, 0.2),
    "min_free_energy": (-10.0, 10.0),
    # Maxwell
    "max_amplitude": (0.0, 50.0),
    "min_frequency": (0.0, 1.0),
    "damping_threshold": (0.0, 1.0),
    # Relativity
    "max_velocity": (0.0, 1.0),
    "alignment_tolerance": (0.01, 0.2),
    "max_time_dilation": (1.0, 10.0),
    # Uncertainty
    "min_uncertainty": (0.0, 1.0),
    "position_limit": (0.0, 1.0),
    "momentum_limit": (0.0, 1.0),
}


__all__ = [
    "PHYSICS_MOMENTUM_STRATEGY",
    "PHYSICS_GRAVITY_STRATEGY",
    "PHYSICS_CONSERVATION_STRATEGY",
    "PHYSICS_THERMODYNAMIC_STRATEGY",
    "PHYSICS_WAVE_STRATEGY",
    "PHYSICS_RELATIVITY_STRATEGY",
    "PHYSICS_UNCERTAINTY_STRATEGY",
    "PHYSICS_COMPOSITE_STRATEGY",
    "PHYSICS_PARAMETER_CONSTRAINTS",
]
