# Numerical Contracts for MLSDM

This document specifies the numerical stability contracts for the Multi-Level Stochastic Decision Model (MLSDM) subsystem.

## Overview

MLSDM enforces strict numerical contracts across all vector/memory/metrics paths to ensure:

1. **Finite Outputs**: No NaN or Inf values propagate through the system
2. **Bounded Metrics**: All coherence/safety metrics return values in [0, 1]
3. **Explicit Failure Modes**: Invalid inputs either raise clear exceptions or are sanitized with logging

## EPS Policy

A single universal epsilon constant is used throughout MLSDM:

```python
EPS = 1e-9
```

### Usage

- **Division safety**: `result = numerator / (denominator + EPS)`
- **Normalization**: `unit_vec = vec / (norm(vec) + EPS)`
- **Zero detection**: `is_zero = norm(vec) < EPS`

### Rationale

- Well above float64 machine epsilon (2.22e-16)
- Small enough to not affect meaningful computations
- Consistent across all MLSDM modules

## strict_mode Policy

All MLSDM components support a `strict_mode` parameter:

| Mode | Behavior on NaN/Inf | Use Case |
|------|---------------------|----------|
| `strict_mode=True` (default) | Raise `NumericalContractError` | Development, testing, safety-critical paths |
| `strict_mode=False` | Sanitize to zeros, log warning | Production fallback, graceful degradation |

### Example

```python
from src.tradepulse.sdk.mlsdm.memory import MultiLevelSynapticMemory
from src.tradepulse.sdk.mlsdm.utils import cosine_coherence

# Strict mode (default): raises on invalid input
memory = MultiLevelSynapticMemory(dim=128, strict_mode=True)
# memory.update(invalid_vector)  # Raises NumericalContractError

# Non-strict mode: sanitizes and continues
memory = MultiLevelSynapticMemory(dim=128, strict_mode=False)
memory.update(invalid_vector)  # Sanitizes NaN/Inf -> 0, logs warning
```

## Zero-Vector Behavior

| Component | Zero Vector Input | Output |
|-----------|------------------|--------|
| `safe_unit_normalize()` | `on_zero="return_zeros"` | Returns zero vector |
| `safe_unit_normalize()` | `on_zero="raise"` | Raises `NumericalContractError` |
| `cosine_coherence()` | Either vector is zero | Returns 0.5 (neutral) |
| `temporal_coherence()` | Empty window | Returns 1.0 (max coherence) |
| `memory_coherence()` | All zeros | Returns 0.5 (neutral) |
| `safety_score()` | Zero deviation | Returns 1.0 (max safety) |

## Lambda Hierarchy (MultiLevelSynapticMemory)

The decay rates must satisfy:

```
λ3 ≤ λ2 ≤ λ1
```

Where:
- `λ1`: Short-term memory decay (fastest decay, largest value close to 1)
- `λ2`: Medium-term memory decay
- `λ3`: Long-term memory decay (slowest decay, smallest value)

This ensures correct memory consolidation behavior where long-term memory changes more slowly than short-term memory.

### Validation

```python
# Valid: λ3=0.90 ≤ λ2=0.95 ≤ λ1=0.99
memory = MultiLevelSynapticMemory(
    dim=128,
    lambda_l1=0.99,
    lambda_l2=0.95,
    lambda_l3=0.90,
)

# Invalid: λ3=0.98 > λ1=0.95
# Raises LambdaHierarchyError
memory = MultiLevelSynapticMemory(
    dim=128,
    lambda_l1=0.95,
    lambda_l2=0.90,
    lambda_l3=0.98,  # INVALID
)
```

## Input Validation Functions

### `validate_finite_array(x, name, strict_mode=True)`

Validates that array contains only finite values.

```python
from src.tradepulse.sdk.mlsdm.utils import validate_finite_array

# Passes validation
arr = validate_finite_array(np.array([1.0, 2.0]), "embedding")

# Raises in strict mode
validate_finite_array(np.array([1.0, np.nan]), "embedding")
# NumericalContractError: Numerical contract violation for 'embedding': contains NaN values

# Sanitizes in non-strict mode
arr = validate_finite_array(np.array([1.0, np.nan]), "embedding", strict_mode=False)
# arr = [1.0, 0.0], logs warning
```

### `safe_unit_normalize(vec, eps=EPS, on_zero="return_zeros")`

Safely normalizes a vector to unit length.

```python
from src.tradepulse.sdk.mlsdm.utils import safe_unit_normalize

# Normal case
unit = safe_unit_normalize(np.array([3.0, 4.0]))
# unit = [0.6, 0.8]

# Zero vector with return_zeros policy
unit = safe_unit_normalize(np.zeros(3))
# unit = [0.0, 0.0, 0.0]

# Zero vector with raise policy
safe_unit_normalize(np.zeros(3), on_zero="raise")
# NumericalContractError: cannot normalize: norm (0.00e+00) < eps (1.00e-09)
```

### `ensure_dtype(vec, dtype=np.float64)`

Ensures array has the specified dtype with overflow checking.

```python
from src.tradepulse.sdk.mlsdm.utils import ensure_dtype

# Convert to float64
arr = ensure_dtype(np.array([1, 2, 3]), np.float64)
# arr.dtype = float64
```

## Running Tests Locally

### Unit Tests

```bash
# Run all MLSDM numerical contract tests
pytest tests/unit/sdk/mlsdm/ -v

# Run specific test file
pytest tests/unit/sdk/mlsdm/test_multilevel_synaptic_memory_numeric_contract.py -v
pytest tests/unit/sdk/mlsdm/test_coherence_metrics_numeric_contract.py -v
```

### Property Tests (Hypothesis)

```bash
# Run property tests with Hypothesis
pytest tests/property/test_mlsdm_metrics_finite_properties.py -v

# Show Hypothesis statistics
pytest tests/property/test_mlsdm_metrics_finite_properties.py --hypothesis-show-statistics
```

### All Tests

```bash
# Run all tests with coverage
pytest tests/unit/sdk/mlsdm/ tests/property/test_mlsdm_metrics_finite_properties.py -v --cov=src/tradepulse/sdk/mlsdm
```

## API Reference

### Input Validator (`src/tradepulse/sdk/mlsdm/utils/input_validator.py`)

| Function | Purpose |
|----------|---------|
| `validate_finite_array()` | Validate array is finite |
| `safe_unit_normalize()` | Safe unit normalization |
| `ensure_dtype()` | Dtype conversion with overflow check |
| `sanitize_array()` | Replace NaN/Inf with zeros |

### Memory (`src/tradepulse/sdk/mlsdm/memory/multi_level_memory.py`)

| Class | Purpose |
|-------|---------|
| `MultiLevelSynapticMemory` | Three-level synaptic memory with λ hierarchy |
| `MemoryState` | Immutable snapshot of memory state |
| `LambdaHierarchyError` | Raised on λ hierarchy violation |

### Metrics (`src/tradepulse/sdk/mlsdm/utils/coherence_safety_metrics.py`)

| Function | Purpose | Output Range |
|----------|---------|--------------|
| `cosine_coherence()` | Cosine similarity scaled to [0,1] | [0, 1] |
| `temporal_coherence()` | Coherence across time window | [0, 1] |
| `memory_coherence()` | Coherence between memory levels | [0, 1] |
| `safety_score()` | Safety based on deviation | [0, 1] |
| `compute_all_metrics()` | Compute all metrics at once | CoherenceMetrics |

## Rollback

If issues arise with numerical contracts:

1. Set `strict_mode=False` to enable sanitization instead of exceptions
2. Review warning logs for sanitized values
3. If needed, revert to pre-contract versions of affected files

Files affected by numerical contracts:
- `src/tradepulse/sdk/mlsdm/utils/input_validator.py`
- `src/tradepulse/sdk/mlsdm/memory/multi_level_memory.py`
- `src/tradepulse/sdk/mlsdm/utils/coherence_safety_metrics.py`
