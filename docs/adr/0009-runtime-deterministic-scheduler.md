# ADR-0009: Runtime Deterministic Scheduler and Isolation Rings

## Status
Accepted

**Date:** 2026-01-02

**Decision makers:** Runtime Lead, Platform Lead, Principal Architect

## Context

The runtime currently mixes real-time and batch workloads without strict isolation, increasing the risk of latency spikes and nondeterministic execution ordering. We need a deterministic scheduling model that aligns with system-level SLAs and supports replay.

## Decision

Adopt a deterministic scheduler in `runtime/` with explicit isolation rings for real-time, near-real-time, and batch workloads. Scheduling priorities will be derived from policy configuration, and all execution ordering will be logged to `observability/` for replay.

## Consequences

### Positive
- Predictable latency for real-time trading workloads.
- Deterministic replay for debugging and incident analysis.

### Negative
- Requires changes to workload definitions and deployment manifests.
- Increased scheduling complexity in the runtime control plane.

### Neutral
- Future workload classes can be added as new rings.

## Alternatives Considered

### Alternative 1: Continue with best-effort scheduling
**Pros:**
- Minimal implementation overhead.

**Cons:**
- Latency unpredictability and reduced replay fidelity.

**Reason for rejection:** Does not meet SLA requirements for mission-critical workloads.

### Alternative 2: Delegate scheduling to external orchestrators only
**Pros:**
- Leverages existing tooling.

**Cons:**
- Lacks domain-specific determinism and observability hooks.

**Reason for rejection:** External orchestrators cannot encode domain priorities reliably.

## Implementation

### Required Changes
- Define ring-based scheduling policies in `runtime/`.
- Emit scheduling traces into `observability/`.

### Migration Path
Start with a dual-mode scheduler to compare outputs before enforcing deterministic ordering.

### Validation Criteria
- Load tests verifying latency budgets per ring.
- Deterministic replay of scheduling decisions.

## Related Decisions
- ADR-0004: Contract-First Modular Architecture

## References
- [core module](../../core/)
- [execution module](../../execution/)
- [runtime module](../../runtime/)
- [observability module](../../observability/)
- [tacl module](../../tacl/)

## Notes
Isolation rings should be aligned with deployment environments and risk tiers.
