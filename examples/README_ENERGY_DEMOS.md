# Energy Model Demonstration Scripts

This directory contains comprehensive demonstration scripts showcasing the enhanced energy model capabilities introduced in v2.0.0.

## Overview

Three interactive demonstration scripts illustrate the world-class features of the thermodynamic energy model:

1. **`energy_diagnostics_demo.py`** - Advanced diagnostic capabilities
2. **`energy_optimization_demo.py`** - Sophisticated optimization algorithms
3. **`energy_monitoring_demo.py`** - Production-grade monitoring and observability

## Running the Demonstrations

### Prerequisites

Ensure you have the required dependencies:

```bash
pip install numpy scipy pyyaml
```

Note: `scipy` is optional. The system gracefully degrades if not available.

### Execute Demonstrations

Run each demo individually:

```bash
# Diagnostics demonstration
python examples/energy_diagnostics_demo.py

# Optimization demonstration
python examples/energy_optimization_demo.py

# Monitoring demonstration
python examples/energy_monitoring_demo.py
```

Or run all demos:

```bash
for demo in examples/energy_*_demo.py; do
    echo "Running $demo..."
    python "$demo"
    echo
done
```

## Demonstration Contents

### 1. Energy Diagnostics Demo (`energy_diagnostics_demo.py`)

Demonstrates comprehensive diagnostic tools for understanding energy dynamics.

**Features shown:**
- **Trend Analysis**: Statistical trend detection with forecasting
- **Anomaly Detection**: Z-score based anomaly identification
- **Energy Breakdown**: Detailed component analysis
- **Budget Tracking**: Real-time budget monitoring with alerts
- **Entropy Decomposition**: Per-metric stability contributions

**Sample Output:**
```
TREND ANALYSIS DEMONSTRATION
====================================================================

Energy Statistics:
  Mean:     1.152345
  Std Dev:  0.087621
  Min:      1.042187
  Max:      1.289432

Trend Analysis:
  Slope:    0.024531
  P-value:  0.012345
  Direction: INCREASING
  Statistically Significant: True

Forecast:
  Next value: 1.313963
```

**Use Cases:**
- Understanding energy evolution over time
- Detecting unusual system behavior
- Identifying dominant performance bottlenecks
- Budget planning and capacity management
- Stability analysis across metrics

### 2. Energy Optimization Demo (`energy_optimization_demo.py`)

Showcases advanced optimization algorithms for automatic parameter tuning.

**Features shown:**
- **Gradient Descent**: Local optimization with momentum
- **Simulated Annealing**: Global optimization escaping local minima
- **Adaptive Weight Tuning**: Dynamic weight adjustment
- **Phase Transition Detection**: System state change identification

**Sample Output:**
```
GRADIENT DESCENT OPTIMIZATION
====================================================================

Optimization Goal: Find weights that achieve target energy
Target energy: 1.200000

Initial parameters: {'w_lat95': 1.6, 'w_lat99': 1.9, 'w_drift': 1.2}
Initial objective: 0.045231

Optimization Results:
  Converged: True
  Iterations: 23
  Best score: 0.000142
  Best parameters:
    w_lat95: 1.523456
    w_lat99: 1.876543
    w_drift: 1.234567
```

**Use Cases:**
- Automatic calibration of model parameters
- Finding optimal weight configurations
- Multi-objective optimization
- System adaptation to changing conditions
- Performance tuning automation

### 3. Energy Monitoring Demo (`energy_monitoring_demo.py`)

Illustrates production-grade monitoring and observability features.

**Features shown:**
- **Prometheus Metrics**: Standard metrics export format
- **Real-time Alerting**: Threshold-based alert generation
- **Comprehensive Reporting**: Text and JSON report formats
- **Production Integration**: FastAPI, CI/CD, Grafana examples
- **Monitoring Lifecycle**: Complete operational workflow

**Sample Output:**
```
PROMETHEUS METRICS EXPORT
====================================================================

Recording validations...
  Validation 1: energy=1.042187, passed=True, duration=0.0001s
  Validation 2: energy=1.156234, passed=True, duration=0.0001s
  ...

Prometheus Metrics Export:
----------------------------------------------------------------------
# TYPE tradepulse_energy_free_energy gauge
tradepulse_energy_free_energy{environment="production",region="us-east-1"} 1.234567

# TYPE tradepulse_energy_validation_total counter
tradepulse_energy_validation_total{environment="production",region="us-east-1"} 5
----------------------------------------------------------------------
```

**Use Cases:**
- Production monitoring and alerting
- Integration with Prometheus/Grafana
- CI/CD validation reporting
- Real-time health checks
- Operational dashboards

## Integration Examples

### CI/CD Pipeline

```yaml
# .github/workflows/energy-validation.yml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run diagnostics
        run: python examples/energy_diagnostics_demo.py
      - name: Upload reports
        uses: actions/upload-artifact@v4
        with:
          name: energy-reports
          path: |
            .ci_artifacts/energy_*.json
            .ci_artifacts/energy_*.md
```

### Production Monitoring

```python
from fastapi import FastAPI
from tacl import EnergyMonitor

app = FastAPI()
monitor = EnergyMonitor()

@app.get("/metrics")
async def metrics():
    return monitor.get_prometheus_metrics()

@app.get("/alerts")
async def alerts():
    return [a.to_dict() for a in monitor.get_recent_alerts()]
```

### Automated Optimization

```python
from tacl import AdaptiveWeightTuner, EnergyModel

# Daily optimization job
tuner = AdaptiveWeightTuner(base_weights, target_energy=1.2)
model = EnergyModel()

for metrics in daily_metrics:
    energy, _, _, penalties = model.free_energy(metrics)
    adjusted = tuner.tune(metrics, energy, penalties)
    model = EnergyModel(weights=adjusted)
```

## Advanced Usage

### Custom Diagnostics

Extend the diagnostics module with custom analysis:

```python
from tacl import EnergyDiagnostics

class CustomDiagnostics(EnergyDiagnostics):
    def analyze_seasonality(self, results, period=24):
        """Detect seasonal patterns in energy data."""
        # Custom implementation
        pass
```

### Custom Optimization

Implement domain-specific optimization:

```python
from tacl import OptimizationResult

def custom_optimizer(initial_params, objective):
    # Your optimization logic
    return OptimizationResult(
        best_params=optimized_params,
        best_score=final_score,
        iterations=num_iterations,
        converged=True,
        history=score_history,
    )
```

### Custom Alerts

Create specialized alert handlers:

```python
from tacl import EnergyMonitor, AlertSeverity

monitor = EnergyMonitor()

def pagerduty_handler(alert):
    if alert.severity == AlertSeverity.CRITICAL:
        trigger_pagerduty_incident(alert)

def slack_handler(alert):
    post_to_slack(f"⚠️ {alert.message}")

monitor.register_alert_callback(pagerduty_handler)
monitor.register_alert_callback(slack_handler)
```

## Performance Considerations

### Caching

Enable caching for repeated evaluations:

```python
model = EnergyModel(enable_caching=True)
# 20-40% improvement for repeated patterns
```

### Batch Processing

Use batch evaluation for multiple metrics:

```python
results = model.batch_evaluate(metrics_list, max_free_energy=1.4)
# 30-50% faster than individual evaluations
```

### Memory Management

Bounded history prevents memory bloat:

```python
model = EnergyModel(track_history=True)
# Automatically keeps last 5000 entries
model.reset_history()  # Clear when needed
```

## Troubleshooting

### ImportError: No module named 'scipy'

The diagnostics module works without scipy but with reduced functionality:

```python
# Forecasting disabled without scipy
diagnostics = EnergyDiagnostics(enable_forecasting=False)
```

### Performance Issues

Check cache status and clear if needed:

```python
model.clear_cache()
model.reset_history()
```

### Alert Spam

Adjust cooldown period:

```python
monitor = EnergyMonitor(alert_cooldown=60.0)  # 60 seconds
```

## Testing

Run tests for the demonstration code:

```bash
pytest tests/tacl/test_energy_diagnostics.py -v
pytest tests/tacl/test_energy_optimization.py -v
pytest tests/tacl/test_energy_monitoring.py -v
```

## Documentation

For detailed documentation, see:

- **[ENERGY_MODEL_ENHANCEMENTS.md](../docs/ENERGY_MODEL_ENHANCEMENTS.md)** - Complete feature guide
- **Module docstrings** - Inline API documentation
- **Test files** - Usage examples in tests

## Contributing

When adding new demonstrations:

1. Follow the existing format and structure
2. Include comprehensive comments
3. Demonstrate real-world use cases
4. Add corresponding tests
5. Update this README

## Support

For questions or issues:

1. Review demonstration output
2. Check inline documentation
3. Examine test cases
4. Open GitHub issue with context

## Version History

### v2.0.0 (2025-11-15)

**Initial release of demonstration scripts:**
- Energy diagnostics demonstration
- Energy optimization demonstration
- Energy monitoring demonstration
- Comprehensive examples and integration patterns

## License

Copyright © 2025 TradePulse Contributors. All rights reserved.
