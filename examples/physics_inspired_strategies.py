# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Example: Physics-Inspired Trading Strategy

This example demonstrates how to use the physics-inspired framework to create
a trading strategy that combines multiple physical principles.
"""

import numpy as np

# Physics indicators
from core.indicators.physics import (
    EnergyConservationIndicator,
    MarketGravityIndicator,
    MarketMomentumIndicator,
    ThermodynamicEquilibriumIndicator,
    UncertaintyQuantificationIndicator,
)

# Physics validation for backtesting
from backtest.physics_validation import PhysicsBacktestValidator

# TACL enhanced validation
from tacl.physics_validation import PhysicsEnhancedValidator


def generate_sample_data(n_samples: int = 100):
    """Generate sample price and volume data for demonstration."""
    np.random.seed(42)
    
    # Generate trending prices with noise
    trend = np.linspace(100, 120, n_samples)
    noise = np.random.randn(n_samples) * 2
    prices = trend + noise
    
    # Generate volumes with some correlation to price changes
    base_volume = 1000
    volume_noise = np.random.randn(n_samples) * 100
    volumes = base_volume + volume_noise
    volumes = np.abs(volumes)  # Ensure positive
    
    # Generate returns for thermodynamic analysis
    returns = np.diff(prices) / prices[:-1]
    
    return prices, volumes, returns


def physics_momentum_strategy():
    """Example: Momentum-based strategy using Newton's Laws."""
    print("=" * 60)
    print("Physics Momentum Strategy (Newton's Laws)")
    print("=" * 60)
    
    prices, volumes, _ = generate_sample_data(100)
    
    # Create momentum indicator
    momentum_indicator = MarketMomentumIndicator(window=20)
    
    # Compute momentum
    result = momentum_indicator.transform(prices, volumes=volumes)
    
    print(f"\nCurrent Momentum: {result.value:.2f}")
    print(f"Window: {result.metadata['window']}")
    print(f"Samples: {result.metadata['samples']}")
    
    # Trading logic
    if abs(result.value) > 50:
        signal = "BUY" if result.value > 0 else "SELL"
        print(f"\n🔔 Signal: {signal} (High momentum detected)")
    else:
        print("\n⏸️  Signal: HOLD (Insufficient momentum)")
    
    print()


def physics_gravity_strategy():
    """Example: Mean reversion strategy using Universal Gravitation."""
    print("=" * 60)
    print("Physics Gravity Strategy (Universal Gravitation)")
    print("=" * 60)
    
    prices, volumes, _ = generate_sample_data(100)
    
    # Create gravity indicator
    gravity_indicator = MarketGravityIndicator()
    
    # Compute gravity and center
    result = gravity_indicator.transform(prices, volumes=volumes)
    
    current_price = prices[-1]
    center = result.metadata['center_of_gravity']
    
    print(f"\nCurrent Price: ${current_price:.2f}")
    print(f"Center of Gravity (VWAP): ${center:.2f}")
    print(f"Distance from Center: ${abs(current_price - center):.2f}")
    print(f"Gravitational Pull: {result.value:.2f}")
    
    # Trading logic
    distance = abs(current_price - center)
    if distance > 5.0:
        signal = "BUY" if current_price < center else "SELL"
        print(f"\n🔔 Signal: {signal} (Price far from center, mean reversion expected)")
    else:
        print("\n⏸️  Signal: HOLD (Price near equilibrium)")
    
    print()


def physics_regime_detection():
    """Example: Regime detection using Thermodynamics and Conservation."""
    print("=" * 60)
    print("Physics Regime Detection (Thermodynamics & Conservation)")
    print("=" * 60)
    
    prices, volumes, returns = generate_sample_data(100)
    
    # Thermodynamic equilibrium indicator
    equilibrium_indicator = ThermodynamicEquilibriumIndicator(window=30)
    eq_result = equilibrium_indicator.transform(returns)
    
    print(f"\nThermodynamic Analysis:")
    print(f"  Temperature 1: {eq_result.metadata['temperature_1']:.2f}K")
    print(f"  Temperature 2: {eq_result.metadata['temperature_2']:.2f}K")
    print(f"  Temperature Difference: {eq_result.value:.2f}K")
    print(f"  Equilibrium: {eq_result.metadata['equilibrium']}")
    
    # Energy conservation indicator
    conservation_indicator = EnergyConservationIndicator(tolerance=0.1)
    cons_result = conservation_indicator.transform(prices, volumes=volumes)
    
    print(f"\nConservation Analysis:")
    print(f"  Energy Before: {cons_result.metadata['energy_before']:.2f}")
    print(f"  Energy After: {cons_result.metadata['energy_after']:.2f}")
    print(f"  Relative Change: {cons_result.value:.2%}")
    print(f"  Conserved: {cons_result.metadata['conserved']}")
    
    # Determine regime
    if eq_result.metadata['equilibrium'] and cons_result.metadata['conserved']:
        print("\n📊 Regime: STABLE")
        print("   - Market in thermodynamic equilibrium")
        print("   - Energy conservation maintained")
        print("   - Suitable for mean reversion strategies")
    else:
        print("\n⚠️  Regime: TRANSITIONAL")
        print("   - Market not in equilibrium")
        print("   - Energy conservation violated")
        print("   - Regime change or external event detected")
    
    print()


def physics_uncertainty_analysis():
    """Example: Uncertainty quantification using Heisenberg's Principle."""
    print("=" * 60)
    print("Physics Uncertainty Analysis (Heisenberg's Principle)")
    print("=" * 60)
    
    prices, _, _ = generate_sample_data(100)
    
    # Uncertainty indicator
    uncertainty_indicator = UncertaintyQuantificationIndicator()
    
    # Compute uncertainty
    result = uncertainty_indicator.transform(prices)
    
    print(f"\nUncertainty Analysis:")
    print(f"  Position Uncertainty (Δx): {result.metadata['position_uncertainty']:.4f}")
    print(f"  Momentum Uncertainty (Δp): {result.metadata['momentum_uncertainty']:.4f}")
    print(f"  Uncertainty Product: {result.value:.4f}")
    
    # Interpret uncertainty
    if result.value < 0.01:
        print("\n✓ Low Uncertainty")
        print("  - High confidence in predictions")
        print("  - Suitable for precise entry/exit")
    elif result.value < 0.1:
        print("\n⚠️  Moderate Uncertainty")
        print("  - Moderate confidence in predictions")
        print("  - Use wider stops and targets")
    else:
        print("\n❌ High Uncertainty")
        print("  - Low confidence in predictions")
        print("  - Fundamental limits on predictability")
        print("  - Consider reducing position size")
    
    print()


def physics_backtest_validation():
    """Example: Backtesting with physics validation."""
    print("=" * 60)
    print("Physics-Based Backtest Validation")
    print("=" * 60)
    
    # Generate time series data
    n_steps = 50
    prices_series = []
    volumes_series = []
    
    np.random.seed(42)
    for _ in range(n_steps):
        prices, volumes, _ = generate_sample_data(20)
        prices_series.append(prices)
        volumes_series.append(volumes)
    
    # Create validator
    validator = PhysicsBacktestValidator(
        energy_tolerance=0.15,
        momentum_tolerance=0.15
    )
    
    # Run validation over backtest
    print("\nRunning physics validation over backtest...")
    
    for t in range(len(prices_series) - 1):
        validator.check_timestep(
            timestep=t,
            prices_before=prices_series[t],
            prices_after=prices_series[t + 1],
            volumes_before=volumes_series[t],
            volumes_after=volumes_series[t + 1]
        )
    
    # Get metrics
    metrics = validator.get_metrics()
    
    print(f"\nBacktest Physics Metrics:")
    print(f"  Total Timesteps: {metrics.total_timesteps}")
    print(f"  Energy Violations: {metrics.energy_violations} ({metrics.energy_violation_rate:.1%})")
    print(f"  Momentum Violations: {metrics.momentum_violations} ({metrics.momentum_violation_rate:.1%})")
    print(f"  Overall Violation Rate: {metrics.overall_violation_rate:.1%}")
    
    # Generate report
    print("\n" + validator.generate_report())


def main():
    """Run all physics-inspired strategy examples."""
    print("\n" + "=" * 60)
    print("PHYSICS-INSPIRED TRADING STRATEGIES")
    print("=" * 60 + "\n")
    
    # Run examples
    physics_momentum_strategy()
    physics_gravity_strategy()
    physics_regime_detection()
    physics_uncertainty_analysis()
    physics_backtest_validation()
    
    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
