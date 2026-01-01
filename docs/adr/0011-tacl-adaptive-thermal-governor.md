# ADR-0011: TACL Adaptive Thermal Governor for System Load

## Status
Accepted

**Date:** 2026-01-02

**Decision makers:** TACL Lead, Runtime Lead, Principal Architect

## Context

The system lacks an explicit mechanism to modulate throughput under stress. We need a control layer that reacts to system heat (latency, queue depth, error rates) and adjusts throughput across runtime and execution layers.

## Decision

Implement an adaptive thermal governor in `tacl/` that ingests telemetry from `observability/` and publishes throttling signals to `runtime/` and `execution/`. The governor will maintain stable operating zones using hysteresis and safety thresholds.

## Consequences

### Positive
- Prevents cascading failures under load.
- Provides clear, tunable control signals for load shedding.

### Negative
- Requires careful tuning to avoid over-throttling.
- Adds complexity to runtime/execution control loops.

### Neutral
- Introduces additional telemetry dependencies between modules.

## Alternatives Considered

### Alternative 1: Manual throttling via operator runbooks
**Pros:**
- No engineering changes required.

**Cons:**
- Slow response time and inconsistent outcomes.

**Reason for rejection:** Manual control cannot meet latency and reliability targets.

### Alternative 2: Simple static rate limits
**Pros:**
- Easy to implement.

**Cons:**
- Cannot adapt to dynamic system heat.

**Reason for rejection:** Static limits are too coarse for real-time trading.

## Implementation

### Required Changes
- Add thermal signal computation in `tacl/`.
- Integrate throttle hooks in `runtime/` and `execution/`.

### Migration Path
Roll out governor in monitor-only mode before enabling enforcement.

### Validation Criteria
- Stress tests that validate recovery and hysteresis behavior.
- Verification that throttling signals reduce error rates.

## Related Decisions
- ADR-0006: TACL / Thermodynamic Control Layer

## References
- [core module](../../core/)
- [execution module](../../execution/)
- [runtime module](../../runtime/)
- [observability module](../../observability/)
- [tacl module](../../tacl/)

## Notes
Thermal thresholds must be reviewed quarterly to align with capacity planning.
