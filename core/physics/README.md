# Physics Module

## Overview

The `core/physics` module provides implementations of seven fundamental physical laws applied to market dynamics. These physics-inspired models ground trading strategies in deterministic, falsifiable principles.

## Structure

```
core/physics/
├── __init__.py           # Main module exports
├── constants.py          # Physical constants (normalized)
├── newton.py            # Newton's Laws of Motion
├── gravity.py           # Universal Gravitation
├── conservation.py      # Conservation Laws
├── thermodynamics.py    # Thermodynamic Principles
├── maxwell.py           # Maxwell's Equations
├── relativity.py        # Theory of Relativity
└── uncertainty.py       # Heisenberg's Uncertainty Principle
```

## Quick Start

```python
from core.physics import (
    compute_momentum,
    gravitational_force,
    check_energy_conservation,
    compute_market_temperature,
)

# Newton: Compute price momentum
momentum = compute_momentum(mass=volume, velocity=price_change_rate)

# Gravity: Compute attraction to price level
force = gravitational_force(mass1, mass2, distance)

# Conservation: Check energy conservation
conserved, change = check_energy_conservation(energy_before, energy_after)

# Thermodynamics: Compute market temperature
temperature = compute_market_temperature(volatility)
```

## Physics-Inspired Indicators

```python
from core.indicators.physics import (
    MarketMomentumIndicator,
    MarketGravityIndicator,
    EnergyConservationIndicator,
)

# Use indicators in strategies
momentum_indicator = MarketMomentumIndicator(window=20)
result = momentum_indicator.transform(prices, volumes=volumes)
```

## Backtesting with Physics Validation

```python
from backtest.physics_validation import PhysicsBacktestValidator

validator = PhysicsBacktestValidator()

# During backtest
for t in range(len(data) - 1):
    validator.check_timestep(
        timestep=t,
        prices_before=data[t],
        prices_after=data[t+1]
    )

# After backtest
report = validator.generate_report()
print(report)
```

## Documentation

See [docs/physics_inspired_modeling.md](../../docs/physics_inspired_modeling.md) for comprehensive documentation.

## Examples

See [examples/physics_inspired_strategies.py](../../examples/physics_inspired_strategies.py) for usage examples.

## Testing

```bash
# Run physics module tests
pytest tests/unit/physics/ -v

# Run physics indicator tests
pytest tests/unit/test_indicators_physics.py -v

# Run integration tests
pytest tests/integration/test_physics_integration.py -v
```

## Design Principles

1. **Normalized Constants**: All physical constants are dimensionless and scaled for market magnitudes
2. **Numerical Stability**: Protections against division by zero and overflow
3. **Type Flexibility**: Functions accept both scalars and numpy arrays
4. **Conservation Checks**: Validate physical consistency throughout
5. **Interpretability**: Physical analogies aid understanding

## References

- Newton, I. (1687). *Philosophiæ Naturalis Principia Mathematica*
- Einstein, A. (1905). "On the Electrodynamics of Moving Bodies"
- Heisenberg, W. (1927). "Über den anschaulichen Inhalt..."
- Maxwell, J. C. (1865). "A Dynamical Theory of the Electromagnetic Field"
- Boltzmann, L. (1877). "Über die Beziehung zwischen dem zweiten Hauptsatze..."
