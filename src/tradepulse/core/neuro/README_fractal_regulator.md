# EEPFractalRegulator - Fractal Energy Regulator Module

## Overview

The EEPFractalRegulator (EEP-FPPA Fractal Energy Regulator) is a fractal-driven state regulation system designed for energy-efficient analytics and adaptive crisis control in TradePulse. It provides real-time monitoring of market dynamics through fractal metrics and enables adaptive system responses during stress events.

## Key Features

- **Fractal Metrics Computation**: Real-time calculation of Hurst exponent, Power Law Exponent (PLE), and Crisis Stability Index (CSI)
- **Energy Efficiency Optimization**: Embodied energy damping under crisis conditions
- **Adaptive Crisis Detection**: Configurable thresholds for automatic crisis detection
- **Sliding Window Architecture**: Efficient state management with configurable history size
- **Production-Ready**: Exception handling, input validation, and comprehensive test coverage (>80%)

## Architecture

The regulator operates on a sliding window of state history and computes key metrics:

1. **Hurst Exponent (H)**: Characterizes long-term memory and trend persistence
   - H < 0.5: Anti-persistent (mean-reverting)
   - H = 0.5: Random walk (no memory)
   - H > 0.5: Persistent (trending)

2. **Power Law Exponent (PLE)**: Indicates scaling behavior and complexity
   - Higher values suggest stronger power-law dynamics

3. **Crisis Stability Index (CSI)**: Multi-component stability measure
   - Combines volatility, Hurst deviation, and regime shift detection
   - Values near 1.0 indicate stability, lower values signal crisis

4. **Energy Cost**: Multiscale incremental energy consumption

5. **Efficiency Delta**: Change in system efficiency with optional crisis damping

## Installation

The module is part of the `core.neuro` package:

```python
from core.neuro.fractal_regulator import EEPFractalRegulator, RegulatorMetrics
```

## Basic Usage

### Simple State Monitoring

```python
from core.neuro.fractal_regulator import EEPFractalRegulator
import numpy as np

# Initialize regulator
regulator = EEPFractalRegulator(
    window_size=100,
    embodied_baseline=1.0,
    crisis_threshold=0.3,
    energy_damping=0.9,
    seed=42
)

# Update with new signal
metrics = regulator.update_state(0.5)

print(f"State: {metrics.state:.3f}")
print(f"Hurst: {metrics.hurst:.3f}")
print(f"CSI: {metrics.csi:.3f}")
print(f"Energy: {metrics.energy_cost:.3f}")

# Check for crisis
if regulator.is_in_crisis():
    print("WARNING: System in crisis state!")
```

### Trade Cycle Simulation

```python
# Generate market-like signals
rng = np.random.default_rng(42)
signals = rng.normal(0, 1, 100)

# Simulate complete cycle
results = regulator.simulate_trade_cycle(signals, verbose=False)

# Analyze results
crisis_count = sum(1 for m in results if m.csi < 0.3)
avg_hurst = np.mean([m.hurst for m in results])

print(f"Crisis events: {crisis_count}")
print(f"Average Hurst: {avg_hurst:.3f}")
```

### Continuous Monitoring

```python
# Process real-time signals
for signal_value in live_market_stream:
    metrics = regulator.update_state(signal_value)
    
    if metrics.csi < 0.3:
        # Trigger crisis handling
        handle_crisis(metrics)
    
    # Log metrics
    logger.info(f"H={metrics.hurst:.3f}, CSI={metrics.csi:.3f}")
```

## Integration with TradePulse

### As Feature Engineering Step

The regulator can be integrated into analytics pipelines for feature enrichment:

```python
from core.neuro.fractal_regulator import EEPFractalRegulator

class FractalFeatureEnricher:
    """Add fractal metrics as features."""
    
    def __init__(self):
        self.regulator = EEPFractalRegulator(window_size=50)
    
    def enrich(self, price_series):
        """Add fractal features to price data."""
        features = []
        for price in price_series:
            metrics = self.regulator.update_state(price)
            features.append({
                'price': price,
                'hurst': metrics.hurst,
                'ple': metrics.ple,
                'csi': metrics.csi,
                'in_crisis': metrics.csi < 0.3
            })
        return features
```

### As System Health Monitor

Monitor overall system health in orchestrator:

```python
from application.system_orchestrator import TradePulseOrchestrator
from core.neuro.fractal_regulator import EEPFractalRegulator

class HealthMonitoredOrchestrator(TradePulseOrchestrator):
    """Orchestrator with fractal health monitoring."""
    
    def __init__(self, system, **kwargs):
        super().__init__(system, **kwargs)
        self.health_monitor = EEPFractalRegulator(
            window_size=100,
            crisis_threshold=0.4
        )
    
    def run_strategy_with_monitoring(self, source, strategy):
        """Run strategy with real-time health monitoring."""
        # Execute strategy
        result = self.run_strategy(source, strategy)
        
        # Update health monitor with returns
        for ret in result.returns:
            metrics = self.health_monitor.update_state(ret)
            
            if self.health_monitor.is_in_crisis():
                self._trigger_crisis_protocol(metrics)
        
        return result
```

### As Crisis Handler (Alternative to thermo_controller)

Use as drop-in alternative for crisis handling:

```python
from core.neuro.fractal_regulator import EEPFractalRegulator

class FractalCrisisController:
    """Crisis controller using fractal regulator."""
    
    def __init__(self, config):
        self.regulator = EEPFractalRegulator(
            window_size=config.get('window_size', 100),
            crisis_threshold=config.get('crisis_threshold', 0.3),
            energy_damping=config.get('energy_damping', 0.9)
        )
        self.crisis_mode = False
    
    def evaluate_system_state(self, system_metrics):
        """Evaluate if system is in crisis."""
        # Update regulator with composite metric
        composite_signal = self._compute_composite_metric(system_metrics)
        metrics = self.regulator.update_state(composite_signal)
        
        # Detect crisis transition
        in_crisis = self.regulator.is_in_crisis()
        if in_crisis and not self.crisis_mode:
            self._enter_crisis_mode(metrics)
        elif not in_crisis and self.crisis_mode:
            self._exit_crisis_mode(metrics)
        
        return metrics
    
    def _compute_composite_metric(self, system_metrics):
        """Combine system metrics into single signal."""
        return (
            system_metrics.get('latency', 0) * 0.3 +
            system_metrics.get('error_rate', 0) * 0.4 +
            system_metrics.get('resource_usage', 0) * 0.3
        )
```

## Configuration

### Parameter Tuning Guide

**window_size** (default: 100)
- Smaller values (20-50): More responsive, higher noise
- Larger values (100-200): More stable, slower adaptation
- Recommended: 50-100 for trading applications

**embodied_baseline** (default: 1.0)
- Reference efficiency level
- Set based on historical system performance
- Higher values expect lower energy consumption

**crisis_threshold** (default: 0.3)
- CSI threshold for crisis detection
- Lower values: More aggressive crisis detection
- Higher values: More tolerant of volatility
- Recommended: 0.2-0.4 for financial markets

**energy_damping** (default: 0.9)
- Smoothing factor during crisis
- Higher values: Stronger damping, slower adjustment
- Lower values: Faster response, more volatility
- Recommended: 0.8-0.95

## Testing and Validation

### Running Unit Tests

```bash
# Run all tests
pytest core/neuro/tests/test_fractal_regulator.py -v

# Run with coverage
pytest core/neuro/tests/test_fractal_regulator.py --cov=core.neuro.fractal_regulator

# Run specific test class
pytest core/neuro/tests/test_fractal_regulator.py::TestCrisisDetection -v
```

### Validation on Market Data

```python
import pandas as pd
from core.neuro.fractal_regulator import EEPFractalRegulator

# Load market data
df = pd.read_csv('market_data.csv')
returns = df['close'].pct_change().dropna()

# Validate regulator
regulator = EEPFractalRegulator(window_size=100, seed=42)
results = regulator.simulate_trade_cycle(returns.values)

# Check metrics plausibility
print(f"Hurst range: [{min(m.hurst for m in results):.3f}, "
      f"{max(m.hurst for m in results):.3f}]")
print(f"CSI range: [{min(m.csi for m in results):.3f}, "
      f"{max(m.csi for m in results):.3f}]")

# Verify crisis detection
crisis_periods = [i for i, m in enumerate(results) if m.csi < 0.3]
print(f"Crisis detected at timesteps: {crisis_periods}")
```

## Performance Considerations

- **Computational Cost**: O(window_size) per update for metric computation
- **Memory**: O(window_size) for state history storage
- **Throughput**: ~1000-5000 updates/second on modern hardware
- **Latency**: < 1ms per update for typical window sizes

## Advanced Usage

### Custom Metric Aggregation

```python
class AggregatedRegulator:
    """Multi-timeframe fractal analysis."""
    
    def __init__(self):
        self.short_term = EEPFractalRegulator(window_size=20)
        self.medium_term = EEPFractalRegulator(window_size=50)
        self.long_term = EEPFractalRegulator(window_size=100)
    
    def update_all(self, signal):
        """Update all timeframes."""
        short_m = self.short_term.update_state(signal)
        medium_m = self.medium_term.update_state(signal)
        long_m = self.long_term.update_state(signal)
        
        # Aggregate CSI across timeframes
        avg_csi = (short_m.csi + medium_m.csi + long_m.csi) / 3
        
        return {
            'short_term': short_m,
            'medium_term': medium_m,
            'long_term': long_m,
            'aggregated_csi': avg_csi
        }
```

### Dynamic Threshold Adjustment

```python
class AdaptiveRegulator:
    """Regulator with dynamic crisis threshold."""
    
    def __init__(self):
        self.regulator = EEPFractalRegulator()
        self.csi_history = []
    
    def update_with_adaptive_threshold(self, signal):
        """Update and adjust threshold based on history."""
        metrics = self.regulator.update_state(signal)
        self.csi_history.append(metrics.csi)
        
        # Adjust threshold to 10th percentile of recent CSI
        if len(self.csi_history) >= 100:
            adaptive_threshold = np.percentile(
                self.csi_history[-100:], 10
            )
            self.regulator.crisis_threshold = adaptive_threshold
        
        return metrics
```

## Troubleshooting

### Common Issues

**Issue**: Hurst always returns 0.5
- **Cause**: Insufficient data in window
- **Solution**: Ensure at least 8 samples before computing metrics

**Issue**: CSI always near 1.0
- **Cause**: Low volatility input or constant signals
- **Solution**: Verify input signals have variation

**Issue**: Excessive crisis detection
- **Cause**: Threshold too high
- **Solution**: Lower crisis_threshold parameter

**Issue**: No crisis detection
- **Cause**: Threshold too low
- **Solution**: Raise crisis_threshold parameter

## API Reference

### EEPFractalRegulator

**Constructor Parameters:**
- `window_size` (int): History window size (default: 100, min: 8)
- `embodied_baseline` (float): Efficiency baseline (default: 1.0, must be positive)
- `crisis_threshold` (float): CSI crisis threshold (default: 0.3, range: [0, 1])
- `energy_damping` (float): Damping factor (default: 0.9, range: [0, 1])
- `seed` (int | None): Random seed for reproducibility

**Methods:**
- `update_state(signal: float) -> RegulatorMetrics`: Update with new signal
- `compute_hurst() -> float`: Get current Hurst exponent
- `compute_ple() -> float`: Get current PLE
- `compute_csi() -> float`: Get current CSI
- `optimize_efficiency() -> float`: Get efficiency delta
- `get_metrics() -> RegulatorMetrics | None`: Get latest metrics without update
- `is_in_crisis() -> bool`: Check crisis state
- `reset() -> None`: Reset all state
- `simulate_trade_cycle(signals, verbose=False) -> list[RegulatorMetrics]`: Simulate cycle

### RegulatorMetrics

**Attributes:**
- `state` (float): Current state value
- `hurst` (float): Hurst exponent
- `ple` (float): Power Law Exponent
- `csi` (float): Crisis Stability Index
- `energy_cost` (float): Energy cost
- `efficiency_delta` (float): Change in efficiency

## References

- Hurst exponent: Rescaled range (R/S) analysis
- Power law scaling: Autocorrelation-based spectral analysis
- Crisis detection: Multi-component stability indexing

## Contributing

When extending the regulator:
1. Maintain backward compatibility
2. Add comprehensive unit tests (target >80% coverage)
3. Update this README with new features
4. Validate on market-like data

## License

Part of TradePulse project. See main LICENSE file.

## Support

For issues or questions:
- Open a GitHub issue
- Consult integration examples above
- Review unit tests for usage patterns
