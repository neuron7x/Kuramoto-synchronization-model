# NaK Controller Specification

**Version:** 1.0  
**Status:** Production  
**Last Updated:** 2025-11-10

## Overview

The **NaK (Na⁺/K⁺ ATPase) Controller** is a neuro-inspired risk management system that dynamically adjusts trading limits based on metabolic-style energy dynamics. Named after the sodium-potassium pump that maintains neuronal membrane potential, this controller models strategy "health" through energy reserves, cumulative load, and engagement metrics.

## Neurophysiological Analogue

### Biological Inspiration

The NaK controller draws from several CNS regulatory mechanisms:

1. **Neuronal Bioenergetics**: Energy (E) models ATP/glucose reserves; Load (L) models firing rate and metabolic cost (Attwell & Laughlin, 2001).

2. **Homeostatic Regulation**: PI controller maintains Engagement Index (EI) in a target band, analogous to maintaining blood glucose, pH, or neurotransmitter levels.

3. **Neuromodulatory Systems**: Four key modulators adjust behavior based on context:
   - **Dopamine (DA)**: Reward prediction error (RPE) from unexpected gains/losses
   - **Noradrenaline (NA)**: Arousal response to volatility/uncertainty
   - **Serotonin (5-HT)**: Inhibitory signal from drawdown/punishment
   - **Acetylcholine (ACh)**: Attentional focus based on portfolio exposure

4. **Global Arousal States**: Three-regime system (GREEN/AMBER/RED) mimics brainstem arousal modulation by locus coeruleus (LC-NE) and periaqueductal gray (PAG).

### Key References

- **Attwell & Laughlin (2001)**: "An Energy Budget for Signaling in the Grey Matter of the Brain"
- **Schultz et al. (1997)**: "A Neural Substrate of Prediction and Reward"
- **Aston-Jones & Cohen (2005)**: "An Integrative Theory of Locus Coeruleus-Norepinephrine Function"
- **Cools et al. (2011)**: "Serotonin and Dopamine: Unifying Affective, Activational, and Decision Functions"

## Mathematical Model

### State Variables

| Variable | Range | Description |
|----------|-------|-------------|
| **L** | [L_min, L_max] | Load (cumulative activity cost) |
| **E** | [0, E_max] | Energy (metabolic reserves) |
| **EI** | [0, 1] | Engagement Index (health metric) |
| **I** | [-I_max, I_max] | PI integrator state |
| **debt** | [0, ∞) | Energy deficit accumulator |

### Discrete-Time Dynamics

#### 1. Load Update

```
L[k+1] = clip(L[k] + Δ_L[k] + ε[k], L_min, L_max)

Δ_L[k] = w_n·trades + w_v·vol' + w_d·DD + w_e·errors + w_l·latency + w_s·slip

vol' = vol · (1 - α_NA · NA[k])

ε[k] ~ N(0, σ_noise · vol)
```

**Parameters:**
- `w_*`: Load weights (must sum to ≤ 1.0)
- `α_NA`: NA scaling factor (typical: 0.6)
- `σ_noise`: Noise standard deviation (typical: 0.01)

#### 2. Energy Update

```
Δ_E[k] = a_p·PnL - a_n·trades - a_v·vol' + a_g·glial [+ a_DA·δ_DA]

If E[k] + Δ_E[k] < 0:
    debt[k+1] = debt[k] + |E[k] + Δ_E[k]|
    E[k+1] = 0
Else:
    debt[k+1] = max(0, debt[k]·0.95 - 0.01)
    recovery = 0.05 · (1 - min(1, debt[k+1]))
    E[k+1] = clip(E[k] + Δ_E[k] + recovery, 0, E_max)
```

**Parameters:**
- `a_p`: PnL gain coefficient (typical: 0.4)
- `a_n`: Trade cost coefficient (typical: 0.25)
- `a_v`: Volatility cost coefficient (typical: 0.25)
- `a_g`: Glial support coefficient (typical: 0.2)
- `a_DA`: Dopamine boost coefficient (typical: 0.1)

**Debt Mechanism:**
- Accumulates when energy would go negative
- Decays exponentially at 5% per step
- Blocks full recovery until repaid

#### 3. Engagement Index

```
EI[k] = clip(u_e·E_norm + u_l·L_norm + u_p·PnL_norm, 0, 1)

E_norm = E / E_max
L_norm = 1 - (L - L_min) / (L_max - L_min)
PnL_norm = (PnL / scale + 1) / 2
```

**Parameters:**
- `u_e`: Energy weight (typical: 0.55)
- `u_l`: Load weight (typical: 0.35)
- `u_p`: PnL weight (typical: 0.10)

**Interpretation:**
- EI < EI_crit (e.g., 0.15): Strategy suspended
- EI ∈ [EI_low, EI_high] (e.g., [0.35, 0.65]): Nominal operating band
- EI > EI_high: Excess capacity, increase risk

#### 4. Neuromodulators

```
DA[k] = clip(0.5 + β_DA · δ_reward, 0, 1)         # Dopamine (RPE)
NA[k] = clip(γ_NA · σ_global, 0, 1)                # Noradrenaline (arousal)
5HT[k] = clip(η_5HT · DD_portfolio, 0, 1)          # Serotonin (inhibition)
ACh[k] = clip(0.5 + η_ACh · exposure, 0, 1)        # Acetylcholine (attention)
```

**Parameters:**
- `β_DA`: DA sensitivity (typical: 0.8)
- `γ_NA`: NA gain (typical: 1.0)
- `η_5HT`: 5-HT gain (typical: 1.0)
- `η_ACh`: ACh sensitivity (typical: 0.6)

#### 5. PI Control

```
e[k] = (EI[k] - c) / w                         # Normalized error
ε[k] = tanh(e[k])                              # Saturated error
I[k] = clip(I[k-1] + ε[k], -I_max, I_max)     # Integrator update
ι[k] = tanh(I[k] / (I_max/2))                 # Saturated integral term
u[k] = K_p · ε[k] + K_i · ι[k]                # Control signal
r_raw[k] = clip(1.0 + u[k], r_min, r_max)     # Risk target
```

Where:
- `c = (EI_low + EI_high) / 2`: Band center
- `w = (EI_high - EI_low) / 2 · β_expand`: Band half-width

**Parameters:**
- `K_p`: Proportional gain (typical: 0.6)
- `K_i`: Integral gain (typical: 0.08)
- `I_max`: Integrator bound (typical: 0.8)

#### 6. Global Mode Selection

```
If DD_portfolio ≥ DD_red OR σ_global ≥ σ_red:
    mode = RED
Elif DD_portfolio ≥ DD_amber OR σ_global ≥ σ_amber:
    mode = AMBER
Else:
    mode = GREEN
```

**Parameters:**
- `σ_amber, σ_red`: Volatility thresholds (typical: 0.7, 0.9)
- `DD_amber, DD_red`: Drawdown thresholds (typical: 0.4, 0.7)

**Mode Effects:**
| Mode | Risk Mult. | Activity Mult. | Band Expand |
|------|-----------|----------------|-------------|
| GREEN | 1.00 | 1.20 | 1.00 |
| AMBER | 0.65 | 0.90 | 1.25 |
| RED | 0.00 | 0.60 | 1.50 |

#### 7. Risk Modulation and Output

```
r_DA[k] = clip(r_raw[k] + α_DA·(DA[k] - 0.5), r_min, r_max)  # DA modulation
r_mode[k] = r_DA[k] · risk_mult[mode]                        # Mode scaling
r[k] = rate_limit(r[k-1], r_mode[k], Δ_max, r_min, r_max)   # Rate limiting

f_ACh[k] = clip(activity_mult[mode] · (0.5 + ACh[k]), 0.25, 1.5)
f[k] = max(f_min, min(f_max, EI[k] · f_ACh[k]))
cooldown[k] = max(1, ⌊cooldown_base / f[k]⌋)

suspended[k] = (EI[k] < EI_crit) OR (mode == RED)
```

**Parameters:**
- `α_DA`: DA modulation gain (typical: 0.25)
- `Δ_max`: Max risk change per step (typical: 0.20)
- `f_min, f_max`: Frequency bounds (typical: 0.25, 1.50)

### Suspension Hysteresis

To prevent oscillation near the critical threshold:

```
If suspended[k-1]:
    suspended[k] = EI[k] < (EI_crit + EI_hysteresis) OR risk_mult == 0
Else:
    suspended[k] = EI[k] < EI_crit OR risk_mult == 0
```

**Parameter:**
- `EI_hysteresis`: Hysteresis width (typical: 0.05)

## Configuration Schema

### Core Bounds

```yaml
L_min: 0.0          # Minimum load
L_max: 1.0          # Maximum load
E_max: 1.0          # Maximum energy
```

### EI Control Band

```yaml
EI_low: 0.35        # Lower band edge
EI_high: 0.65       # Upper band edge
EI_crit: 0.15       # Suspension threshold
EI_hysteresis: 0.05 # Unsuspension threshold offset
```

### PI Controller

```yaml
Kp: 0.6             # Proportional gain
Ki: 0.08            # Integral gain
I_max: 0.8          # Integrator bound
```

### Risk/Frequency Limits

```yaml
r_min: 0.2          # Minimum risk factor
r_max: 1.8          # Maximum risk factor
f_min: 0.25         # Minimum frequency multiplier
f_max: 1.50         # Maximum frequency multiplier
delta_r_limit: 0.20 # Max risk change per step
```

### Load Weights

```yaml
w_n: 0.15           # Trade count weight
w_v: 0.25           # Volatility weight
w_d: 0.30           # Drawdown weight
w_e: 0.10           # Tech errors weight
w_l: 0.10           # Latency weight
w_s: 0.10           # Slippage weight
```

**Constraint:** `Σw_i ≤ 1.0`

### Energy Coefficients

```yaml
a_p: 0.40           # PnL gain coefficient
a_n: 0.25           # Trade cost coefficient
a_v: 0.25           # Volatility cost coefficient
a_g: 0.20           # Glial support coefficient
a_da: 0.10          # Dopamine boost coefficient
```

### EI Weights

```yaml
u_e: 0.55           # Energy weight
u_l: 0.35           # Load weight
u_p: 0.10           # PnL weight
```

**Constraint:** `u_e + u_l + u_p > 0` (recovery reserve)

### Neuromodulator Gains

```yaml
beta_DA: 0.8        # Dopamine sensitivity
eta_ACh: 0.6        # Acetylcholine sensitivity
da_gain: 0.25       # Dopamine modulation strength
na_vol_gain: 1.0    # Noradrenaline arousal gain
na_scale: 0.6       # NA volatility scaling
ht_dd_gain: 1.0     # Serotonin inhibition gain
```

### Global Mode Thresholds

```yaml
vol_amber: 0.7      # AMBER volatility threshold
vol_red: 0.9        # RED volatility threshold
dd_amber: 0.4       # AMBER drawdown threshold
dd_red: 0.7         # RED drawdown threshold
```

**Constraint:** `*_amber < *_red`

### Mode Multipliers

```yaml
risk_mult:
  GREEN: 1.00
  AMBER: 0.65
  RED: 0.00

activity_mult:
  GREEN: 1.20
  AMBER: 0.90
  RED: 0.60

band_expand:
  GREEN: 1.00
  AMBER: 1.25
  RED: 1.50
```

### Noise

```yaml
noise_sigma: 0.01   # Load noise standard deviation
```

## Usage Examples

### Basic Initialization

```python
from pathlib import Path
from nak_controller.runtime.controller import NaKController

# Load controller with config
controller = NaKController(
    config_path=Path("nak_controller/conf/nak.yaml"),
    seed=42  # For reproducibility
)
```

### Single Step

```python
# Prepare observations
local_obs = {
    "trades": 0.5,           # Normalized trade count
    "pnl": 0.002,            # Raw PnL
    "pnl_scale": 0.01,       # PnL normalization scale
    "local_vol": 0.3,        # Local volatility [0, 1]
    "local_dd": 0.15,        # Local drawdown [0, 1]
    "tech_errors": 0.02,     # Error rate [0, 1]
    "latency": 0.1,          # Latency metric [0, 1]
    "slippage": 0.0005,      # Slippage rate [0, 1]
    "glial_support": 0.5,    # External support [0, 1]
}

global_obs = {
    "global_vol": 0.4,       # Global volatility [0, 1]
    "portfolio_dd": 0.2,     # Portfolio drawdown [0, 1]
    "exposure": 0.6,         # Portfolio exposure
    "unexpected_reward": 0.05, # RPE signal
}

bases = {
    "cooldown_ms_base": 2000.0  # Base cooldown in milliseconds
}

# Execute control step
result = controller.step("strategy_1", local_obs, global_obs, bases)

# Extract outputs
risk_factor = result["risk_per_trade_factor"]  # ∈ [r_min, r_max]
max_pos_factor = result["max_position_factor"] # == risk_factor
cooldown_ms = result["cooldown_ms"]            # Computed from EI and ACh
is_suspended = result["is_suspended"]          # bool
mode = result["mode"]                          # "GREEN"|"AMBER"|"RED"
```

### TACL Metrics Export

```python
# Export all state for monitoring
metrics = controller.export_tacl_metrics("strategy_1")

print(f"Energy: {metrics['tacl.nak.energy']:.3f}")
print(f"Load: {metrics['tacl.nak.load']:.3f}")
print(f"EI: {metrics['tacl.nak.engagement_index']:.3f}")
print(f"Dopamine: {metrics['tacl.nak.dopamine']:.3f}")
print(f"Mode: {result['mode']}")
```

### Multi-Strategy Management

```python
# Controller maintains separate state per strategy_id
strategies = ["momentum_1", "mean_rev_2", "arb_3"]

for strat_id in strategies:
    local = get_local_obs(strat_id)
    global_view = get_global_obs()
    bases = get_bases(strat_id)
    
    result = controller.step(strat_id, local, global_view, bases)
    apply_limits(strat_id, result)
```

### Reset and Re-initialization

```python
# Reset all state, optionally with new seed
controller.reset(seed=1337)

# Or reset without seed to use random sequence
controller.reset()
```

### Integration Hook

```python
from nak_controller.integration.hook import NaKHook

# Thin wrapper for strategy integration
hook = NaKHook(
    config_path="nak_controller/conf/nak.yaml",
    seed=42
)

# Compute scaled limits directly
limits = hook.compute_limits(
    strategy_id="strat_1",
    local_obs=local_obs,
    global_obs=global_obs,
    base_risk_per_trade=0.02,    # Base risk in account currency
    base_max_position=10.0,       # Base position size
    base_cooldown_ms=1500.0       # Base cooldown
)

# limits contains both factors and scaled values
risk_per_trade = limits["risk_per_trade"]          # Scaled
max_position = limits["max_position"]              # Scaled
cooldown_ms = limits["cooldown_ms"]                # Scaled
```

## Invariants and Safety Properties

### State Bounds

All state variables remain bounded at all times:

```
L ∈ [L_min, L_max]
E ∈ [0, E_max]
EI ∈ [0, 1]
I ∈ [-I_max, I_max]
debt ≥ 0
```

### Output Bounds

All control outputs are constrained:

```
r ∈ [r_min, r_max]
f ∈ [f_min, f_max]
cooldown ≥ 1 ms
```

### Mode-Suspension Consistency

```
mode == "RED" ⟹ suspended == True
```

This is enforced as a runtime assertion.

### Risk-Position Consistency

```
max_position_factor == risk_factor
```

Ensures deterministic sizing from a single control signal.

### Rate Limiting

```
|r[k] - r[k-1]| ≤ delta_r_limit
```

Prevents abrupt position changes.

### Monotonicity

When EI increases monotonically, risk exposure eventually increases (assuming no mode change or suspension).

## Testing Guidelines

### Determinism

All tests use fixed seeds to ensure reproducibility:

```python
controller = NaKController(config_path, seed=42)
```

### Coverage Requirements

- Branch coverage: ≥ 92%
- Current coverage: 99.59%

### Test Categories

1. **Unit Tests**: Individual function correctness
   - Neuromodulator calculations
   - PI control step logic
   - Energy/load updates
   - Mode selection

2. **Integration Tests**: Controller behavior
   - Multi-step sequences
   - State transitions
   - Suspension/unsuspension
   - Seed reproducibility

3. **Property Tests**: Invariant checking
   - State bounds preservation
   - Output bounds enforcement
   - Monotonicity properties

### Key Test Scenarios

- **Seed reproducibility**: Same seed → identical outputs
- **Hysteresis**: Suspension requires recovery beyond EI_crit + hysteresis
- **RED mode suspension**: RED mode always suspends
- **Rate limiting**: Abrupt changes are clamped to delta_r_limit
- **Debt accumulation**: Negative energy accumulates as debt
- **TACL metrics**: All metrics exported correctly

## Performance Characteristics

### Computational Complexity

- **Per-step cost**: O(1) with respect to number of strategies
- **Memory**: O(n) where n is number of unique strategy_ids

### Typical Step Time

- ~0.1 ms per strategy per step (Python, single-core)

### Recommended Update Frequency

- 1 Hz to 10 Hz (1–10 steps per second per strategy)

## Troubleshooting

### Common Issues

1. **Immediate suspension after init**
   - Check that EI_low < EI_high and initial E=0.5 is reasonable
   - Verify EI_crit < EI_low (separation needed)

2. **Oscillating suspension state**
   - Increase EI_hysteresis (e.g., 0.05 → 0.10)
   - Widen EI band (increase EI_high - EI_low)

3. **Risk factor stuck at r_min or r_max**
   - Check K_p and K_i gains (may be too aggressive)
   - Verify EI is within reasonable range

4. **No response to stress (vol/DD)**
   - Verify vol_amber/red and dd_amber/red thresholds
   - Check risk_mult.RED == 0.0 (should force suspension)

### Debugging Tools

1. **Export TACL metrics** to see all internal state
2. **Check `result["diag"]`** for per-step diagnostics
3. **Enable INFO logging** to see step-by-step telemetry

## Changelog

### v1.0 (2025-11-10)

- Initial production release
- Full neuro-mathematical documentation
- TACL metrics integration
- Type-safe implementation (mypy clean)
- 99.59% branch coverage

## References

1. Attwell, D., & Laughlin, S. B. (2001). An energy budget for signaling in the grey matter of the brain. *Journal of Cerebral Blood Flow & Metabolism*, 21(10), 1133-1145.

2. Schultz, W., Dayan, P., & Montague, P. R. (1997). A neural substrate of prediction and reward. *Science*, 275(5306), 1593-1599.

3. Aston-Jones, G., & Cohen, J. D. (2005). An integrative theory of locus coeruleus-norepinephrine function: adaptive gain and optimal performance. *Annu. Rev. Neurosci.*, 28, 403-450.

4. Cools, R., Nakamura, K., & Daw, N. D. (2011). Serotonin and dopamine: unifying affective, activational, and decision functions. *Neuropsychopharmacology*, 36(1), 98-113.

5. Hasselmo, M. E., & Sarter, M. (2011). Modes and models of forebrain cholinergic neuromodulation of cognition. *Neuropsychopharmacology*, 36(1), 52-73.

6. Harris, J. J., Jolivet, R., & Attwell, D. (2012). Synaptic energy use and supply. *Neuron*, 75(5), 762-777.

7. Borbély, A. A. (1982). A two process model of sleep regulation. *Human neurobiology*, 1(3), 195-204.
