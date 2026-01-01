# ADR-0007: Core State Lattice and Canonical Feature Fabric

## Status
Accepted

**Date:** 2026-01-02

**Decision makers:** Principal Architect, Core Systems Lead, Quant Research Lead

## Context

Feature computation and market state derivation are currently distributed across multiple pipelines, which makes it difficult to guarantee determinism, traceability, and reuse. We need a single, canonical fabric inside `core/` that defines how raw market events become normalized features and state snapshots that are safe to consume downstream.

## Decision

Adopt a core state lattice that standardizes market state transitions and feature materialization. The canonical feature fabric will live in `core/` and define a deterministic ordering, schema versioning, and validation gates for all derived state and features.

## Consequences

### Positive
- Deterministic feature generation across training, backtesting, and live execution.
- Simplifies downstream consumption because `execution/`, `runtime/`, and `observability/` share the same canonical state model.

### Negative
- Additional upfront work to migrate existing feature pipelines into the lattice.
- Stricter schema validation may surface legacy inconsistencies.

### Neutral
- Requires ongoing schema governance and version bump discipline.

## Alternatives Considered

### Alternative 1: Keep feature logic in each pipeline
**Pros:**
- No migration effort in the short term.

**Cons:**
- Continues non-deterministic feature drift.

**Reason for rejection:** Increases divergence and reduces auditability.

### Alternative 2: Centralize features in a shared library outside `core/`
**Pros:**
- Can be reused without touching core state logic.

**Cons:**
- Leaves core state transitions fragmented and harder to test.

**Reason for rejection:** Does not guarantee canonical ordering or state lineage.

## Implementation

### Required Changes
- Define the state lattice schema and versioning rules in `core/`.
- Migrate existing feature builders to consume lattice transitions.

### Migration Path
Phase existing pipelines to read from the canonical fabric while preserving legacy outputs for verification.

### Validation Criteria
- Feature parity checks across training and live pipelines.
- Deterministic replay tests for state transitions.

## Related Decisions
- ADR-0004: Contract-First Modular Architecture

## References
- [core module](../../core/)
- [execution module](../../execution/)
- [runtime module](../../runtime/)
- [observability module](../../observability/)
- [tacl module](../../tacl/)

## Notes
The lattice should expose explicit upgrade hooks for feature schema evolution.
