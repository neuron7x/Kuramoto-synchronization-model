# Neuro-Orchestrator Agent

## Overview

The Neuro-Orchestrator Agent is a biologically-inspired control architecture orchestrator that maps trading scenarios to module-level instructions for the GeoSync system. It implements a neuroscience-based approach to algorithmic trading strategy configuration and execution.

## Module API Reference

This section documents the public interfaces of all neuro submodules.

### Core Package (`geosync.core.neuro`)

```python
from geosync.core.neuro import (
    # Orchestrator
    NeuroOrchestrator,
    OrchestrationOutput,
    TradingScenario,
    ModuleInstruction,
    RiskContour,
    LearningLoop,
    create_orchestration_from_scenario,
    # Submodules
    dopamine,
    serotonin,
    gaba,
    na_ach,
    nak,
    desensitization,
)
```

### Dopamine Module (`geosync.core.neuro.dopamine`)

Appetitive reward signaling and action invigoration.

```python
from geosync.core.neuro.dopamine import (
    DopamineController,    # TD(0) RPE computation, temperature modulation
    ActionGate,            # Go/Hold/No-Go decision fusion
    GateEvaluation,        # Decision gate output dataclass
    DDMThresholds,         # DDM threshold container
    DDMAdjustment,         # DDM adjustment container
    StepResult,            # Step helper result
    # Invariants
    assert_no_nan_inf,     # NaN/Inf checker
    check_monotonic_thresholds,  # Threshold ordering invariant
    clamp,                 # Value clamping utility
)
```

### Serotonin Module (`geosync.core.neuro.serotonin`)

Chronic stress and hold-state management.

```python
from geosync.core.neuro.serotonin import (
    SerotoninController,   # Hysteretic hold logic with desensitization
    SerotoninConfig,       # Configuration dataclass
    SerotoninMonitor,      # SRE observability monitor
    Alert,                 # Alert definition
    AlertSeverity,         # Alert severity levels
    SLI, SLO,             # Service level indicators/objectives
)
```

### GABA Module (`geosync.core.neuro.gaba`)

Inhibitory impulse control.

```python
from geosync.core.neuro.gaba import (
    GABAInhibitionGate,    # STDP-modulated impulse dampening
    GABAConfig,            # Configuration dataclass
)
```

### NA/ACh Module (`geosync.core.neuro.na_ach`)

Arousal and attention modulation.

```python
from geosync.core.neuro.na_ach import (
    NAACHNeuromodulator,   # Risk and temperature scaling
    NAACHConfig,           # Configuration dataclass
)
```

### NaK Module (`geosync.core.neuro.nak`)

Homeostatic control with bio-inspired gating.

```python
from geosync.core.neuro.nak import (
    NaKController,         # Homeostatic trading controller (alias)
    NaKControllerV4_2,     # Homeostatic controller v4.2
    NaKConfig,             # Configuration dataclass
    NaKAdapter,            # Integration adapter
    DesensitizationModule, # Lambda/scale adaptation
)
```

### Desensitization Module (`geosync.core.neuro.desensitization`)

Adaptive sensitivity management.

```python
from geosync.core.neuro.desensitization import (
    DesensitizationManager,  # Coordinated reward/sensory/threat modulation
    DesensitizationConfig,   # Configuration bundle
    DesensitizationGate,     # Policy gate wrapper
    RewardDesensitizer,      # Reward shaping
    SensoryHabituation,      # Feature habituation
    ThreatGate,              # Drawdown-based gating
)
```

## Architecture

The orchestrator coordinates four key components:

1. **Basal Ganglia-style Action Selection**: Maps to the action_selector module with neuromodulator coordination
2. **Dopamine Loop Learning**: TD-based reinforcement learning for reward prediction
3. **Threat/Risk Contours**: Risk management with VaR/ES and Kelly fraction sizing
4. **TACL (Thermodynamic Autonomic Control Layer)**: Free-energy monitoring with monotonic descent constraint

## Neuroscience Mapping

| Biological Component | System Module | Function |
|---------------------|---------------|----------|
| Basal Ganglia | `action_selector` | Action selection via Go/No-Go pathways |
| Dopamine Neurons | `learning_loop` | Reward prediction error (RPE) signals |
| Prefrontal Cortex | `risk_assessment` | Risk evaluation and threat detection |
| Amygdala | `risk_contour` | Threat threshold and stress response |
| Homeostatic Control | `tacl_monitor` | System energy regulation |

## Usage

### Basic Example

```python
from geosync.core.neuro import create_orchestration_from_scenario

# Create orchestration for a trading scenario
output = create_orchestration_from_scenario(
    market="BTC/USDT",
    timeframe="1h",
    risk_profile="moderate",
    capital=100000.0,
)

# Get JSON output
json_output = output.to_json()
print(json_output)
```

### Advanced Example

```python
from geosync.core.neuro import NeuroOrchestrator, TradingScenario

# Define scenario
scenario = TradingScenario(
    market="ETH/USDT",
    timeframe="5m",
    risk_profile="conservative",
    capital=50000.0,
    max_position_size=0.15,
)

# Initialize orchestrator with custom TACL threshold
orchestrator = NeuroOrchestrator(
    free_energy_threshold=1.2,
    enable_tacl_validation=True,
)

# Generate orchestration
output = orchestrator.orchestrate(scenario)

# Access components
for module in output.module_sequence:
    print(f"{module.module_name}: {module.operation}")

print(f"Learning Rate: {output.parameters['learning_rate']}")
print(f"Risk Mode: {output.risk_contour.mode}")
print(f"Discount Gamma: {output.learning_loop.discount_gamma}")
```

### Custom Parameters

```python
custom_params = {
    "learning_rate": 0.025,
    "temperature": 1.5,
    "dopamine": {
        "burst_factor": 2.0,
        "invigoration_threshold": 0.7,
    },
    "tacl": {
        "epsilon_tolerance": 0.005,
    },
}

output = orchestrator.orchestrate(scenario, custom_parameters=custom_params)
```

## JSON Output Format

The orchestrator returns JSON with the following structure:

```json
{
  "module_sequence": [
    {
      "module_name": "data_ingestion",
      "operation": "ingest",
      "parameters": {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "buffer_size": 1000
      },
      "priority": 0
    },
    {
      "module_name": "action_selector",
      "operation": "select",
      "parameters": {
        "algorithm": "basal_ganglia",
        "temperature": 1.0,
        "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"]
      },
      "priority": 3
    }
  ],
  "parameters": {
    "capital": 100000.0,
    "learning_rate": 0.01,
    "discount_gamma": 0.99,
    "exposure_limit": 0.5,
    "free_energy_threshold": 1.4,
    "dopamine": {
      "burst_factor": 1.5,
      "decay_rate": 0.95,
      "invigoration_threshold": 0.6
    },
    "tacl": {
      "monotonic_descent": true,
      "epsilon_tolerance": 0.01,
      "crisis_detection": true,
      "protocol_options": ["CRDT", "RDMA", "gRPC", "shared_memory"]
    }
  },
  "risk_contour": {
    "mode": "normal",
    "threat_threshold": 0.5,
    "exposure_limit": 0.5,
    "drawdown_limit": 0.10,
    "var_confidence": 0.975,
    "kelly_fraction_cap": 0.75
  },
  "learning_loop": {
    "algorithm": "TD(0)",
    "discount_gamma": 0.99,
    "learning_rate": 0.01,
    "prediction_window": 1,
    "error_metric": "absolute",
    "update_rule": "delta = reward + gamma * V_next - V_current; V_current += learning_rate * delta"
  }
}
```

## Module Sequence

The orchestrator generates modules in the following biological execution order:

1. **data_ingestion** (priority 0): Sensory input - market data acquisition
2. **feature_extraction** (priority 1): Preprocessing - indicator computation
3. **risk_assessment** (priority 2): Threat detection - VaR/ES calculation
4. **action_selector** (priority 3): Motor output - basal ganglia decision
5. **learning_loop** (priority 4): Synaptic plasticity - dopamine-based learning
6. **tacl_monitor** (priority 5): Homeostasis - free-energy validation

## Risk Profiles

### Conservative
- Lower exposure limits (30%)
- Stricter drawdown limits (5%)
- Lower learning rate (0.005)
- Lower temperature (0.5) = less exploration
- Kelly cap at 50%

### Moderate
- Balanced exposure (50%)
- Moderate drawdown tolerance (10%)
- Standard learning rate (0.01)
- Standard temperature (1.0)
- Kelly cap at 75%

### Aggressive
- Higher exposure (80%)
- Higher drawdown tolerance (20%)
- Higher learning rate (0.02)
- Higher temperature (1.5) = more exploration
- Kelly cap at 100%

## TACL Constraints

The orchestrator enforces TACL's **Monotonic Free-Energy Descent** constraint:

- No configuration can increase system free energy (F) without human override
- Free energy threshold must be ≤ 2.0 (enforced)
- Temperature must be ≤ 2.5 (enforced)
- Monotonic descent cannot be disabled (enforced)

### Validation Examples

```python
# Valid configuration
output = orchestrator.orchestrate(scenario)  # ✓ Passes validation

# Invalid: high free-energy threshold
try:
    invalid = {"free_energy_threshold": 2.5}
    output = orchestrator.orchestrate(scenario, custom_parameters=invalid)
except ValueError as e:
    print(f"Rejected: {e}")  # ✗ Exceeds safe limit

# Invalid: disabled monotonic descent
try:
    invalid = {"tacl": {"monotonic_descent": False}}
    output = orchestrator.orchestrate(scenario, custom_parameters=invalid)
except ValueError as e:
    print(f"Rejected: {e}")  # ✗ Must be enabled
```

## Neuromodulator Configuration

### Dopamine (Reward & Learning)
- `burst_factor`: Phasic response magnitude (1.5)
- `decay_rate`: Tonic level decay (0.95)
- `invigoration_threshold`: Go pathway activation (0.6)

### Serotonin (Stress & Inhibition)
- `stress_threshold`: Stress detection level (0.15)
- `hold_temperature_floor`: Minimum exploration when stressed (0.3)

### GABA (Impulse Control)
- `inhibition_decay`: Inhibitory signal decay (0.90)
- `impulse_threshold`: Impulsive action threshold (0.5)

### Noradrenaline/Acetylcholine (Arousal & Attention)
- `arousal_sensitivity`: Volatility response (1.2)
- `attention_gain`: Novelty attention boost (1.0)

## Learning Loop Specification

The dopamine-based learning loop implements TD(0) temporal difference learning:

```
Algorithm: TD(0)
Update Rule: δ = r + γ·V' - V
             V ← V + α·δ

Where:
  δ = Reward Prediction Error (RPE)
  r = Immediate reward
  γ = Discount factor (0.99)
  V = Current value estimate
  V' = Next state value estimate
  α = Learning rate (0.01)
```

### Biological Mapping
- **Phasic Dopamine** = RPE when δ > 0 (unexpected reward)
- **Dopamine Dip** = RPE when δ < 0 (reward omission)
- **Value Update** = Synaptic weight changes in striatum

## Integration with GeoSync

The orchestration output integrates with existing GeoSync components:

```python
from geosync.policy import BasalGangliaDecisionStack
from geosync.core.neuro.dopamine import DopamineController
from geosync.risk import RiskConfig

# Get orchestration
output = create_orchestration_from_scenario(
    market="BTC/USDT",
    timeframe="1h",
    risk_profile="moderate",
)

# Configure components
risk_config = RiskConfig(
    es_limit=output.risk_contour.drawdown_limit,
    var_alpha=output.risk_contour.var_confidence,
    f_max=output.risk_contour.kelly_fraction_cap,
)

# Initialize basal ganglia stack with orchestrated parameters
stack = BasalGangliaDecisionStack(
    dopamine_config="configs/dopamine.yaml",  # Updated with output.parameters["dopamine"]
    serotonin_config="configs/serotonin.yaml",
    gaba_config="configs/gaba.yaml",
    na_ach_config="configs/na_ach.yaml",
)
```

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/core/neuro/test_neuro_orchestrator.py -v
```

## References

- **Basal Ganglia**: Gurney, K., Prescott, T. J., & Redgrave, P. (2001). A computational model of action selection in the basal ganglia.
- **Dopamine & TD Learning**: Schultz, W., Dayan, P., & Montague, P. R. (1997). A neural substrate of prediction and reward.
- **TACL**: GeoSync TACL Documentation - Thermodynamic Autonomic Control Layer
- **Free Energy Principle**: Friston, K. (2010). The free-energy principle: a unified brain theory?

## License

See LICENSE file in the repository root.
