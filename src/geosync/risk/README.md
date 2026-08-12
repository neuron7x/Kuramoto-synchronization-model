# GeoSync Risk Management Module

This module provides comprehensive risk management capabilities for GeoSync, including risk metrics calculation, position sizing, and automated testing.

## Components

### Risk Core (`risk_core.py`)

Core risk management functions:
- **VaR/ES Calculation**: Value at Risk and Expected Shortfall at configurable confidence levels
- **Kelly Fraction Sizing**: Kelly criterion with regime-aware shrinkage
- **Risk Breach Detection**: Automated detection of risk limit violations

### Automated Testing (`automated_testing.py`)

Comprehensive automated risk testing framework:
- **Scenario Generation**: Pre-built market scenarios (normal, volatile, crisis, flash crashes)
- **Stress Testing**: Systematic validation of risk metrics under various conditions
- **Monte Carlo Simulation**: Statistical risk analysis
- **Validation Framework**: Automated validation of risk calculations

## Quick Start

### Basic Risk Metrics

```python
import numpy as np
from geosync.risk import var_es, kelly_shrink, check_risk_breach

# Calculate VaR and ES
returns = np.random.normal(0.0005, 0.015, 252)
var, es = var_es(returns, alpha=0.975)

# Calculate Kelly fraction for position sizing
mu = np.mean(returns)
sigma2 = np.var(returns)
kelly = kelly_shrink(mu, sigma2, ews_level="EMERGENT", f_max=1.0)

# Check for risk breach
breach = check_risk_breach(es, es_limit=0.03)
```

### Automated Risk Testing

```python
from geosync.risk import (
    AutomatedRiskTester,
    generate_market_stress_scenarios,
    MonteCarloConfig
)

# Initialize tester
tester = AutomatedRiskTester(es_limit=0.03, seed=42)

# Add market stress scenarios
scenarios = generate_market_stress_scenarios(num_days=252, seed=42)
for scenario in scenarios:
    tester.add_scenario(scenario)

# Run tests
results = tester.run_all_scenarios()

# Generate report
summary = tester.generate_summary_report()
print(f"Pass Rate: {summary['pass_rate']:.1%}")
```

### Monte Carlo Simulation

```python
from geosync.risk import AutomatedRiskTester, MonteCarloConfig

tester = AutomatedRiskTester(seed=42)

config = MonteCarloConfig(
    num_simulations=1000,
    num_periods=252,
    mu=0.0005,
    sigma=0.015,
    seed=42
)

results = tester.run_monte_carlo_simulation(config)
```

## Documentation

- **Full API Reference**: See `docs/automated_risk_testing.md`
- **Demo Script**: Run `python examples/automated_risk_testing_demo.py`
- **Tests**: See `tests/unit/geosync/risk/`

## Key Features

### Risk Metrics
- Value at Risk (VaR) with configurable confidence levels
- Expected Shortfall (ES) / Conditional VaR
- Kelly criterion position sizing
- Sharpe ratio calculation
- Maximum drawdown tracking

### Scenario Types
- Normal market conditions
- High volatility markets
- Bull/bear trending markets
- Mean-reverting markets
- Flash crashes
- Liquidity crises
- Black swan events
- Regime shifts

### Testing Capabilities
- Automated scenario generation
- Stress testing with configurable limits
- Monte Carlo simulation (1000+ iterations)
- Comprehensive validation framework
- Detailed reporting and analytics

## Integration

The risk module integrates with:
- **Portfolio Management**: Position sizing and allocation
- **Risk Managers**: Real-time risk monitoring
- **Backtesting Engine**: Historical risk analysis
- **Trading Systems**: Pre-trade risk checks

## Configuration

Risk parameters can be configured via:
- **Environment Variables**: `TP_ES_LIMIT`, `TP_VAR_ALPHA`, `TP_FMAX`
- **RiskConfig Class**: Programmatic configuration
- **Tester Parameters**: Per-test configuration

## Testing

Run the test suite:

```bash
# All risk tests
pytest tests/unit/geosync/risk/ -v

# Just automated testing
pytest tests/unit/geosync/risk/test_automated_testing.py -v

# Run demo
python examples/automated_risk_testing_demo.py
```

## Examples

See the `examples/` directory for:
- `automated_risk_testing_demo.py`: Comprehensive demo of all features

## Performance

- Scenario generation: < 1ms per scenario
- Single stress test: < 10ms
- Monte Carlo (1000 sims): ~1-2 seconds
- Comprehensive suite (10+ scenarios): < 100ms

## Best Practices

1. **Set Seed for Reproducibility**: Always use `seed` parameter for deterministic tests
2. **Define Expected Ranges**: Set `expected_var_range` and `expected_es_range` for custom scenarios
3. **Regular Testing**: Run stress tests regularly to detect risk control degradation
4. **Monte Carlo Coverage**: Use 1000+ simulations for robust statistical properties
5. **Validate Assumptions**: Check that risk metrics satisfy theoretical properties (ES ≥ VaR)

## Contributing

When adding new features:
1. Add new scenario types to `ScenarioType` enum
2. Create generator functions following existing patterns
3. Add comprehensive tests
4. Update documentation
5. Run full test suite

## License

Part of GeoSync - see main LICENSE file.
