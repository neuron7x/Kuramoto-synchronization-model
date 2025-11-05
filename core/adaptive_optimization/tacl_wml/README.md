# WML (Weighted Myelin Layer) Adaptive Optimization

## Overview

The WML (Weighted Myelin Layer) is a neurobiologically-inspired adaptive optimization system for TradePulse. It dynamically adjusts system parameters based on performance metrics, market regimes, and risk conditions.

## Neurobiological Foundations

WML implements several key principles from neuroscience:

### 1. Plasticity (Hebbian Learning + Synaptic Decay)

**Code:**
```python
tentative = s.myelin + eta * delta * u - lam * s.inactive_for
```

**Neuroscience Mapping:**
- **LTP (Long-Term Potentiation)**: `eta * delta * u` - Connections strengthen when they produce positive results
- **LTD (Long-Term Depression)**: `lam * s.inactive_for` - Unused connections atrophy
- **Hebbian Rule**: "What fires together, wires together"

### 2. Threat Response (Amygdala + PFC)

**Code:** `RegimeDetector`, `plasticity_schedule`, `risk_freeze_fn`

**Neuroscience Mapping:**
- **RegimeDetector**: Sensory input (thalamus/cortex) assessing threat level
- **Plasticity Schedule**: Neuromodulation - different regimes release "neurotransmitters" that change learning rules
- **SHOCK Regime**: `eta: 0.00` - Acute stress blocks flexible learning (PFC/hippocampus shutdown)
- **Risk Freeze**: Reflexive "freeze" response with priority over learning

### 3. Homeostasis (Free Energy Principle)

**Code:**
```python
F = p99 + α·jitter + β·resource_cost + γ·IS_bp
```

**Neuroscience Mapping:**
- Minimizes "free energy" (total allostatic load)
- Multi-objective optimization across:
  - Latency (p99)
  - Stability (jitter)
  - Resources (metabolic cost)
  - Execution quality (implementation shortfall)

### 4. Action Selection (Basal Ganglia)

**Code:**
```python
F_try < F_now * (1.0 - eps_rel)
```

**Neuroscience Mapping:**
- Forms expectation (F_now)
- Simulates action (probe.measure_after)
- Only acts if predicted outcome is significantly better
- Implements "Actor-Critic" decision making

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     WML Controller                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Regime    │  │  Plasticity  │  │ Risk Freeze  │      │
│  │  Detector   │→ │  Modulation  │→ │   Override   │      │
│  └─────────────┘  └──────────────┘  └──────────────┘      │
│         ↓                ↓                   ↓              │
│  ┌──────────────────────────────────────────────────┐      │
│  │          Free Energy Minimization                │      │
│  │   F = p99 + α·jitter + β·cost + γ·IS_bp        │      │
│  └──────────────────────────────────────────────────┘      │
│         ↓                                                    │
│  ┌──────────────────────────────────────────────────┐      │
│  │         Action Plan Generation                   │      │
│  │   (timing, conduct, metabolic adjustments)       │      │
│  └──────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

```bash
# Enable WML
TP_WML_ENABLED=true

# Implementation shortfall penalty (basis points)
TP_WML_GAMMA_IS=0.02

# Relative threshold for accepting changes
TP_WML_EPS=0.03

# Minimum interval between optimizations (seconds)
TP_WML_MIN_APPLY_INTERVAL_S=0.2

# Auto-freeze after N consecutive failures
TP_WML_AUTO_FREEZE_FAILS=2

# Expected shortfall limit for risk freeze
TP_ES_LIMIT=0.03
```

### Code Configuration

```python
from core.adaptive_optimization.tacl_wml import WMLConfig

cfg = WMLConfig(
    # Free energy weights
    mfe_alpha=0.5,        # Jitter weight
    mfe_beta=0.3,         # Resource cost weight
    gamma_is=0.02,        # IS penalty (bp)
    eps_rel=0.03,         # Relative threshold
    
    # Myelin bounds
    bounds={"m_min": 0.0, "m_max": 1.0},
    
    # Plasticity by regime
    plasticity_schedule={
        "CALM":     {"eta": 0.04, "lambda_decay": 0.002},
        "TREND":    {"eta": 0.03, "lambda_decay": 0.003},
        "VOLATILE": {"eta": 0.01, "lambda_decay": 0.01},
        "SHOCK":    {"eta": 0.00, "lambda_decay": 0.05},
    }
)
```

## Usage

### Basic Integration

```python
from runtime.hooks_wml import make_wml, step_hot_path

# Initialize once (e.g., at startup)
def risk_freeze():
    """Check if optimization should freeze."""
    return (
        current_ews_state == EWSState.KILL 
        or current_es > ES_LIMIT
    )

wml = make_wml(risk_freeze_fn=risk_freeze)

# In hot path (e.g., feature computation loop)
def compute_features():
    # ... your feature computation code ...
    pass

# Call periodically (every N iterations)
if step_hot_path(wml, "feature_pipe", compute_features):
    logger.info("WML applied optimization")
```

### Four Hot Paths

1. **quotes_ingest**: Parser/resampling
   ```python
   step_hot_path(wml, "quotes_ingest", parse_quotes, is_bp=0.0)
   ```

2. **feature_pipe**: Kuramoto/Ricci/Topo computation
   ```python
   step_hot_path(wml, "feature_pipe", compute_features, is_bp=0.0)
   ```

3. **signal_decide**: Signal generation
   ```python
   step_hot_path(wml, "signal_decide", generate_signals, is_bp=0.0)
   ```

4. **order_execute**: Order execution
   ```python
   step_hot_path(wml, "order_execute", execute_order, is_bp=current_is_bp)
   ```

## Regimes

### CALM (vol_index < 0.3)
- **High plasticity**: `eta=0.04`
- **Low decay**: `lambda_decay=0.002`
- **Behavior**: Aggressive optimization, quick adaptation

### TREND (0.3 ≤ vol_index < 0.6)
- **Moderate plasticity**: `eta=0.03`
- **Moderate decay**: `lambda_decay=0.003`
- **Behavior**: Balanced optimization

### VOLATILE (vol_index ≥ 0.6)
- **Low plasticity**: `eta=0.01`
- **High decay**: `lambda_decay=0.01`
- **Behavior**: Conservative optimization, safety constraints

### SHOCK (extreme latency/jitter)
- **No plasticity**: `eta=0.00`
- **Maximum decay**: `lambda_decay=0.05`
- **Behavior**: Freeze learning, rely on defaults

## Monitoring

### Audit Log

```python
# Access audit logs
logs = wml.audit.get_logs()

for log in logs:
    print(f"Event: {log['event']}")  # WML_APPLY, WML_REJECTED, WML_FROZEN
    print(f"Path: {log['data']['path']}")
    print(f"Free Energy: {log['data']['F_now']} → {log['data']['F_try']}")
    print(f"IS Change: {log['data']['dIS_bp']} bp")
```

### Event Bus

```python
# Subscribe to events
def on_optimization(data):
    print(f"Optimization applied to {data['path']}")

wml.bus.subscribe("WML_APPLY", on_optimization)
```

### State Inspection

```python
# Check path state
state = wml.get_state("feature_pipe")
print(f"Myelin: {state.myelin:.3f}")
print(f"Regime: {state.last_regime.name}")
print(f"Usefulness: {state.recent_usefulness:.3f}")
print(f"Failures: {state.control_failures}")
```

## Testing

Run the test suite:

```bash
pytest tests/adaptive_optimization/test_wml_integration.py -v
```

Run the demo:

```bash
python examples/wml_demo.py
```

## Performance Impact

- **Overhead**: ~0.1-0.2ms per step (negligible)
- **Optimization Interval**: Configurable (default 0.2s minimum)
- **Memory**: ~1KB per hot path state
- **CPU**: No-op on non-Linux (CPU affinity requires Linux)

## Safety Features

### 1. Risk Freeze
- Overrides all optimization when risk conditions are met
- Triggered by EWS=KILL or ES>limit

### 2. Auto-Freeze
- Automatically disables path after repeated control failures
- Default: 2 consecutive failures

### 3. Bounded Optimization
- Myelin constrained to [0.0, 1.0]
- Free energy must improve by threshold (relative or absolute)

### 4. Regime-Based Constraints
- VOLATILE: Limited fusion depth, higher flush intervals
- SHOCK: Aggressive safety constraints, zero-copy disabled

## Troubleshooting

### WML always skips optimization

**Cause**: Free energy not improving or within min_apply_interval

**Solution**: 
- Check `eps_rel` threshold (lower = more aggressive)
- Verify probe is measuring correctly
- Check min_apply_interval setting

### Auto-freeze triggered

**Cause**: Repeated control plane failures

**Solution**:
- Check `TP_CONTROL_URL` if using distributed control
- Verify system actions are not throwing exceptions
- Increase `auto_freeze_fails` threshold

### Unexpected regime detection

**Cause**: vol_index or telemetry values incorrect

**Solution**:
- Implement proper `_current_vol_proxy()` in hooks_wml.py
- Verify telemetry collection is accurate
- Adjust regime thresholds in config

## References

1. **Free Energy Principle**: Friston, K. (2010). "The free-energy principle: a unified brain theory?"
2. **Hebbian Learning**: Hebb, D.O. (1949). "The Organization of Behavior"
3. **Synaptic Homeostasis**: Turrigiano, G. (2012). "Homeostatic synaptic plasticity"
4. **Neuromodulation**: Marder, E. (2012). "Neuromodulation of neuronal circuits"

## License

This implementation is part of TradePulse and follows the same licensing terms.
