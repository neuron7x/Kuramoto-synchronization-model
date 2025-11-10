# NaK Neuro-Energetic Controller

**A biologically-inspired risk management system for algorithmic trading**

NaK is a neuro-energetic limit controller designed for multi-strategy trading
systems. Named after the Na⁺/K⁺ ATPase pump that maintains neuronal membrane
potential, it models strategy "health" through metabolic-style energy dynamics,
producing adaptive risk, position, and frequency limits.

## 🧠 Neuro-Inspired Architecture

The controller implements several CNS-inspired mechanisms:

### Core Dynamics

- **Energy (E)**: Metabolic reserves (like ATP/glucose in neurons)
- **Load (L)**: Cumulative activity cost (like neuronal firing rate)
- **Engagement Index (EI)**: Overall health metric determining trading capacity

### Neuromodulators

Four key modulators adjust behavior based on market/portfolio context:

- **🔴 Dopamine (DA)**: Reward prediction error (RPE) → risk appetite modulation
- **🟠 Noradrenaline (NA)**: Arousal from volatility → stress response
- **🟢 Serotonin (5-HT)**: Inhibition from drawdown → risk suppression
- **🔵 Acetylcholine (ACh)**: Attention gating → activity scaling

### Global Modes

Three arousal states modulate all strategies simultaneously:

- **GREEN**: Normal conditions (full capacity)
- **AMBER**: Elevated stress (reduced capacity)
- **RED**: Crisis mode (forced suspension)

## ✨ Key Features

- ✅ **Deterministic**: Fixed seeds ensure reproducible behavior
- ✅ **Type-Safe**: Full mypy compliance with strict type hints
- ✅ **Observable**: Comprehensive TACL metrics for monitoring
- ✅ **Configurable**: All parameters externalized to YAML
- ✅ **Tested**: 99.59% branch coverage, 49 passing tests
- ✅ **Production-Ready**: Validated energetic dynamics, safety invariants

## 🚀 Quick Start

### Installation

```bash
cd nak_controller
python -m pip install -e .
```

### Basic Usage

```python
from pathlib import Path
from nak_controller.runtime.controller import NaKController

# Initialize controller with config
controller = NaKController(
    config_path=Path("conf/nak.yaml"),
    seed=42  # For reproducibility
)

# Define observations
local_obs = {
    "trades": 0.5,           # Normalized trade count [0, 1]
    "pnl": 0.002,            # Raw PnL
    "pnl_scale": 0.01,       # Normalization scale
    "local_vol": 0.3,        # Volatility [0, 1]
    "local_dd": 0.15,        # Drawdown [0, 1]
    "tech_errors": 0.02,     # Error rate [0, 1]
    "latency": 0.1,          # Latency metric [0, 1]
    "slippage": 0.0005,      # Slippage rate [0, 1]
    "glial_support": 0.5,    # External support [0, 1]
}

global_obs = {
    "global_vol": 0.4,       # Global volatility [0, 1]
    "portfolio_dd": 0.2,     # Portfolio drawdown [0, 1]
    "exposure": 0.6,         # Portfolio exposure
    "unexpected_reward": 0.05, # Reward prediction error
}

bases = {"cooldown_ms_base": 2000.0}

# Execute control step
result = controller.step("strategy_1", local_obs, global_obs, bases)

# Extract control outputs
print(f"Risk Factor: {result['risk_per_trade_factor']:.3f}")
print(f"Cooldown: {result['cooldown_ms']} ms")
print(f"Mode: {result['mode']}")
print(f"Suspended: {result['is_suspended']}")
print(f"EI: {result['EI']:.3f}")
```

### TACL Metrics Export

```python
# Export all internal state for monitoring
metrics = controller.export_tacl_metrics("strategy_1")

print(f"Energy: {metrics['tacl.nak.energy']:.3f}")
print(f"Load: {metrics['tacl.nak.load']:.3f}")
print(f"Dopamine: {metrics['tacl.nak.dopamine']:.3f}")
```

### CLI Validation

```bash
# Run deterministic validation
python -m nak_controller.cli.run_validate \
  --config nak_controller/conf/nak.yaml \
  --steps 200 \
  --seeds 2 \
  --seed 1337
```

## 📁 Project Structure

```
nak_controller/
├── core/                   # State machines and energetic models
│   ├── state.py           # StrategyState dataclass
│   ├── energetics.py      # Energy/load dynamics
│   ├── params.py          # Immutable parameters
│   ├── config.py          # Pydantic configuration
│   └── metrics.py         # Normalization utilities
├── control/                # Control algorithms
│   ├── pi.py              # PI controller
│   ├── neuromods.py       # Neuromodulator transforms
│   └── global_mode.py     # Regime classification
├── runtime/                # Orchestration
│   └── controller.py      # Main NaKController class
├── integration/            # External integration
│   └── hook.py            # Strategy hook adapter
├── validate/               # Validation tools
│   ├── sim_env.py         # Synthetic environment
│   └── cv_runner.py       # Cross-validation harness
├── cli/                    # Command-line tools
│   ├── run_validate.py    # Validation runner
│   └── run_cv.py          # Cross-validation runner
├── tests/                  # Test suite
│   ├── test_controller_behaviour.py
│   ├── test_config_and_metrics.py
│   └── test_cli.py
├── conf/                   # Configuration files
│   └── nak.yaml           # Default config
├── README.md              # This file
└── SPEC.md                # Detailed mathematical specification
```

## 📊 Configuration

All parameters are defined in `conf/nak.yaml`. Key sections:

### Control Parameters

```yaml
Kp: 0.6             # Proportional gain
Ki: 0.08            # Integral gain
EI_low: 0.35        # Target band lower edge
EI_high: 0.65       # Target band upper edge
EI_crit: 0.15       # Suspension threshold
```

### Neuromodulator Gains

```yaml
beta_DA: 0.8        # Dopamine sensitivity
eta_ACh: 0.6        # Acetylcholine sensitivity
na_vol_gain: 1.0    # Noradrenaline arousal
ht_dd_gain: 1.0     # Serotonin inhibition
```

### Global Mode Thresholds

```yaml
vol_amber: 0.7      # AMBER volatility trigger
vol_red: 0.9        # RED volatility trigger
dd_amber: 0.4       # AMBER drawdown trigger
dd_red: 0.7         # RED drawdown trigger
```

See [SPEC.md](SPEC.md) for complete parameter reference and mathematical details.

## 🧪 Testing

### Run Test Suite

```bash
# All tests with coverage
pytest nak_controller/tests --cov=nak_controller --cov-report=term-missing

# Current coverage: 99.59% (49 tests)
```

### Run Type Checking

```bash
mypy nak_controller --config-file=mypy.ini
# Success: no issues found in 21 source files
```

### Validation Benchmarks

```bash
# Cross-validation with multiple seeds
python -m nak_controller.cli.run_cv \
  --config conf/nak.yaml \
  --folds 5 \
  --steps 1000
```

## 📖 Documentation

- **[SPEC.md](SPEC.md)**: Complete mathematical specification with equations
- **[Docstrings](runtime/controller.py)**: Inline documentation with neuro background
- **[Tests](tests/)**: Usage examples and edge cases

## 🔬 Neuro-Mathematical Model

### Energy Dynamics

```
E[k+1] = clip(E[k] + a_p·PnL - a_n·trades - a_v·vol + a_g·glial, 0, E_max)
```

### Load Dynamics

```
L[k+1] = clip(L[k] + w_n·trades + w_v·vol + w_d·DD + w_e·errors + ε, L_min, L_max)
```

### Engagement Index

```
EI[k] = u_e·(E/E_max) + u_l·(1 - L/L_max) + u_p·PnL_norm
```

### PI Control

```
u[k] = K_p·tanh((EI - c)/w) + K_i·tanh(I/I_max)
r[k] = clip(1.0 + u[k], r_min, r_max)
```

See [SPEC.md](SPEC.md) for full derivations and parameter tuning guidelines.

## 🛡️ Safety Invariants

The controller enforces several critical safety properties:

1. **State bounds**: All state variables remain bounded
2. **Output limits**: Risk/frequency within configured ranges
3. **Mode consistency**: RED mode always suspends
4. **Rate limiting**: Prevents abrupt position changes
5. **Debt tracking**: Energy deficits must be repaid

All invariants are tested and validated (99.59% coverage).

## 🔧 Troubleshooting

### Common Issues

**Q: Strategy suspends immediately after init**  
A: Check EI_crit < EI_low and initial E=0.5 is reasonable

**Q: Oscillating suspension state**  
A: Increase EI_hysteresis or widen EI band

**Q: Risk stuck at r_min or r_max**  
A: Check K_p/K_i gains, verify EI range

See [SPEC.md § Troubleshooting](SPEC.md#troubleshooting) for more.

## 📚 References

1. Attwell & Laughlin (2001): "An Energy Budget for Signaling in the Grey Matter"
2. Schultz et al. (1997): "A Neural Substrate of Prediction and Reward"
3. Aston-Jones & Cohen (2005): "Integrative Theory of Locus Coeruleus-NE Function"
4. Cools et al. (2011): "Serotonin and Dopamine: Unifying Affective Functions"

## 📝 License

See [LICENSE](LICENSE) and [SECURITY.md](SECURITY.md) for details.

## 🤝 Contributing

Pull requests welcome! Ensure tests pass and coverage remains ≥ 92%.

---

**Built with ❤️ for the TradePulse neuroeconomic trading platform**
