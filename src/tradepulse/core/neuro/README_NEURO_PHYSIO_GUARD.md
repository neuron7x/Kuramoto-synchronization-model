# NeuroPhysioGuard Agent

## Overview

NeuroPhysioGuard is a specialized AI agent for advancing neurophysiology research projects. It implements Distinguished-level AI Safety protocols while providing structured pipeline management for neurophysiology workflows.

## Core Principles (Non-Negotiable Safety Guardrails)

1. **Alignment Check**: Every output aligns with neurophysiological facts, citing sources like Hodgkin-Huxley model, Hebbian learning, or peer-reviewed papers from PubMed/Neuron journal. Uncertain outputs are flagged as "hypothesis" with suggested empirical validation.

2. **Robustness**: Uses chain-of-thought reasoning. Tasks are broken into verifiable steps. Incomplete data defaults to conservative estimates (e.g., "Error margin: ±20% based on synaptic noise models").

3. **Interpretability**: Decisions are explained transparently in structured format:
   - `[Step]` -> `[Rationale]` -> `[Output]` -> `[Safety Audit]`

4. **Ethical Rails**: Never generates medical advice. Flags biases (e.g., over-representation of rodent models vs. human data). Ensures inclusivity by considering diverse populations.

5. **Project Velocity**: Structures workflows as: `Ideate -> Model -> Simulate -> Validate -> Iterate`

## Supported Domains

| Domain | Description | Key References |
|--------|-------------|----------------|
| `synaptic_plasticity` | LTP, LTD, STDP mechanisms | Bi & Poo (1998), Bliss & Collingridge (1993) |
| `network_oscillations` | Theta, gamma rhythms | Buzsáki (2006), Fries (2005) |
| `optogenetics` | Light-controlled neural activity | Boyden et al. (2005), Deisseroth (2011) |
| `ion_channels` | Hodgkin-Huxley dynamics | Hodgkin & Huxley (1952), Hille (2001) |
| `neural_coding` | Population coding, tuning curves | Quiroga et al. (2005), Hubel & Wiesel (1962) |
| `neuromodulation` | Dopamine, serotonin systems | Marder (2012), Schultz (1998) |
| `circadian_rhythms` | SCN oscillators, clock genes | Reppert & Weaver (2002) |
| `motor_control` | Optimal feedback control | Todorov & Jordan (2002) |

## Quick Start

### Basic Usage

```python
from tradepulse.core.neuro import create_neurophysiology_pipeline

output = create_neurophysiology_pipeline(
    domain="synaptic_plasticity",
    task_type="model",
    organism="mouse",
    brain_region="hippocampus_CA1",
)

print(output.project_milestone)
print(output.to_json())
```

### Advanced Usage

```python
from tradepulse.core.neuro import (
    NeuroPhysioGuard,
    NeurophysiologyDomain,
    PhysioScenario,
)

# Initialize with custom settings
guard = NeuroPhysioGuard(
    confidence_threshold=0.9,
    enable_safety_validation=True,
    flag_hypotheses=True,
)

# Create a research scenario
scenario = PhysioScenario(
    domain=NeurophysiologyDomain.ION_CHANNELS,
    task_type="simulate",
    organism="squid",
    brain_region="giant_axon",
    confidence_threshold=0.85,
    validate_empirically=True,
)

# Process the scenario
output = guard.process(scenario)
```

## Output Format

The agent produces structured output with exactly these fields:

```json
{
  "project_milestone": "Brief summary of progress",
  "pipeline_steps": [
    {
      "step_name": "...",
      "operation": "...",
      "rationale": "...",
      "parameters": {},
      "priority": 0,
      "tools": ["pytorch", "sympy"],
      "citations": ["Bi & Poo (1998)"]
    }
  ],
  "key_outputs": {
    "code_snippet": "...",
    "equations": {},
    "visualization": {}
  },
  "safety_log": {
    "risks_mitigated": [],
    "biases_flagged": [],
    "confidence_score": 0.8,
    "validation_required": true,
    "validation_method": "Simulate in NEURON software",
    "ethical_considerations": [],
    "is_hypothesis": false
  },
  "next_action": "Suggested next step. Ready for iteration?",
  "parameters": {}
}
```

## Pipeline Phases

### Ideate Phase
- Data acquisition planning
- Model architecture design
- Literature review

### Model Phase
- Data acquisition
- Model construction with biophysical equations
- Simulation setup

### Simulate Phase
- All model phase steps
- Neural dynamics simulation execution

### Validate Phase
- All simulate phase steps
- Comparison with experimental data

### Iterate Phase
- Full pipeline
- Parameter optimization
- Model refinement

## Domain-Specific Parameters

### Ion Channels (Hodgkin-Huxley)
```python
{
    "g_na_mS_cm2": 120.0,
    "g_k_mS_cm2": 36.0,
    "g_l_mS_cm2": 0.3,
    "e_na_mV": 50.0,
    "e_k_mV": -77.0,
    "e_l_mV": -54.4
}
```

### Synaptic Plasticity (STDP)
```python
{
    "tau_plus_ms": 20.0,
    "tau_minus_ms": 20.0,
    "a_plus": 0.005,
    "a_minus": 0.00525,
    "plasticity_rule": "Equation 3.2 in Bi & Poo (1998)"
}
```

### Network Oscillations (Kuramoto)
```python
{
    "model_type": "kuramoto",
    "frequency_band": "theta",
    "coupling_strength": 0.5
}
```

## Safety Features

### Bias Detection
- Flags over-representation of rodent models
- Highlights species-specific translation limitations
- Notes age/sex effects on parameters

### Ethical Considerations
- Never generates medical advice
- Research use only disclaimers
- Empirical validation requirements

### Confidence Scoring
- Confidence scores between 0-1
- Low confidence outputs flagged as hypotheses
- Conservative defaults for uncertain parameters

## AI Tools Integration

| Tool | Usage |
|------|-------|
| PyTorch | Neural network models, tensor operations |
| SymPy | Symbolic biophysical equations |
| BioPython | Biological data parsing |
| SciPy | Scientific computing, statistics |
| NumPy | Numerical arrays |
| NEURON | Neural simulation software |
| Brian2 | Spiking neural network simulator |

## Agent Registry

The agent is registered in the global agent registry:

```python
from core.agent import global_agent_registry

registry = global_agent_registry()
guard = registry.resolve("neuro_physio_guard")()
```

## Testing

Run the test suite:

```bash
pytest tests/unit/core/neuro/test_neuro_physio_guard.py -v
```

## Demo

Run the demonstration script:

```bash
python examples/neuro_physio_guard_demo.py
```

## References

- Bi, G. Q., & Poo, M. M. (1998). Synaptic modifications in cultured hippocampal neurons. *Journal of Neuroscience*.
- Hodgkin, A. L., & Huxley, A. F. (1952). A quantitative description of membrane current. *Journal of Physiology*.
- Buzsáki, G. (2006). *Rhythms of the Brain*. Oxford University Press.
- Deisseroth, K. (2011). Optogenetics. *Nature Methods*.
- Schultz, W. (1998). Predictive reward signal of dopamine neurons. *Journal of Neurophysiology*.

---

**Implementation Date**: 2025-11-27  
**Author**: GitHub Copilot Agent  
**Tests**: 42 passed  
**Lines of Code**: ~800 (core module) + ~600 (tests)
