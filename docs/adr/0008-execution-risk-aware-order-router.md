# ADR-0008: Execution Risk-Aware Order Router

## Status
Accepted

**Date:** 2026-01-02

**Decision makers:** Execution Lead, Risk Lead, Principal Architect

## Context

Execution currently relies on static routing rules and scattered risk checks. We need a centralized router that enforces risk policy, aligns with core state, and exposes deterministic behavior for audits and simulation.

## Decision

Implement a risk-aware order router inside `execution/` that consumes canonical state from `core/`, enforces hard/soft risk limits, and emits structured telemetry to `observability/`. Routing decisions must be deterministic, replayable, and parameterized by runtime policies.

## Consequences

### Positive
- Unified enforcement of risk constraints across all order types.
- Deterministic routing decisions for audit and replay.

### Negative
- Requires refactoring existing exchange adapters to use the router.
- Additional latency budgets must be carefully managed.

### Neutral
- Governance needed for risk policy versioning.

## Alternatives Considered

### Alternative 1: Keep per-exchange routing logic
**Pros:**
- Minimal disruption to current adapters.

**Cons:**
- Inconsistent risk enforcement and duplicated logic.

**Reason for rejection:** Increases operational risk and compliance burden.

### Alternative 2: Push routing logic into `runtime/`
**Pros:**
- Central control plane for routing.

**Cons:**
- Blurs boundaries between execution and scheduling.

**Reason for rejection:** Breaks contract-first modular separation.

## Implementation

### Required Changes
- Introduce a routing policy interface in `execution/`.
- Normalize adapter inputs to consume routing outputs.

### Migration Path
Use feature flags to switch individual exchanges to the router, with shadow evaluation for comparison.

### Validation Criteria
- Risk limit enforcement tests with simulated order bursts.
- Replay tests using recorded order streams.

## Related Decisions
- ADR-0005: Multi-Exchange Adapter Framework

## References
- [core module](../../core/)
- [execution module](../../execution/)
- [runtime module](../../runtime/)
- [observability module](../../observability/)
- [tacl module](../../tacl/)

## Notes
The router should emit decision traces with policy IDs for auditability.
