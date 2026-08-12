# Async resilience layer for distributed execution

## Problem
Deterministic monotonic potential decrease can break under asynchronous jitter, delayed delivery, partial node dropout, and re-entry.

## Adaptive layer
`run_reset_wave_async_resilient(...)` adds:
- message jitter modeling (`message_jitter`),
- dropout and re-entry (`dropout_rate`, `reentry_gain`),
- monotonic guard with fallback step shrink,
- fail-closed lock if monotonic repair fails.

## Contract
- `dropout_rate in [0,1)`
- `reentry_gain > 0`
- deterministic replay under fixed `seed`

## Expected behavior
1. In moderate async noise, final potential remains <= initial potential.
2. In adversarial async conditions, system either stabilizes or locks safely.
