# ADR-0010: Observability Unified Telemetry Fabric

## Status
Accepted

**Date:** 2026-01-02

**Decision makers:** Observability Lead, SRE Lead, Principal Architect

## Context

Telemetry is fragmented across tracing, metrics, and logs, with inconsistent correlation IDs. We need a unified fabric that offers end-to-end visibility and ties together runtime scheduling, execution decisions, and TACL signals.

## Decision

Create a unified telemetry fabric in `observability/` that standardizes correlation IDs, event schemas, and sampling strategy. All critical components (`core/`, `execution/`, `runtime/`, `tacl/`) will emit to this fabric with shared context propagation.

## Consequences

### Positive
- End-to-end traceability across modules.
- Simplifies incident response and root cause analysis.

### Negative
- Requires instrumentation updates across multiple modules.
- Increased telemetry volume must be controlled via sampling.

### Neutral
- Adds governance overhead for schema evolution.

## Alternatives Considered

### Alternative 1: Keep module-specific telemetry standards
**Pros:**
- Minimal instrumentation changes.

**Cons:**
- Hard to correlate events across modules.

**Reason for rejection:** Limits observability depth and auditing capability.

### Alternative 2: Adopt third-party tracing without schema alignment
**Pros:**
- Faster to implement.

**Cons:**
- Inconsistent domain semantics and missing business context.

**Reason for rejection:** Does not meet traceability requirements.

## Implementation

### Required Changes
- Introduce shared telemetry schemas and correlation helpers in `observability/`.
- Update emitters in `core/`, `execution/`, `runtime/`, and `tacl/`.

### Migration Path
Dual-write legacy and new telemetry for one release cycle, then deprecate old schemas.

### Validation Criteria
- Cross-module trace correlation tests.
- Sampling validation to ensure budgeted telemetry volume.

## Related Decisions
- ADR-0002: Serotonin Controller - Hysteretic Hold Logic with SRE Observability

## References
- [core module](../../core/)
- [execution module](../../execution/)
- [runtime module](../../runtime/)
- [observability module](../../observability/)
- [tacl module](../../tacl/)

## Notes
Telemetry must carry risk policy IDs and scheduler ring metadata.
