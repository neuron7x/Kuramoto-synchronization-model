# Neuro-Optimization Guide

## Overview

This guide covers TradePulse's adaptive neuromodulator calibration and cross-neuromodulator optimization systems. These components enable the neuroscience-grounded AI system to self-tune for optimal trading performance while maintaining homeostatic balance.

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture](#architecture)
3. [Adaptive Calibrator](#adaptive-calibrator)
4. [Cross-Neuromodulator Optimizer](#cross-neuromodulator-optimizer)
5. [Usage Examples](#usage-examples)
6. [Best Practices](#best-practices)
7. [Performance Tuning](#performance-tuning)
8. [Numerical Stability](#numerical-stability)
9. [Troubleshooting](#troubleshooting)

## Introduction

### Motivation

Traditional trading systems use fixed parameters that may not adapt to changing market conditions. TradePulse's neuroscience-inspired architecture includes multiple neuromodulators (dopamine, serotonin, GABA, NA/ACh) that must be coordinated and optimized for each trading scenario.

The optimization system provides:

- **Adaptive Calibration**: Automatically tunes neuromodulator parameters based on performance feedback
- **Homeostatic Balance**: Ensures neuromodulators maintain healthy ratios and interactions
- **Multi-Objective Optimization**: Balances performance, risk, and stability
- **Regime Adaptation**: Adjusts to changing market conditions

### Key Concepts

#### Neuromodulators

TradePulse models four key neuromodulator systems:

1. **Dopamine**: Reward prediction, action selection, exploration
2. **Serotonin**: Stress response, hold decisions, conservative bias
3. **GABA**: Inhibition, impulse control, risk management
4. **NA/ACh**: Arousal, attention, volatility sensitivity

#### Homeostasis

The system maintains homeostatic balance by monitoring:

- **DA/5-HT Ratio**: Dopamine to serotonin ratio (target: ~1.67, acceptable range: **[1.0, 3.0]**)
- **E/I Balance**: Excitation to inhibition ratio (target: ~1.5, acceptable range: **[1.0, 2.5]**)
- **Arousal-Attention Coherence**: Correlation between arousal and attention

#### Invariant Validation

All neuro-optimization runs enforce bounds on the core invariants via
`validate_neuro_invariants` in `src/tradepulse/core/neuro/_validation.py`:

- **DA/5-HT ratio** must stay within the configured bounds (default **[1.0, 3.0]**).
- **E/I balance** must stay within the configured bounds (default **[1.0, 2.5]**).
- **Arousal-attention coherence** must remain in **[0, 1]**.
- **Stability score** must remain in **[0, 1]**.

These checks are called from unit tests and benchmark runs to provide
continuous guardrails during optimization and profiling.

##### Core Invariant Bounds

| Метрика | Допустимий діапазон | Фізичний сенс | Формула |
| --- | --- | --- | --- |
| **DA/5-HT ratio** | **[1.0, 3.0]** | Баланс системи винагороди (DA) та стресового гальмування (5-HT). | `dopamine_level / (serotonin_level + ε)` |
| **E/I balance** | **[1.0, 2.5]** | Співвідношення збудження (DA + arousal) до гальмування (GABA + 5-HT). | `(dopamine_level + na_arousal) / (gaba_inhibition + serotonin_level + ε)` |
| **Arousal-attention coherence** | **[0, 1]** | Узгодженість активації та фокусу уваги (1 — ідеальне узгодження). | `clip(1 - |na_arousal - ach_attention| / 2, 0, 1)` |
| **Stability score** | **[0, 1]** | Стабільність цільової функції у часі (менша дисперсія = вища стабільність). | `clip(1 - std(recent) / max(|mean|, ε), 0, 1)` |

#### Multi-Objective Optimization

Optimization balances three objectives:

1. **Performance** (45%): Risk-adjusted returns (Sharpe ratio)
2. **Balance** (35%): Homeostatic stability
3. **Stability** (20%): Consistency over time

#### Formal Objective

The cross-neuromodulator optimizer solves the following constrained objective:

```
maximize F = w_p * P + w_b * B + w_s * S
```

Subject to:

- **Parameter bounds**: each neuromodulator parameter remains within its validated
  lower/upper limits. Bounds are configured per module/parameter via
  `OptimizationConfig.param_bounds` and applied after each update.
- **Homeostatic invariants**: dopamine/serotonin ratio, excitation/inhibition balance,
  and arousal-attention coherence remain within physiological bounds.

##### Metric Scales and Objective Influence

The optimizer combines metrics that are normalized onto comparable scales before weighting:

- **Performance scale**: Sharpe ratio is normalized from
  **[performance_min, performance_max] → [0, 1]** with clipping.
  - Below `performance_min` maps to **0**, above `performance_max` maps to **1**.
  - Defaults: `performance_min = -2`, `performance_max = 3`.

Formally, the normalization is:

```
performance_norm = clip(
    (performance - performance_min) / (performance_max - performance_min),
    0,
    1
)
```
- **Balance scale**: `overall_balance_score` is already in **[0, 1]** (higher is better).
- **Stability scale**: Derived from recent objective history as
  `1 - std(recent) / max(abs(mean), ε)`, clipped to **[0, 1]**.
  - `abs(mean)` makes negative and positive averages comparable in magnitude.
  - `ε` prevents division by zero or near-zero means from exploding the ratio.
  - Until enough history accumulates, stability defaults to **0.5**.
  - For a fixed mean, higher standard deviation lowers the stability score.
  - Negative mean values are still bounded because the denominator uses `abs(mean)` and the
    final stability score is clipped to **[0, 1]**.

**Mathematical note on normalization and bounds**

- **Arousal-attention coherence** is computed as:
  `aa_coherence = 1 - |na_arousal - ach_attention| / 2`.
- The raw value is explicitly **clipped to [0, 1]** to keep the metric bounded,
  even for extreme arousal/attention inputs.

The composite objective is a **linear combination** of these normalized metrics:

```
objective = (performance_weight * performance_norm
             + balance_weight * balance_score
             + stability_weight * stability_score)
```

Changing weights shifts the optimizer's focus:

- Increasing **performance_weight** prioritizes high Sharpe results (faster response to alpha).
- Increasing **balance_weight** biases toward homeostatic stability (lower stress/overdrive).
- Increasing **stability_weight** penalizes volatile objective trajectories (smoother learning).

### Numerical Stability

All numerically sensitive denominators share the same
`OptimizationConfig.numeric.stability_epsilon` (re-exported as
`tradepulse.core.neuro.numeric_config.STABILITY_EPSILON`) to ensure consistent behavior
across balance, stability, and gradient calculations. The current uses are:

- **Dopamine/serotonin ratio**: `dopamine_level / (serotonin_level + ε)`.
- **Excitation/inhibition balance**: `(dopamine_level + na_arousal) / (gaba_inhibition + serotonin_level + ε)`.
- **Homeostatic deviation normalization**:
  - `|da_5ht_ratio - setpoint| / (setpoint + ε)`
  - `|ei_balance - setpoint| / (setpoint + ε)`
- **Stability objective**: `1 - std(recent) / max(abs(mean), ε)`.
- **Proportional gradient heuristic**: `(value - setpoint) / (setpoint + ε)`,
  including `dopamine_level / (serotonin_level + ε)` for the ratio deviation.

### Logged Metrics

The optimizer logs the core metrics below (via `_log_metrics`) using the
`neuro_opt.<metric>` naming scheme. Ranges reflect validated or clipped bounds.

| Metric name | Units | Expected range |
| --- | --- | --- |
| `neuro_opt.objective` | unitless | **[0, 1]** |
| `neuro_opt.balance_score` | unitless | **[0, 1]** |
| `neuro_opt.homeostatic_dev` | unitless | **[0, ∞)** |
| `neuro_opt.da_5ht_ratio` | ratio | **[1.0, 3.0]** (default config) |
| `neuro_opt.ei_balance` | ratio | **[1.0, 2.5]** (default config) |
| `neuro_opt.aa_coherence` | unitless | **[0, 1]** |

## Math Spec

Strict definitions for core neuro-optimization metrics, aligned with
`src/tradepulse/core/neuro/neuro_optimizer.py`. All inputs must be finite real
values. Unless otherwise noted, parameters are expected to be non-negative.

### `da_5ht_ratio`

**Formula**

```
da_5ht_ratio = dopamine_level / (serotonin_level + epsilon)
```

**Range**

- **[da_min, da_max]** (default **[1.0, 3.0]**, configured via
  `OptimizationConfig.da_5ht_ratio_range`)

**Interpretation**

Relative reward drive (dopamine) vs. stress/hold signaling (serotonin). Higher
values indicate stronger reward-driven behavior.

**Allowed inputs**

- `dopamine_level >= 0`
- `serotonin_level >= 0`
- `epsilon = numeric.stability_epsilon > 0`

### `ei_balance`

**Formula**

```
excitation = dopamine_level + na_arousal
inhibition = gaba_inhibition + serotonin_level
ei_balance = excitation / (inhibition + epsilon)
```

**Range**

- **[ei_min, ei_max]** (default **[1.0, 2.5]**, configured via
  `OptimizationConfig.ei_balance_range`)

**Interpretation**

Excitation-to-inhibition balance. Higher values imply more excitable, risk-on
behavior; lower values indicate stronger inhibitory control.

**Allowed inputs**

- `dopamine_level >= 0`
- `na_arousal >= 0`
- `gaba_inhibition >= 0`
- `serotonin_level >= 0`
- `epsilon = numeric.stability_epsilon > 0`

### `aa_coherence`

**Formula**

```
aa_coherence = 1 - |na_arousal - ach_attention| / 2
aa_coherence = clip(aa_coherence, 0, 1)
```

**Range**

- **[0, 1]**

**Interpretation**

Alignment between arousal (NA) and attention (ACh). Values near 1 indicate
tightly coupled arousal/attention; values near 0 indicate decoupling.

**Allowed inputs**

- `na_arousal`, `ach_attention` finite real values
- Recommended physiological band: **[0, 2]** to keep the pre-clip value within
  **[0, 1]**

### `homeostatic_dev`

**Formula**

```
da_5ht_dev = |da_5ht_ratio - da_5ht_setpoint| / (da_5ht_setpoint + epsilon)
ei_dev     = |ei_balance - ei_setpoint| / (ei_setpoint + epsilon)
homeostatic_dev = (da_5ht_dev + ei_dev) / 2
homeostatic_dev = clip(homeostatic_dev, 0, +∞)
```

**Range**

- **[0, +∞)**

**Interpretation**

Average relative deviation from DA/5-HT and E/I setpoints. Zero is ideal
homeostasis; larger values indicate increasing drift.

**Allowed inputs**

- `da_5ht_ratio`, `ei_balance` finite real values
- `da_5ht_setpoint > 0`, `ei_setpoint > 0`
- `epsilon = numeric.stability_epsilon > 0`

### `balance_score`

**Formula**

```
balance_score = 1 / (1 + homeostatic_dev)
balance_score = clip(balance_score, 0, 1)
```

**Range**

- **(0, 1]** (clipped to **[0, 1]** in implementation)

**Interpretation**

Inverse transform of homeostatic deviation; compresses large deviations while
keeping near-perfect balance close to 1.

**Invariant**

- Larger `homeostatic_dev` implies a smaller `balance_score` (monotonic inverse).

**Allowed inputs**

- `homeostatic_dev >= 0`

### `stability`

**Formula**

```
stability = 1 - std(recent_perf) / max(abs(mean(recent_perf)), epsilon)
stability = clip(stability, 0, 1)
```

If insufficient history (`len(recent_perf) < history_window`), the value
defaults to **0.5** (neutral).

**Range**

- **[0, 1]**

**Interpretation**

Consistency of recent objective values. High stability means low variance
relative to mean magnitude.

**Allowed inputs**

- `recent_perf` list of finite floats
- `history_window > 1`
- `epsilon = numeric.stability_epsilon > 0`

### Metric Ranges

Homeostatic ratio bounds are configured via `OptimizationConfig` (proxied from
`numeric`) and used for clipping plus health diagnostics:

- **DA/5-HT ratio**: `da_5ht_ratio_range = (low, high)` with `low > 0`, `high > 0`,
  and `low < high`. The health assessment flags values below/above these bounds.
- **E/I balance**: `ei_balance_range = (low, high)` with `low > 0`, `high > 0`,
  and `low < high`. The health assessment flags values outside these limits.
- **Arousal-attention coherence**: `aa_coherence_min` in **[0, 1]**; values below
  this threshold produce a warning in the health assessment.

### Failure Modes

Behavior when metrics or inputs exceed their intended bounds.

| Metric | Out-of-range condition | Behavior |
| --- | --- | --- |
| `da_5ht_ratio` | Outside `da_5ht_ratio_range` | **ValueError** via `validate_neuro_invariants` |
| `ei_balance` | Outside `ei_balance_range` | **ValueError** via `validate_neuro_invariants` |
| `aa_coherence` | Raw value < 0 or > 1 | **Clip** to **[0, 1]** |
| `aa_coherence` | < 0.5 (advisory threshold) | **Warning** in health assessment (`issues` list) |
| `homeostatic_dev` | Negative due to numerical drift | **Clip** to **[0, +∞)** |
| `balance_score` | Outside **[0, 1]** due to numeric error | **Clip** to **[0, 1]** |
| `balance_score` | < 0.6 (advisory threshold) | **Warning** status in health assessment |
| `stability` | Outside **[0, 1]** due to mean/variance extremes | **Clip** to **[0, 1]** |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Trading Environment                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐│
│  │  Market   │  │  Orders   │  │   Risk    │  │  Capital ││
│  │   Data    │  │ Execution │  │ Management│  │  P&L     ││
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └────┬─────┘│
└────────┼──────────────┼──────────────┼──────────────┼──────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│              Neuromodulator Controllers                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Dopamine │ │Serotonin │ │   GABA   │ │  NA/ACh  │      │
│  │Controller│ │Controller│ │  Gate    │ │ Modulat. │      │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘      │
└───────┼────────────┼────────────┼────────────┼─────────────┘
        │            │            │            │
        └────────────┴────────────┴────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  NeuroOrchestrator     │◄──────┐
        │  (Coordination)        │       │
        └───────────┬────────────┘       │
                    │                     │
        ┌───────────▼────────────┐       │
        │ Cross-Neuromodulator   │       │
        │     Optimizer          │       │
        │  • Balance Monitoring  │       │
        │  • Gradient Updates    │       │
        │  • Health Assessment   │       │
        └───────────┬────────────┘       │
                    │                     │
        ┌───────────▼────────────┐       │
        │  Adaptive Calibrator   │       │
        │  • Simulated Annealing │       │
        │  • Parameter Search    │───────┘
        │  • Performance Tracking│
        └────────────────────────┘
```

## Adaptive Calibrator

### Overview

The `AdaptiveCalibrator` uses simulated annealing to explore the parameter space and find optimal neuromodulator configurations.

### Key Features

- **Simulated Annealing**: Balances exploration and exploitation
- **Automatic Bounds**: Parameters stay within safe, validated ranges
- **Composite Scoring**: Combines multiple performance metrics
- **Patience Mechanism**: Resets exploration when stuck in local optima
- **State Persistence**: Save and restore calibration state

### API Reference

#### CalibrationMetrics

```python
@dataclass
class CalibrationMetrics:
    sharpe_ratio: float          # Risk-adjusted returns
    max_drawdown: float          # Maximum drawdown (0-1)
    win_rate: float              # Win rate (0-1)
    avg_hold_time: float         # Average position hold time
    dopamine_stability: float    # Dopamine level variance
    serotonin_stress: float      # Average stress level
    gaba_inhibition_rate: float  # Inhibition rate
    na_ach_arousal: float        # Average arousal
    total_trades: int            # Total trades executed
    timestamp: float             # Unix timestamp
```

#### AdaptiveCalibrator

```python
class AdaptiveCalibrator:
    def __init__(
        self,
        initial_params: Dict[str, Any],
        *,
        temperature_initial: float = 1.0,
        temperature_decay: float = 0.95,
        min_temperature: float = 0.01,
        patience: int = 50,
        perturbation_scale: float = 0.1,
    ) -> None:
        """Initialize adaptive calibrator."""
        
    def step(self, metrics: CalibrationMetrics) -> Dict[str, Any]:
        """Execute one calibration step.
        
        Returns:
            Updated parameters for next iteration
        """
        
    def get_best_params(self) -> Dict[str, Any]:
        """Get best parameters found so far."""
        
    def get_calibration_report(self) -> Dict[str, Any]:
        """Generate comprehensive calibration report."""
        
    def export_state(self) -> Dict[str, Any]:
        """Export state for persistence."""
        
    @classmethod
    def from_state(cls, state_dict: Dict[str, Any]) -> AdaptiveCalibrator:
        """Restore from exported state."""
```

### Usage Example

```python
from tradepulse.core.neuro.adaptive_calibrator import (
    AdaptiveCalibrator,
    CalibrationMetrics,
)

# Initialize with starting parameters
initial_params = {
    'dopamine': {
        'discount_gamma': 0.99,
        'learning_rate': 0.01,
        'burst_factor': 1.5,
    },
    'serotonin': {
        'stress_threshold': 0.15,
        'release_threshold': 0.10,
    },
    'gaba': {
        'k_inhibit': 0.4,
        'impulse_threshold': 0.5,
    },
    'na_ach': {
        'arousal_gain': 1.2,
        'attention_gain': 1.0,
    },
}

calibrator = AdaptiveCalibrator(
    initial_params,
    temperature_initial=1.0,
    temperature_decay=0.98,
    patience=20,
)

# Calibration loop
for iteration in range(100):
    # Run trading iteration with current parameters
    performance_metrics = run_trading_iteration(current_params)
    
    # Update calibrator
    metrics = CalibrationMetrics(
        sharpe_ratio=performance_metrics['sharpe'],
        max_drawdown=performance_metrics['max_dd'],
        win_rate=performance_metrics['win_rate'],
        avg_hold_time=performance_metrics['avg_hold'],
        dopamine_stability=performance_metrics['da_variance'],
        serotonin_stress=performance_metrics['stress'],
        gaba_inhibition_rate=performance_metrics['inhibition'],
        na_ach_arousal=performance_metrics['arousal'],
        total_trades=performance_metrics['trades'],
        timestamp=time.time(),
    )
    
    current_params = calibrator.step(metrics)
    
# Get final results
best_params = calibrator.get_best_params()
report = calibrator.get_calibration_report()
```

## Cross-Neuromodulator Optimizer

### Overview

The `NeuroOptimizer` coordinates all neuromodulators to maintain homeostatic balance while optimizing performance.

### Key Features

- **Homeostatic Regulation**: Maintains DA/5-HT ratio and E/I balance
- **Multi-Objective**: Balances performance, balance, and stability
- **Momentum Updates**: Smooth parameter changes with momentum
- **Health Monitoring**: Real-time assessment of system health
- **Convergence Detection**: Automatic detection of optimization convergence

### Proportional Gradient Heuristic

The optimizer uses proportional deviations from setpoints to estimate gradients.
For any state value \(x\) with setpoint \(s\), the relative deviation is:

```
dev(x, s) = (x - s) / (s + epsilon)
```

To prevent extreme states from dominating updates, deviations are clipped:

```
dev_clip(x, s) = clip(dev(x, s), -gradient_clip, gradient_clip)
```

`gradient_clip` is configured via `OptimizationConfig.gradient_clip` (defaults to
`OptimizationConfig.numeric.gradient_dev_clip` when unset).

For dopamine/serotonin, the DA/5-HT ratio deviation directly drives proportional updates:

```
ratio_dev = dev_clip(da_5ht_ratio, da_5ht_setpoint)
dopamine_grad  = -ratio_dev
serotonin_grad =  ratio_dev
```

Other modules follow the same proportional rule:

```
gaba_grad      = -dev_clip(gaba_inhibition, gaba_setpoint)
arousal_grad   = -dev_clip(na_arousal, arousal_setpoint)
attention_grad = -dev_clip(ach_attention, attention_setpoint)
```

Negative gradients indicate the parameter should decrease, positive gradients
indicate it should increase, and larger deviations produce larger |gradients|.

### Homeostatic Deviation & Balance Score

The optimizer summarizes homeostatic drift with a scalar deviation and its
inverse balance score.

For the DA/5-HT ratio and E/I balance, first compute relative deviations:

```
da_5ht_dev = |da_5ht_ratio - da_5ht_setpoint| / da_5ht_setpoint
ei_dev     = |ei_balance - ei_setpoint| / ei_setpoint
```

Then average them to obtain the homeostatic deviation:

```
homeostatic_dev = (da_5ht_dev + ei_dev) / 2
```

Finally, map deviation to a bounded balance score:

```
balance_score = 1 / (1 + homeostatic_dev)
```

**Ranges**

- `homeostatic_dev ∈ [0, +∞)`: zero means perfect alignment with setpoints.
- `balance_score ∈ (0, 1]`: 1.0 is ideal balance, values approach 0 as deviation grows.

**Physical meaning**

`homeostatic_dev` measures how far the neuromodulator system drifts from its
target ratios (reward/serotonin and excitation/inhibition). `balance_score`
is a monotonic inverse transform that compresses large deviations while keeping
small deviations near 1, making it a stable, interpretable objective term.

### Health Status Rules

The health status derives **only** from the balance score. Let
`s = overall_balance_score`, with thresholds:

```
healthy_threshold   = 0.8
acceptable_threshold = 0.6
```

The rule is piecewise:

```
status(s) =
    healthy    if s > healthy_threshold
    acceptable if acceptable_threshold < s <= healthy_threshold
    warning    if s <= acceptable_threshold
```

### Stability Objective

Stability is computed from recent objective history (using the configured
`history_window`) as:

```
stability = 1 - std(recent_perf) / max(abs(mean(recent_perf)), epsilon)
```

Here, `epsilon` is `OptimizationConfig.numeric.stability_epsilon` (or the
`STABILITY_EPSILON` re-export).

`abs` normalizes negative/positive means by magnitude, while `epsilon` prevents division by
zero when the mean collapses toward zero. The value is clipped to `[0, 1]` to avoid spikes
when the mean is negative or near zero.

### Adaptive Learning Rate (EMA + Plateau Decay)

The optimizer smooths the composite objective with an exponential moving average (EMA)
to distinguish transient noise from true improvements:

```
ema_t = alpha * objective_t + (1 - alpha) * ema_{t-1}
```

If the current objective is **at least** the EMA, the run is considered improving:

```
improving_t = objective_t >= ema_t
```

Learning-rate recovery on improvement:

```
lr_t = min(lr_base, lr_{t-1} + 0.25 * (lr_base - lr_{t-1}))
```

If the objective is **below** the EMA, the step counts toward a plateau. Once
`plateau_steps >= plateau_patience`, the learning rate decays by `adaptive_decay`,
but never below the configured floor:

```
lr_t = max(lr_floor, lr_{t-1} * adaptive_decay)
plateau_steps = 0
```

These rules ensure that learning decays during sustained stagnation, while recovering
steadily when performance rebounds.

### API Reference

#### OptimizationConfig

```python
@dataclass
class NumericConfig:
    performance_min: float = -2.0      # Min performance for normalization
    performance_max: float = 3.0       # Max performance for normalization
    stability_epsilon: float = 1e-6    # Numerical stability constant
    gradient_dev_clip: float = 3.0     # Default deviation clip for gradients
    max_gradient_norm: float = 0.05    # Max relative gradient magnitude
    da_5ht_ratio_range: Tuple[float, float] = (1.0, 3.0)  # DA/5-HT ratio limits
    ei_balance_range: Tuple[float, float] = (1.0, 2.5)    # E/I balance limits
    aa_coherence_min: float = 0.5      # Min arousal-attention coherence


@dataclass
class OptimizationConfig:
    balance_weight: float = 0.35       # Weight for balance objective
    performance_weight: float = 0.45   # Weight for performance
    stability_weight: float = 0.20     # Weight for stability
    learning_rate: float = 0.01        # Base learning rate
    gradient_clip: float = 3.0         # Deviation clip for gradient heuristic
    momentum: float = 0.9              # Momentum factor
    max_iterations: int = 100          # Max iterations
    convergence_threshold: float = 0.001  # Convergence threshold
    enable_plasticity: bool = True     # Enable plasticity
    plasticity_window: int = 50        # Plasticity window
    regime_adaptation: bool = True     # Regime adaptation
    numeric: NumericConfig = field(default_factory=NumericConfig)
    param_bounds: Dict[str, Dict[str, Tuple[float, float]]] = {}  # Per-parameter bounds
```

| Поле | Формула / вплив | Допустимий діапазон |
| --- | --- | --- |
| `balance_weight` | Вага складової `balance_score` в об'єктиві: `objective += balance_weight * balance_score`. | **[0, 1]**, сума ваг = **1.0**. |
| `performance_weight` | Вага нормалізованої продуктивності: `objective += performance_weight * performance_norm`. | **[0, 1]**, сума ваг = **1.0**. |
| `stability_weight` | Вага стабільності: `objective += stability_weight * stability_score`. | **[0, 1]**, сума ваг = **1.0**. |
| `numeric.performance_min` | Нижня межа нормалізації продуктивності: `performance_norm = clip((performance - min)/(max-min), 0, 1)`. | `< performance_max`. |
| `numeric.performance_max` | Верхня межа нормалізації продуктивності. | `> performance_min`. |
| `learning_rate` | Базова швидкість оновлення параметрів. | **(0, 1)**. |
| `learning_rate_floor` | Мінімальний адаптивний LR під час плато: `lr = max(lr_floor, lr * adaptive_decay)`. | **(0, learning_rate]**. |
| `adaptive_decay` | Множник зменшення LR після плато. | **(0, 1)**. |
| `plateau_patience` | Кількість ітерацій без покращення до зниження LR. | Ціле **≥ 1**. |
| `ema_alpha` | Коефіцієнт EMA: `ema_t = α * obj_t + (1-α) * ema_{t-1}`. | **(0, 1]**. |
| `numeric.max_gradient_norm` | Обмеження відносної величини градієнта на крок. | **(0, 1]**. |
| `momentum` | Моментум у кумуляції швидкості: `v = momentum * v + grad`. | **[0, 1)**. |
| `max_iterations` | Ліміт ітерацій оптимізації. | Ціле **≥ 1**. |
| `convergence_threshold` | Поріг ранньої зупинки за зміною об'єктива. | **> 0** (рекомендовано). |
| `history_window` | Розмір вікна для стабільності/EMA історії. | Ціле **≥ 1**. |
| `numeric.stability_epsilon` | ε для стабільності знаменників (баланс/стабільність/відхилення). | **> 0**. |
| `gradient_clip` | Кліп девіацій в пропорційному градієнті: `clip(dev, ±gradient_clip)`. | **> 0**. |
| `numeric.gradient_dev_clip` | Дефолтне значення `gradient_clip`, якщо воно не задане. | **> 0**. |
| `dtype` | Тип чисел для буферів (numpy dtype). | Валідний `np.dtype` (напр. `float32`). |
| `use_gpu` | Спроба використати CuPy (за наявності). | `True/False`. |
| `enable_plasticity` | Увімкнення пластичності. | `True/False`. |
| `plasticity_window` | Вікно для оцінки пластичності. | Ціле **≥ 1** (рекомендовано). |
| `regime_adaptation` | Увімкнення адаптації під режими ринку. | `True/False`. |
| `numeric.da_5ht_ratio_range` | Межі клiпiнгу DA/5-HT: `clip(da_5ht_ratio, min, max)`. | `(low, high)` з **low > 0**, **high > 0**, **low < high**. |
| `numeric.ei_balance_range` | Межі клiпiнгу E/I балансу. | `(low, high)` з **low > 0**, **high > 0**, **low < high**. |
| `numeric.aa_coherence_min` | Мінімально допустима узгодженість arousal/attention. | **[0, 1]**. |
| `bounds_spec` | Структуровані BoundsSpec: визначають `min_value`, `max_value`, `behavior`. | Кожен `min_value < max_value`, `behavior ∈ {clip, raise}`. |
| `param_bounds` | Пер-параметрові межі `low/high`, застосовуються після оновлень. | Кожен `low < high`. |

#### BalanceMetrics

```python
@dataclass
class BalanceMetrics:
    dopamine_serotonin_ratio: float   # DA/5-HT ratio
    gaba_excitation_balance: float    # E/I balance
    arousal_attention_coherence: float  # Arousal-attention correlation
    overall_balance_score: float      # Composite balance (0-1)
    homeostatic_deviation: float      # Deviation from setpoint
```

#### NeuroOptimizer

```python
class NeuroOptimizer:
    def __init__(
        self,
        config: OptimizationConfig,
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        """Initialize neuro-optimizer."""
        
    def optimize(
        self,
        current_params: Dict[str, Any],
        current_state: Dict[str, float],
        performance_score: float,
    ) -> Tuple[Dict[str, Any], BalanceMetrics]:
        """Execute optimization iteration.
        
        Returns:
            Tuple of (updated_params, balance_metrics)
        """
        
    def get_optimization_report(self) -> Dict[str, Any]:
        """Generate optimization status report."""
        
    def reset(self) -> None:
        """Reset optimizer state."""
```

### Usage Example

```python
from tradepulse.core.neuro.neuro_optimizer import (
    NeuroOptimizer,
    OptimizationConfig,
)

# Configure optimizer
config = OptimizationConfig(
    balance_weight=0.35,
    performance_weight=0.45,
    stability_weight=0.20,
    learning_rate=0.01,
)

optimizer = NeuroOptimizer(config)

# Optimization loop
for iteration in range(100):
    # Get current neuromodulator state
    current_state = {
        'dopamine_level': dopamine_controller.level,
        'serotonin_level': serotonin_controller.level,
        'gaba_inhibition': gaba_gate.inhibition,
        'na_arousal': na_ach_controller.arousal,
        'ach_attention': na_ach_controller.attention,
    }
    
    # Optimize
    updated_params, balance = optimizer.optimize(
        current_params,
        current_state,
        performance_score=sharpe_ratio,
    )
    
    # Apply updated parameters
    apply_parameters(updated_params)
    current_params = updated_params
    
    # Monitor balance
    if balance.overall_balance_score < 0.6:
        print(f"Warning: Imbalanced system at iteration {iteration}")
        
# Get final report
report = optimizer.get_optimization_report()
```

## Usage Examples

### Complete Optimization Cycle

See `examples/neuro_optimization_cycle.py` for a comprehensive demonstration:

```bash
cd /home/runner/work/TradePulse/TradePulse
PYTHONPATH=. python examples/neuro_optimization_cycle.py
```

The example demonstrates:
1. System initialization with default parameters
2. 100 iterations of optimization
3. Market simulation with regime changes
4. Trading execution based on neuromodulator state
5. Real-time calibration and optimization
6. Final reporting and recommendations

### Integration with NeuroOrchestrator

```python
from tradepulse.core.neuro.neuro_orchestrator import (
    NeuroOrchestrator,
    TradingScenario,
)
from tradepulse.core.neuro.adaptive_calibrator import AdaptiveCalibrator
from tradepulse.core.neuro.neuro_optimizer import NeuroOptimizer

# Create scenario
scenario = TradingScenario(
    market="BTC/USDT",
    timeframe="1h",
    risk_profile="moderate",
)

# Generate initial orchestration
orchestrator = NeuroOrchestrator()
initial_output = orchestrator.orchestrate(scenario)
initial_params = initial_output.parameters

# Initialize optimization systems
calibrator = AdaptiveCalibrator(initial_params)
optimizer = NeuroOptimizer(OptimizationConfig())

# Run optimization loop
for iteration in range(100):
    # Execute trading with current parameters
    results = execute_trading_iteration(current_params)
    
    # Collect metrics
    metrics = collect_performance_metrics(results)
    neuro_state = collect_neuromodulator_state(results)
    
    # Calibrate
    calibrated_params = calibrator.step(metrics)
    
    # Optimize for balance
    optimized_params, balance = optimizer.optimize(
        calibrated_params,
        neuro_state,
        metrics.composite_score(),
    )
    
    current_params = optimized_params
```

## Best Practices

### 1. Calibration

#### Start Conservative
```python
calibrator = AdaptiveCalibrator(
    initial_params,
    temperature_initial=0.5,  # Lower for less exploration
    temperature_decay=0.98,
    patience=30,              # Higher for more stability
)
```

#### Monitor Progress
```python
if iteration % 20 == 0:
    report = calibrator.get_calibration_report()
    print(f"Best score: {report['best_score']:.3f}")
    print(f"Temperature: {report['current_temperature']:.3f}")
    
    for rec in report['recommendations']:
        print(f"  • {rec}")
```

#### Save State Regularly
```python
if iteration % 50 == 0:
    state = calibrator.export_state()
    with open(f'calibrator_state_{iteration}.json', 'w') as f:
        json.dump(state, f)
```

### 2. Optimization

#### Balance Weights for Your Goals

Performance-focused (aggressive):
```python
config = OptimizationConfig(
    balance_weight=0.25,
    performance_weight=0.60,
    stability_weight=0.15,
)
```

Balance-focused (conservative):
```python
config = OptimizationConfig(
    balance_weight=0.50,
    performance_weight=0.30,
    stability_weight=0.20,
)
```

#### Monitor Health
```python
report = optimizer.get_optimization_report()
health = report['health_status']

if health['status'] == 'warning':
    print(f"System warning: {health['message']}")
    for issue in health['issues']:
        print(f"  • {issue}")
    
    # Consider intervention
    if 'excessive excitation' in str(health['issues']):
        # Increase GABA inhibition
        current_params['gaba']['k_inhibit'] *= 1.2
```

### 3. Combined Usage

#### Phased Approach
```python
# Phase 1: Exploration (0-200 iterations)
calibrator.state.temperature = 1.0
optimizer.config.learning_rate = 0.02

# Phase 2: Exploitation (200-400 iterations)
if iteration == 200:
    calibrator.state.temperature = 0.3
    optimizer.config.learning_rate = 0.01

# Phase 3: Fine-tuning (400+ iterations)
if iteration == 400:
    calibrator.state.temperature = 0.1
    optimizer.config.learning_rate = 0.005
```

#### Adaptive Learning Rate
```python
# Reduce learning rate as optimization converges
convergence = optimizer._check_convergence()
if convergence['converged']:
    optimizer.config.learning_rate *= 0.5
    print("Converged - reducing learning rate")
```

## Performance Tuning

### Calibration Speed vs. Quality

Fast calibration (quick results, less optimal):
```python
calibrator = AdaptiveCalibrator(
    initial_params,
    temperature_initial=0.3,
    temperature_decay=0.90,  # Faster decay
    patience=10,             # Quick reset
    perturbation_scale=0.2,  # Larger steps
)
```

Thorough calibration (slower, more optimal):
```python
calibrator = AdaptiveCalibrator(
    initial_params,
    temperature_initial=1.5,
    temperature_decay=0.99,  # Slower decay
    patience=100,            # Patient search
    perturbation_scale=0.05, # Smaller steps
)
```

### Optimization Convergence

Early stopping:
```python
report = optimizer.get_optimization_report()
if report['convergence']['converged']:
    print("Optimization converged - stopping early")
    break
```

### Memory Management

For long-running optimizations:
```python
# Limit history length
if len(calibrator.state.metrics_history) > 1000:
    calibrator.state.metrics_history = calibrator.state.metrics_history[-500:]

if len(optimizer._performance_history) > 1000:
    optimizer._performance_history = optimizer._performance_history[-500:]
```

## Troubleshooting

### Issue: Parameters Not Changing

**Symptoms**: Parameters remain constant across iterations

**Causes**:
- Temperature too low
- Patience too high
- Insufficient performance variance

**Solutions**:
```python
# Increase temperature
calibrator.state.temperature = 0.5

# Reset exploration
calibrator._reset_exploration()

# Check if stuck in local optimum
if calibrator.state.iteration - calibrator.state.last_improvement > 50:
    calibrator._reset_exploration()
```

### Issue: Oscillating Parameters

**Symptoms**: Parameters swing wildly between iterations

**Causes**:
- Temperature too high
- Learning rate too high
- Noisy performance metrics

**Solutions**:
```python
# Reduce temperature
calibrator.state.temperature *= 0.5

# Reduce learning rate
optimizer.config.learning_rate *= 0.5

# Increase momentum for stability
optimizer.config.momentum = 0.95

# Smooth metrics with moving average
def smooth_metrics(new_metrics, history, window=5):
    history.append(new_metrics)
    if len(history) > window:
        history.pop(0)
    # Return average of recent metrics
    return average_metrics(history)
```

### Issue: Poor Balance Scores

**Symptoms**: `overall_balance_score < 0.5` consistently

**Causes**:
- Imbalanced parameter initialization
- Insufficient balance weight in optimization
- Extreme market conditions

**Solutions**:
```python
# Increase balance weight
optimizer.config.balance_weight = 0.50
optimizer.config.performance_weight = 0.35

# Check specific imbalances
balance = optimizer._balance_history[-1]
if balance.dopamine_serotonin_ratio < 1.0:
    # Boost dopamine or reduce serotonin
    current_params['dopamine']['burst_factor'] *= 1.2
    current_params['serotonin']['stress_threshold'] *= 0.9
```

### Issue: Convergence Too Slow

**Symptoms**: Optimization runs for hundreds of iterations without converging

**Causes**:
- Convergence threshold too tight
- High noise in performance metrics
- Conflicting objectives

**Solutions**:
```python
# Relax convergence threshold
optimizer.config.convergence_threshold = 0.01

# Reduce objective conflict
optimizer.config.balance_weight = 0.30
optimizer.config.performance_weight = 0.50
optimizer.config.stability_weight = 0.20

# Use longer smoothing window
# (smooth metrics before passing to optimizer)
```

## Advanced Topics

### Custom Objective Functions

Override composite score calculation:
```python
class CustomCalibrationMetrics(CalibrationMetrics):
    def composite_score(self, weights=None):
        # Custom scoring logic
        risk_penalty = self.max_drawdown * 2.0
        quality = self.sharpe_ratio * self.win_rate
        return quality - risk_penalty
```

### Regime-Aware Optimization

```python
def detect_regime(market_data):
    volatility = calculate_volatility(market_data)
    if volatility > 0.03:
        return 'high_vol'
    elif volatility < 0.01:
        return 'low_vol'
    else:
        return 'normal'

regime = detect_regime(market_data)

if regime == 'high_vol':
    # Increase inhibition in volatile markets
    optimizer.config.balance_weight = 0.50
    current_params['gaba']['k_inhibit'] = 0.6
elif regime == 'low_vol':
    # Increase exploration in calm markets
    calibrator.state.temperature = 0.8
    current_params['dopamine']['base_temperature'] = 1.2
```

### Multi-Asset Optimization

```python
# Separate optimizers per asset
optimizers = {
    'BTC/USDT': NeuroOptimizer(aggressive_config),
    'ETH/USDT': NeuroOptimizer(moderate_config),
    'BNB/USDT': NeuroOptimizer(conservative_config),
}

# Optimize each independently
for asset, optimizer in optimizers.items():
    state = get_neuromodulator_state(asset)
    perf = get_performance(asset)
    
    updated, balance = optimizer.optimize(
        params[asset], state, perf
    )
    params[asset] = updated
```

## References

- [Neurodecision Stack Documentation](neurodecision_stack.md)
- [Neuromodulator Documentation](neuromodulators/)
- [TACL Thermodynamic Control](../README.md#tacl-thermodynamic-autonomic-control-layer)
- [NeuroOrchestrator Guide](../src/tradepulse/core/neuro/README_ORCHESTRATOR.md)

## Support

For issues or questions:
- GitHub Issues: https://github.com/neuron7x/TradePulse/issues
- Documentation: See `docs/` directory
- Examples: See `examples/` directory
