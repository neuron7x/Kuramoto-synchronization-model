# AAR (Acceptor of Action Result) Specification

**Version:** 1.0.0  
**Date:** 2025-12-01  
**Module:** `nak_controller/aar/`  
**Status:** 🟢 Active

## Overview

The AAR (Acceptor of Action Result) mechanism provides a formal feedback loop that compares predicted outcomes of actions with actual outcomes, generating error signals that drive adaptation in neuro-controllers.

## Core Concepts

### Action
Any controlled system action:
- Trade orders (buy/sell)
- Mode changes (GREEN/AMBER/RED)
- Risk parameter adjustments
- Strategy suspension/activation

### Context
System state before action:
- Market state (volatility, drawdown)
- Internal modes (current risk, engagement)
- Controller configuration

### Prediction (PredictedOutcome)
Expected result of an action in measurable coordinates:
- Expected PnL direction/magnitude
- Expected fill price/slippage
- Expected execution latency
- Expected risk exposure change

### Outcome (ActualOutcome)
Observed result after action execution:
- Actual PnL
- Actual fill price/slippage
- Actual execution latency
- Actual risk exposure

### ErrorSignal
Quantified difference between prediction and outcome:
- Normalized to scale [-1, 1] or [0, 1]
- Drives controller adaptation
- Sign indicates "better/worse than expected"

## Data Structures

### ActionEvent

```python
@dataclass
class ActionEvent:
    action_id: str          # UUID for traceability
    action_type: str        # "trade", "mode_change", "risk_adjust"
    strategy_id: str        # Which strategy triggered action
    timestamp: float        # Unix timestamp
    parameters: dict        # Action-specific parameters
```

### Prediction

```python
@dataclass
class Prediction:
    action_id: str          # Links to ActionEvent
    expected_pnl: float     # Expected profit/loss
    expected_latency_ms: float
    expected_slippage: float
    confidence: float       # Model confidence [0, 1]
    timestamp: float        # When prediction was made
```

### Outcome

```python
@dataclass
class Outcome:
    action_id: str          # Links to ActionEvent
    actual_pnl: float       # Realized profit/loss
    actual_latency_ms: float
    actual_slippage: float
    success: bool           # Whether action completed
    timestamp: float        # When outcome was recorded
```

### AAREntry

```python
@dataclass
class AAREntry:
    action_id: str
    action: ActionEvent
    prediction: Prediction
    outcome: Outcome
    error_signal: ErrorSignal
    context_snapshot: dict  # Context at action time
```

### ErrorSignal

```python
@dataclass
class ErrorSignal:
    action_id: str
    absolute_error: float   # |prediction - outcome|
    relative_error: float   # (prediction - outcome) / scale
    sign: int               # +1 = better than expected, -1 = worse
    normalized_error: float # Error in [-1, 1] scale
    components: dict        # Per-dimension errors
```

## Invariants

### I1: Action-Prediction Linkage
Every prediction MUST reference a valid action_id that exists in the action log.

### I2: Outcome Follows Prediction
Outcome MUST only be recorded for actions that have predictions.

### I3: Error Computation Consistency
```
error = compute_error(prediction, outcome, context)
assert -1.0 <= error.normalized_error <= 1.0
```

### I4: Temporal Ordering
```
action.timestamp <= prediction.timestamp <= outcome.timestamp
```

### I5: Error Sign Convention
- `sign = +1`: Outcome better than predicted (lower slippage, higher PnL, etc.)
- `sign = -1`: Outcome worse than predicted
- `sign = 0`: Outcome matches prediction within tolerance

## Error Computation

### Absolute Error
```python
def absolute_error(predicted: float, actual: float) -> float:
    return abs(predicted - actual)
```

### Relative Error
```python
def relative_error(predicted: float, actual: float, scale: float) -> float:
    return (predicted - actual) / max(scale, 1e-9)
```

### Normalized Error
Maps error to [-1, 1] using tanh scaling:
```python
def normalize_error(error: float, scale: float = 1.0) -> float:
    return math.tanh(error / scale)
```

### Sign Detection
```python
def error_sign(predicted: float, actual: float, tolerance: float = 0.0) -> int:
    diff = actual - predicted
    if abs(diff) <= tolerance:
        return 0
    return 1 if diff > 0 else -1
```

## Aggregation

### Sliding Window
Maintain rolling statistics over N recent entries:
- Mean error by action type
- Standard deviation of errors
- Frequency of catastrophic errors (|error| > threshold)

### Strategy Aggregation
Group errors by strategy_id for per-strategy adaptation:
- Mean error per strategy
- Error trend (improving/worsening)
- Health score contribution

### Mode Aggregation
Group errors by system mode (GREEN/AMBER/RED):
- Track which modes produce larger prediction errors
- Adjust confidence based on mode-specific accuracy

## Integration Points

### Dopamine Controller
Positive error signals (outcomes better than predicted) → increase dopamine → reinforce current behavior.

The integration is implemented via `aar_dopamine_modulation()`:
```python
from nak_controller.aar import aar_dopamine_modulation, AARAdaptationConfig

config = AARAdaptationConfig(
    dopamine_sensitivity=0.5,
    positive_threshold=0.1,
)
dopamine_adjustment = aar_dopamine_modulation(stats, config)
# Apply: DA = DA + dopamine_adjustment
```

### Serotonin Controller
Negative error signals (outcomes worse than predicted) → trigger serotonin response → increase caution.

The integration is implemented via `aar_serotonin_modulation()`:
```python
from nak_controller.aar import aar_serotonin_modulation

serotonin_adjustment = aar_serotonin_modulation(stats, config)
# Apply: 5HT = 5HT + serotonin_adjustment
```

### Risk Management
Series of negative errors → reduce risk-per-trade → engage safe-mode thresholds.

The integration is implemented via `compute_risk_reduction()`:
```python
from nak_controller.aar import compute_risk_reduction

risk_factor = compute_risk_reduction(stats, config)
# Apply: risk_per_trade = risk_per_trade * risk_factor
```

### Comprehensive Integration
For full integration, use `compute_aar_adaptation()`:
```python
from nak_controller.aar import (
    compute_aar_adaptation,
    update_adaptation_state,
    AARAdaptationConfig,
    AARAdaptationState,
)

config = AARAdaptationConfig()
state = AARAdaptationState()

# Get stats from tracker
stats = tracker.get_strategy_stats("my_strategy")

# Compute adaptation
result = compute_aar_adaptation(stats, state, config)

if not result.is_frozen:
    # Apply modulations
    DA += result.dopamine_adjustment
    HT += result.serotonin_adjustment
    if result.should_reduce_risk:
        risk_per_trade *= result.risk_reduction_factor

# Update state for next cycle
update_adaptation_state(state, stats, result)
```

## Observability

### Metrics
The `AARAdaptationResult.metrics` dictionary provides:
- `aar_error_mean`: Mean normalized error (gauge)
- `aar_error_std`: Error standard deviation (gauge)
- `aar_positive_rate`: Rate of positive errors (gauge)
- `aar_negative_rate`: Rate of negative errors (gauge)
- `aar_catastrophic_rate`: Rate of errors above threshold (gauge)
- `aar_dopamine_adjustment`: Current dopamine adjustment (gauge)
- `aar_serotonin_adjustment`: Current serotonin adjustment (gauge)
- `aar_risk_factor`: Current risk reduction factor (gauge)
- `aar_is_frozen`: Whether adaptation is frozen (gauge, 0/1)

### Logging
Structured logs with fields:
- `action_id`
- `prediction_summary`
- `outcome_summary`
- `error_value`
- `strategy_id`
- `mode`

## Safety Guards

### G1: Maximum Adaptation Step
No single error signal can cause more than 10% change in controller parameters.

Implemented via `AARAdaptationConfig.max_adaptation_step = 0.1`:
```python
config = AARAdaptationConfig(max_adaptation_step=0.1)
```

### G2: Freeze Threshold
If error variance exceeds threshold, freeze adaptation and collect statistics only.

Implemented via `should_freeze_adaptation()`:
```python
config = AARAdaptationConfig(freeze_variance_threshold=0.5)
should_freeze, reason = should_freeze_adaptation(stats, state, config)
```

### G3: Minimum Sample Size
Aggregated statistics require minimum 10 samples before influencing controllers.

Implemented via `AARAdaptationConfig.min_samples = 10`:
```python
config = AARAdaptationConfig(min_samples=10)
```

### G4: Error Outlier Rejection
Errors beyond catastrophic threshold are tracked separately and can trigger freeze.

## Usage Example

```python
from nak_controller.aar import AARTracker, compute_error
from nak_controller.aar.types import ActionEvent, Prediction, Outcome

# Initialize tracker
tracker = AARTracker(window_size=100)

# Record action
action = ActionEvent(
    action_id="uuid-1",
    action_type="trade",
    strategy_id="momentum_1",
    timestamp=time.time(),
    parameters={"side": "buy", "size": 100}
)
tracker.record_action(action)

# Record prediction
prediction = Prediction(
    action_id="uuid-1",
    expected_pnl=50.0,
    expected_latency_ms=5.0,
    expected_slippage=0.0001,
    confidence=0.8,
    timestamp=time.time()
)
tracker.record_prediction(prediction)

# After execution, record outcome
outcome = Outcome(
    action_id="uuid-1",
    actual_pnl=45.0,
    actual_latency_ms=7.0,
    actual_slippage=0.00015,
    success=True,
    timestamp=time.time()
)
entry = tracker.record_outcome(outcome)

# Use error for adaptation
if entry.error_signal.normalized_error < -0.5:
    # Significant negative error - trigger caution
    pass
```

## References

- NaK Controller: `nak_controller/runtime/controller.py`
- Neuromodulators: `nak_controller/control/neuromods.py`
- Energetics: `nak_controller/core/energetics.py`
