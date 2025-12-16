# Memory Invariants Specification

This document specifies the formal invariants, validation behavior, and recovery
policies for TradePulse memory systems. These guarantees ensure memory state
correctness and resilience against corruption.

## Overview

TradePulse implements memory hardening for the following components:

1. **StrategyMemory** (`core/agent/memory.py`)  
   Episodic memory for trading strategies with time-based decay

2. **FractalPELMGPU** (`cortex_service/app/memory/experimental/fractal_pelm_gpu.py`)  
   Phase-entangled lattice memory for GPU-accelerated vector retrieval

Both systems now support:
- Formal invariant validation
- Deterministic serialization with checksum
- Strict vs recovery modes for corruption handling
- NaN/Inf rejection on all numeric values

## Invariants

### StrategyMemory Invariants

| # | Invariant | Check | Error on Violation |
|---|-----------|-------|-------------------|
| SM1 | `decay_lambda ≥ 0` | Finite, non-negative | `InvariantError` |
| SM2 | `max_records > 0` | Positive integer | `InvariantError` |
| SM3 | `len(records) ≤ max_records` | Capacity constraint | `InvariantError` |
| SM4 | All scores are finite | No NaN/Inf | `InvariantError` |
| SM5 | All timestamps `≥ 0` | Non-negative | `InvariantError` |
| SM6 | All signature fields finite | No NaN/Inf in R, delta_H, etc. | `InvariantError` |
| SM7 | Decay monotonicity | `decayed_score ≤ original_score` | `InvariantError` |
| SM8 | Signature keys unique | No duplicate keys | Silently update |

### FractalPELMGPU Invariants

| # | Invariant | Check | Error on Violation |
|---|-----------|-------|-------------------|
| PM1 | `dimension > 0` | Positive integer | `ValueError` |
| PM2 | `capacity > 0` | Positive integer | `ValueError` |
| PM3 | `fractal_weight ∈ [0, 1]` | Bounded float | `ValueError` |
| PM4 | `len(entries) ≤ capacity` | Capacity constraint | `InvariantError` |
| PM5 | All vectors finite | No NaN/Inf | `InvariantError` |
| PM6 | Vector dimensions match | `len(v) == dimension` | `InvariantError` |
| PM7 | All phases finite | No NaN/Inf | `InvariantError` |
| PM8 | Metadata is dict or None | Type constraint | `InvariantError` |
| PM9 | Scores in [0, 1] | Bounded retrieval scores | Clamped |

## Serialization Format

### State Version

Current format version: `1.0.0`

States include a `state_version` field for forward compatibility.

### Checksum Algorithm

- Algorithm: SHA-256
- Coverage: All fields except `_checksum` and `_computed_at`
- Key ordering: Deterministic (sorted)
- Numpy arrays: Serialized with shape, dtype, and data

### Example State (StrategyMemory)

```json
{
  "state_version": "1.0.0",
  "decay_lambda": 1e-6,
  "max_records": 256,
  "records": [
    {
      "name": "momentum",
      "signature": {
        "R": 0.95,
        "delta_H": 0.05,
        "kappa_mean": 0.3,
        "entropy": 2.1,
        "instability": 0.1
      },
      "score": 0.85,
      "ts": 1702734421.123
    }
  ],
  "_checksum": "a1b2c3d4..."
}
```

## Strict vs Recovery Modes

### Strict Mode (default)

```python
memory = StrategyMemory.from_dict(state, strict=True)
pelm = FractalPELMGPU.from_dict(state, strict=True)
```

Behavior:
- **Checksum mismatch**: Raises `CorruptedStateError`
- **Invariant violation**: Raises `InvariantError`
- **Corrupted record**: Raises `InvariantError`

Use strict mode in:
- Production deployments
- Critical state restoration
- When data integrity is paramount

### Recovery Mode

```python
memory = StrategyMemory.from_dict(state, strict=False)
pelm = FractalPELMGPU.from_dict(state, strict=False)
```

Behavior:
- **Checksum mismatch**: Logs warning, continues
- **Invariant violation**: Quarantines corrupted entries
- **Corrupted record**: Skips with warning

Recovery mode:
- Emits `RuntimeWarning` for quarantined data
- Logs details to the `core.utils.memory_validation` logger
- Sets `_recovered=True` and `_quarantined_count=N` in state
- Returns a valid, degraded state

Use recovery mode in:
- Development/debugging
- Data migration scenarios
- When partial data is acceptable

## Error Types

### InvariantError

Raised when a state invariant is violated:

```python
from core.utils.memory_validation import InvariantError

try:
    memory.add("strategy", sig, score=float("nan"))
except InvariantError as e:
    print(f"Invariant violated: {e}")
```

### CorruptedStateError

Raised when checksum verification fails in strict mode:

```python
from core.utils.memory_validation import CorruptedStateError

try:
    memory = StrategyMemory.from_dict(corrupted_state, strict=True)
except CorruptedStateError as e:
    print(f"State corruption detected: {e}")
```

## Validation API

### Manual Validation

```python
# Validate current state
memory.validate(strict=True)  # Raises on invalid
pelm.validate(strict=True)    # Raises on invalid

# Low-level validation
from core.utils.memory_validation import (
    validate_strategy_memory_state,
    validate_pelm_state,
)

result = validate_strategy_memory_state(state_dict, strict=False)
if not result.is_valid:
    print(f"Violations: {result.violations}")
    print(f"Quarantined indices: {result.quarantined_indices}")
```

### Finite Value Assertions

```python
from core.utils.memory_validation import (
    assert_finite_float,
    assert_finite_array,
)

# Single values
assert_finite_float(value, "score", min_value=0.0, max_value=1.0)

# Arrays
assert_finite_array(vectors, "embeddings", allow_empty=False)
```

## How to Run Tests

```bash
# Memory validation unit tests
python -m pytest tests/unit/core/utils/test_memory_validation.py -v

# StrategyMemory tests
python -m pytest tests/unit/core/agent/test_strategy_memory.py -v

# FractalPELMGPU tests
python -m pytest cortex_service/tests/test_fractal_pelm_gpu.py -v

# All memory-related tests
python -m pytest tests/unit/core/utils/test_memory_validation.py \
                 tests/unit/core/agent/test_strategy_memory.py \
                 cortex_service/tests/test_fractal_pelm_gpu.py -v
```

## Corruption Demo

To demonstrate corruption detection:

```python
from core.agent.memory import StrategyMemory
from core.utils.memory_validation import CorruptedStateError
import json

# Create and serialize memory
memory = StrategyMemory()
memory.add("test", (0.9, 0.05, 0.3, 2.1, 0.1), score=0.85)
state = memory.to_dict()

# Corrupt the state
json_str = json.dumps(state)
json_bytes = bytearray(json_str.encode())
json_bytes[len(json_bytes)//2] ^= 0xFF  # Flip a byte

try:
    corrupted = json.loads(json_bytes.decode(errors='replace'))
    StrategyMemory.from_dict(corrupted, strict=True)
except (CorruptedStateError, json.JSONDecodeError, KeyError) as e:
    print(f"Corruption detected: {type(e).__name__}: {e}")
```

## Changelog

### 2025-12-16: Memory Correctness Hardening

- Added `InvariantError` and `CorruptedStateError` exceptions
- Added invariant validation for StrategyMemory and FractalPELMGPU
- Added deterministic serialization with SHA-256 checksum
- Added strict/recovery modes for corruption handling
- Added NaN/Inf rejection on all numeric inputs
- Added decay monotonicity invariant validation
- Backward compatible: existing code works without changes
