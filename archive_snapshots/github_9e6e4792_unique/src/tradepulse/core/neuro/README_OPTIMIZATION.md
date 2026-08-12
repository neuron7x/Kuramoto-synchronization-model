# Neuromodulator Optimization System

## Overview

This directory contains the adaptive optimization system for TradePulse's neuroscience-grounded AI architecture. The system provides automatic calibration and cross-neuromodulator balance optimization for optimal trading performance.

## Components

### 1. Adaptive Calibrator (`adaptive_calibrator.py`)

Implements simulated annealing-based parameter optimization:

- **CalibrationMetrics**: Performance metrics dataclass
- **AdaptiveCalibrator**: Main calibration controller
- **Features**:
  - Multi-objective optimization (Sharpe, drawdown, win rate, stability)
  - Automatic parameter bound enforcement
  - Exploration/exploitation balance via temperature
  - Performance tracking and actionable recommendations
  - State persistence for long-running optimizations

### 2. Cross-Neuromodulator Optimizer (`neuro_optimizer.py`)

Implements homeostatic balance optimization:

- **OptimizationConfig**: Configuration dataclass
- **BalanceMetrics**: Neuromodulator balance health metrics
- **NeuroOptimizer**: Main optimization controller
- **Features**:
  - Homeostatic regulation (DA/5-HT ratio, E/I balance)
  - Multi-objective optimization across all neuromodulators
  - Momentum-based gradient updates
  - Real-time health assessment
  - Convergence detection

## Quick Start

### Basic Usage

```python
from tradepulse.core.neuro.adaptive_calibrator import (
    AdaptiveCalibrator,
    CalibrationMetrics,
)
from tradepulse.core.neuro.neuro_optimizer import (
    NeuroOptimizer,
    OptimizationConfig,
)

# Initialize
initial_params = {
    'dopamine': {'discount_gamma': 0.99, 'learning_rate': 0.01},
    'serotonin': {'stress_threshold': 0.15},
    'gaba': {'k_inhibit': 0.4},
    'na_ach': {'arousal_gain': 1.2},
}

calibrator = AdaptiveCalibrator(initial_params)
optimizer = NeuroOptimizer(OptimizationConfig())

# Optimization loop
for iteration in range(100):
    # Collect performance metrics
    metrics = CalibrationMetrics(
        sharpe_ratio=1.5,
        max_drawdown=0.08,
        win_rate=0.65,
        # ... other metrics
    )
    
    # Calibrate parameters
    calibrated_params = calibrator.step(metrics)
    
    # Optimize for balance
    neuro_state = collect_neuromodulator_state()
    optimized_params, balance = optimizer.optimize(
        calibrated_params,
        neuro_state,
        metrics.composite_score(),
    )
    
    # Use optimized parameters
    apply_parameters(optimized_params)
```

### Validation

Run the validation script to verify functionality:

```bash
python examples/neuro_optimization_validation.py
```

For reproducible results in benchmarks and validation runs, initialize a single
global seed (for example via `utils.seed.set_global_seed(DEFAULT_SEED)`) before
any NumPy-driven sampling.

## Architecture

```
Trading System
     │
     ▼
┌─────────────────────┐
│ Neuromodulators     │
│ (DA, 5-HT, GABA,    │
│  NA/ACh)            │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Performance Metrics │
└─────────┬───────────┘
          │
     ┌────┴────┐
     │         │
     ▼         ▼
┌─────────┐ ┌─────────┐
│Adaptive │ │  Neuro  │
│Calibra- │ │Optimizer│
│tor      │ │         │
└────┬────┘ └────┬────┘
     │           │
     └─────┬─────┘
           │
           ▼
    Updated Parameters
```

## Key Algorithms

### Simulated Annealing (Calibrator)

1. Start with initial parameters and high temperature
2. Generate candidate parameters via perturbation
3. Accept if score improves, or with probability exp(Δ/T) if worse
4. Decay temperature over time
5. Reset exploration if stuck in local optimum

### Homeostatic Optimization (Optimizer)

1. Calculate balance metrics (DA/5-HT, E/I, arousal-attention)
2. Compute multi-objective function (performance + balance + stability)
3. Estimate gradients toward homeostatic setpoints, scaling magnitude by deviation
4. Apply momentum-based parameter updates
5. Monitor health and convergence

## Parameters

### Calibration Parameters

- **temperature_initial**: Initial exploration temperature (default: 1.0)
- **temperature_decay**: Temperature decay rate (default: 0.95)
- **patience**: Iterations without improvement before reset (default: 50)
- **perturbation_scale**: Scale of parameter perturbations (default: 0.1)

### Optimization Parameters

- **balance_weight**: Weight for homeostatic balance (default: 0.35)
- **performance_weight**: Weight for trading performance (default: 0.45)
- **stability_weight**: Weight for consistency (default: 0.20)
- **learning_rate**: Base learning rate for updates (default: 0.01)
- **momentum**: Momentum factor for smoothing (default: 0.9)

## Monitoring

### Calibration Metrics

Track via `get_calibration_report()`:
- Current iteration and best score
- Temperature (exploration level)
- Iterations since last improvement
- Recent performance trends
- Actionable recommendations

### Optimization Metrics

Track via `get_optimization_report()`:
- Current and best objective values
- Balance score and homeostatic deviation
- Convergence status
- Health assessment with specific issues
- Performance trend

## Integration

### With NeuroOrchestrator

```python
from tradepulse.core.neuro.neuro_orchestrator import (
    NeuroOrchestrator,
    TradingScenario,
)

# Generate initial configuration
scenario = TradingScenario(
    market="BTC/USDT",
    timeframe="1h",
    risk_profile="moderate",
)

orchestrator = NeuroOrchestrator()
initial_output = orchestrator.orchestrate(scenario)

# Initialize optimization with orchestrated parameters
calibrator = AdaptiveCalibrator(initial_output.parameters)
optimizer = NeuroOptimizer(OptimizationConfig())

# Run optimization...
```

### With Neuromodulator Controllers

```python
from tradepulse.core.neuro.dopamine.dopamine_controller import DopamineController
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController
# ... other controllers

# After optimization
optimized_params, balance = optimizer.optimize(...)

# Apply to controllers
dopamine_controller.config = update_config(
    dopamine_controller.config,
    optimized_params['dopamine']
)
serotonin_controller.config = update_config(
    serotonin_controller.config,
    optimized_params['serotonin']
)
```

## Examples

### 1. Simple Calibration

See `examples/neuro_optimization_validation.py`

### 2. Full Optimization Cycle

See `examples/neuro_optimization_cycle.py`

### 3. Integration Demo

See `examples/neuro_orchestrator_demo.py` for orchestrator integration

## Testing

### Unit Tests

```bash
# Calibrator tests
pytest tests/unit/core/neuro/test_adaptive_calibrator.py -v

# Optimizer tests
pytest tests/unit/core/neuro/test_neuro_optimizer.py -v
```

### Integration Tests

```bash
# Run validation
python examples/neuro_optimization_validation.py

# Full cycle demonstration
PYTHONPATH=. python examples/neuro_optimization_cycle.py
```

## Documentation

- **Full Guide**: See `docs/neuro_optimization_guide.md`
- **Neurodecision Stack**: See `docs/neurodecision_stack.md`
- **Neuromodulators**: See `docs/neuromodulators/`

## Performance Considerations

### Memory Usage

For long-running optimizations, limit history:

```python
# Limit metrics history to last 1000 entries
if len(calibrator.state.metrics_history) > 1000:
    calibrator.state.metrics_history = calibrator.state.metrics_history[-500:]
```

### Convergence

Monitor convergence to avoid unnecessary iterations:

```python
report = optimizer.get_optimization_report()
if report['convergence']['converged']:
    print("Optimization converged - stopping")
    break
```

### Parallelization

Calibrator and optimizer can run in separate threads:

```python
import concurrent.futures

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    future_cal = executor.submit(calibrator.step, metrics)
    future_opt = executor.submit(optimizer.optimize, params, state, score)
    
    calibrated = future_cal.result()
    optimized, balance = future_opt.result()
```

## Troubleshooting

### High Variance in Parameters

**Symptom**: Parameters oscillate between iterations

**Solution**:
- Reduce temperature: `calibrator.state.temperature *= 0.5`
- Reduce learning rate: `optimizer.config.learning_rate *= 0.5`
- Increase momentum: `optimizer.config.momentum = 0.95`

### Poor Balance Scores

**Symptom**: `balance_score < 0.5` consistently

**Solution**:
- Increase balance weight: `config.balance_weight = 0.50`
- Check specific ratios in balance metrics
- Review neuromodulator state collection

### Slow Convergence

**Symptom**: Many iterations without convergence

**Solution**:
- Relax convergence threshold: `config.convergence_threshold = 0.01`
- Reduce objective conflict (adjust weights)
- Use performance smoothing

## Future Enhancements

- [ ] Bayesian optimization for calibration
- [ ] Multi-asset optimization coordination
- [ ] Regime-specific parameter sets
- [ ] Online learning rate adaptation
- [ ] Distributed optimization for large-scale systems

## References

- [Simulated Annealing](https://en.wikipedia.org/wiki/Simulated_annealing)
- [Multi-Objective Optimization](https://en.wikipedia.org/wiki/Multi-objective_optimization)
- [Homeostasis](https://en.wikipedia.org/wiki/Homeostasis)
- [Momentum Optimization](https://en.wikipedia.org/wiki/Stochastic_gradient_descent#Momentum)

## License

See LICENSE file in repository root.

## Contributing

See CONTRIBUTING.md for guidelines on contributing to this module.
