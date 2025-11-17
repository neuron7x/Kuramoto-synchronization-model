# Automated Risk Testing Module

## Overview

The Automated Risk Testing Module provides comprehensive automated testing capabilities for risk management systems in TradePulse. It enables systematic validation of risk metrics, stress testing under various market conditions, and Monte Carlo simulations to ensure robust risk controls.

## Features

- **Automated Scenario Generation**: Pre-built market scenarios including normal markets, volatile markets, liquidity crises, and flash crashes
- **Stress Testing**: Comprehensive stress testing framework with configurable risk limits
- **Monte Carlo Simulation**: Statistical risk analysis through Monte Carlo methods
- **Risk Metrics Validation**: Automated validation of VaR, ES, and Kelly fraction calculations
- **Comprehensive Reporting**: Detailed test results and summary statistics

## Architecture

### Core Components

1. **AutomatedRiskTester**: Main testing framework that coordinates scenario execution and result aggregation
2. **RiskScenario**: Represents a single risk testing scenario with expected outcomes
3. **Scenario Generators**: Functions to generate predefined market conditions
4. **Risk Metrics Validator**: Validates computed risk metrics against expected ranges

### Scenario Types

The module supports the following scenario types:

- `NORMAL_MARKET`: Standard market conditions with low volatility
- `VOLATILE_MARKET`: High volatility market conditions
- `TRENDING_MARKET`: Markets with strong directional trends (bull/bear)
- `MEAN_REVERTING`: Mean-reverting market dynamics
- `FLASH_CRASH`: Sudden extreme price drops with partial recovery
- `LIQUIDITY_CRISIS`: Deteriorating liquidity with increased volatility
- `BLACK_SWAN`: Rare, extreme events
- `REGIME_SHIFT`: Structural changes in market behavior

## Usage

### Basic Risk Validation

```python
import numpy as np
from tradepulse.risk.automated_testing import validate_risk_metrics

# Generate or load returns data
returns = np.random.normal(0.0005, 0.015, 252)

# Validate risk metrics
result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)

print(f"VaR: {result['metrics']['var']:.6f}")
print(f"ES: {result['metrics']['es']:.6f}")
print(f"Risk Breach: {result['risk_breach']}")
print(f"All Validations Passed: {result['all_valid']}")
```

### Stress Testing

```python
from tradepulse.risk.automated_testing import (
    AutomatedRiskTester,
    generate_market_stress_scenarios,
)

# Initialize tester
tester = AutomatedRiskTester(
    es_limit=0.03,
    var_alpha=0.975,
    f_max=1.0,
    seed=42
)

# Generate and add scenarios
scenarios = generate_market_stress_scenarios(num_days=252, seed=42)
for scenario in scenarios:
    tester.add_scenario(scenario)

# Run all scenarios
results = tester.run_all_scenarios()

# Generate summary report
summary = tester.generate_summary_report()
print(f"Pass Rate: {summary['pass_rate']:.1%}")
```

### Monte Carlo Simulation

```python
from tradepulse.risk.automated_testing import (
    AutomatedRiskTester,
    MonteCarloConfig,
)

# Initialize tester
tester = AutomatedRiskTester(seed=42)

# Configure Monte Carlo simulation
config = MonteCarloConfig(
    num_simulations=1000,
    num_periods=252,
    mu=0.0005,  # Daily expected return
    sigma=0.015,  # Daily volatility
    alpha=0.975,
    seed=42
)

# Run simulation
results = tester.run_monte_carlo_simulation(config)

# Analyze results
vars = [r.var for r in results]
ess = [r.es for r in results]
print(f"Mean VaR: {np.mean(vars):.6f} ± {np.std(vars):.6f}")
print(f"Mean ES: {np.mean(ess):.6f} ± {np.std(ess):.6f}")
```

### Custom Scenarios

```python
import numpy as np
from tradepulse.risk.automated_testing import (
    AutomatedRiskTester,
    RiskScenario,
    ScenarioType,
)

# Create custom scenario
custom_returns = np.random.normal(-0.001, 0.03, 252)

scenario = RiskScenario(
    name="custom_market_stress",
    scenario_type=ScenarioType.VOLATILE_MARKET,
    returns=custom_returns,
    description="Custom high-volatility market with negative drift",
    expected_var_range=(0.04, 0.10),
    expected_es_range=(0.05, 0.15)
)

# Run test
tester = AutomatedRiskTester()
result = tester.run_stress_test(scenario)

print(f"Test Passed: {result.passed}")
if not result.passed:
    print("Validation Errors:")
    for error in result.validation_errors:
        print(f"  - {error}")
```

## API Reference

### AutomatedRiskTester

Main testing framework class.

**Constructor Parameters:**
- `es_limit` (float): Maximum allowed Expected Shortfall (default: 0.03)
- `var_alpha` (float): Confidence level for VaR/ES calculations (default: 0.975)
- `f_max` (float): Maximum Kelly fraction (default: 1.0)
- `seed` (Optional[int]): Random seed for reproducibility (default: None)

**Methods:**

#### `add_scenario(scenario: RiskScenario) -> None`
Add a risk scenario to the test suite.

#### `run_stress_test(scenario: RiskScenario) -> StressTestResult`
Run a single stress test scenario and return results.

#### `run_all_scenarios() -> List[StressTestResult]`
Run all configured scenarios and return list of results.

#### `run_monte_carlo_simulation(config: MonteCarloConfig) -> List[StressTestResult]`
Run Monte Carlo simulation with specified configuration.

#### `generate_summary_report() -> dict`
Generate comprehensive summary report of all test results.

### RiskScenario

Represents a risk testing scenario.

**Attributes:**
- `name` (str): Scenario name
- `scenario_type` (ScenarioType): Type of scenario
- `returns` (NDArray[np.float64]): Array of returns
- `description` (str): Human-readable description
- `expected_var_range` (Optional[Tuple[float, float]]): Expected VaR range
- `expected_es_range` (Optional[Tuple[float, float]]): Expected ES range
- `max_drawdown` (Optional[float]): Maximum expected drawdown
- `metadata` (dict): Additional metadata

**Methods:**

#### `validate_metrics(var: float, es: float, alpha: float) -> List[str]`
Validate computed metrics against expected ranges. Returns list of validation errors (empty if all pass).

### StressTestResult

Contains results from a stress test execution.

**Attributes:**
- `scenario_name` (str): Name of tested scenario
- `scenario_type` (ScenarioType): Type of scenario
- `var` (float): Computed Value at Risk
- `es` (float): Computed Expected Shortfall
- `alpha` (float): Confidence level used
- `kelly_fraction` (float): Kelly fraction for position sizing
- `risk_breach` (str): Risk breach status ("OK" or "BREACH")
- `max_drawdown` (float): Maximum drawdown observed
- `sharpe_ratio` (float): Sharpe ratio
- `validation_errors` (List[str]): List of validation errors
- `passed` (bool): Whether test passed all validations
- `timestamp` (datetime): Test execution timestamp
- `duration_seconds` (float): Test execution duration

**Methods:**

#### `to_dict() -> dict`
Convert result to dictionary for serialization/reporting.

### MonteCarloConfig

Configuration for Monte Carlo simulations.

**Attributes:**
- `num_simulations` (int): Number of simulations to run (default: 1000)
- `num_periods` (int): Number of periods per simulation (default: 252)
- `mu` (float): Expected daily return (default: 0.0005)
- `sigma` (float): Daily volatility (default: 0.02)
- `alpha` (float): Confidence level (default: 0.975)
- `seed` (Optional[int]): Random seed (default: None)

## Scenario Generators

### `generate_market_stress_scenarios(num_days: int, seed: Optional[int]) -> List[RiskScenario]`

Generates comprehensive market stress scenarios including:
- Normal market conditions
- High volatility markets
- Bull markets (trending up)
- Bear markets (trending down)
- Mean-reverting markets

### `generate_liquidity_crisis_scenarios(num_days: int, seed: Optional[int]) -> List[RiskScenario]`

Generates liquidity crisis scenarios including:
- Sudden liquidity crunch
- Gradual liquidity deterioration

### `generate_flash_crash_scenarios(num_days: int, crash_magnitude: float, seed: Optional[int]) -> List[RiskScenario]`

Generates flash crash scenarios including:
- Single large flash crash
- Multiple smaller crashes

## Validation Functions

### `validate_risk_metrics(returns: NDArray, alpha: float, es_limit: float) -> dict`

Validates risk metrics for a given return series.

**Returns:**
Dictionary containing:
- `metrics`: Computed risk metrics (VaR, ES, Kelly fractions, Sharpe ratio)
- `validations`: Boolean validation results
- `all_valid`: Whether all validations passed
- `risk_breach`: Risk breach status

## Best Practices

1. **Use Seed for Reproducibility**: Always set a seed when running tests that need to be reproducible
2. **Define Expected Ranges**: When creating custom scenarios, define expected metric ranges for validation
3. **Run Monte Carlo Regularly**: Use Monte Carlo simulations to understand statistical properties of risk metrics
4. **Test Multiple Scenarios**: Include diverse scenarios (normal, stress, crisis) in your test suite
5. **Monitor Pass Rates**: Track pass rates over time to detect degradation in risk controls
6. **Save Reports**: Save test reports for audit trails and historical analysis

## Integration with Existing Risk Modules

The Automated Risk Testing Module integrates seamlessly with existing risk components:

- **risk_core.py**: Uses `var_es()`, `kelly_shrink()`, and `check_risk_breach()` functions
- **Risk Managers**: Can validate risk manager behavior under various scenarios
- **Portfolio Management**: Test portfolio risk limits and position sizing

## Performance Considerations

- Monte Carlo simulations with thousands of iterations may take significant time
- Use appropriate `num_periods` based on your testing needs (252 for daily data over a year)
- Parallel execution of scenarios is not yet implemented but can be added for large test suites

## Example Output

### Stress Test Summary

```
Stress Test Results:
--------------------------------------------------------------------------------
✓ PASS | normal_market                  | VaR: 0.0195 | ES: 0.0251 | Breach: OK     | Sharpe:   1.45
✓ PASS | high_volatility_market         | VaR: 0.0612 | ES: 0.0778 | Breach: BREACH | Sharpe:   0.15
✓ PASS | bull_market                    | VaR: 0.0134 | ES: 0.0171 | Breach: OK     | Sharpe:   4.23
✓ PASS | bear_market                    | VaR: 0.0423 | ES: 0.0538 | Breach: BREACH | Sharpe:  -3.45
✓ PASS | mean_reverting_market          | VaR: 0.0183 | ES: 0.0234 | Breach: OK     | Sharpe:   0.87

Summary:
  Total Scenarios: 5
  Passed: 5
  Failed: 0
  Pass Rate: 100.0%
```

## Troubleshooting

### Import Errors

If you encounter import errors, ensure the `src` directory is in your Python path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
```

### NaN Values in Results

NaN values in Sharpe ratios or other metrics typically indicate:
- Zero volatility in returns (constant values)
- Empty return arrays
- Division by zero in calculations

### Validation Failures

If scenarios fail validation unexpectedly:
1. Check that expected ranges are reasonable for the scenario type
2. Verify return data is properly generated
3. Ensure alpha and es_limit parameters are appropriate

## Contributing

When extending the module:

1. Add new scenario types to `ScenarioType` enum
2. Create corresponding generator functions following existing patterns
3. Add comprehensive tests for new scenarios
4. Update documentation with examples

## License

This module is part of TradePulse and is subject to the same license terms.

## Support

For issues or questions:
- Open an issue on GitHub
- Refer to existing tests for usage examples
- Check the demo script in `examples/automated_risk_testing_demo.py`
