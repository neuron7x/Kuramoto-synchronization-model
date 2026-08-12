# ADR-0004: Contract-First Modular Architecture

## Status
Accepted

**Date:** 2025-12-08

**Decision makers:** Principal System Architect, Core Platform Guild, Execution Guild, Runtime Guild

## Context

GeoSync spans multiple bounded domains (research, execution, runtime control) that evolve independently. Without formalized contracts, interface drift leads to:
- Integration failures across `core/`, `execution/`, and `runtime/`.
- Undetected schema changes in strategy inputs/outputs.
- Higher onboarding time due to implicit coupling.

Existing modules already expose contract-like behavior:
- `core/strategies/engine.py` enforces IO contracts at runtime.
- `execution/adapters/plugin.py` declares adapter contracts for connectors.
- `runtime/behavior_contract.py` defines behavioral mandates for control actions.

We need a unified, contract-first architecture that standardizes how modules declare and validate inputs/outputs, version compatibility, and integration boundaries.

## Decision

Adopt a **contract-first modular architecture** for all cross-module interactions:

1. **Declare explicit IO contracts** for strategy modules in `core/` using `IOContract` and validation hooks.
2. **Define adapter interface contracts** for execution connectors in `execution/` (identifier, transport, credentials, capabilities, version).
3. **Formalize runtime control contracts** in `runtime/` through TACL mandates and gated actions.
4. **Document canonical contracts** in `docs/contracts/interface-contracts.md` with versioned semantics and traceability.

All new modules that cross boundaries between `core/`, `execution/`, and `runtime/` must expose a contract definition, validation strategy, and version compatibility plan.

## Consequences

### Positive
- Clear integration boundaries enable parallel development across guilds.
- Contract validation catches breaking changes early.
- Documentation becomes a single source of truth for integrations.

### Negative
- Increased upfront effort to define and maintain contracts.
- Runtime validation adds measurable overhead for some flows.

### Neutral
- Requires periodic contract audits to keep implementations aligned.

## Alternatives Considered

### Alternative 1: Informal documentation only
**Pros:**
- Faster iteration without validation overhead.

**Cons:**
- High integration risk and hidden coupling.

**Reason for rejection:** Failed to prevent recurring interface regressions.

### Alternative 2: Hard-coded integration tests without contract specs
**Pros:**
- Detects regressions in CI.

**Cons:**
- Lacks human-readable contract definitions and versioning metadata.

**Reason for rejection:** Tests alone do not provide explicit design intent.

## Implementation

### Required Changes
- Maintain IO contracts in `core/strategies/engine.py` and strategy module definitions.
- Require `AdapterContract` metadata for all `execution/adapters/*` plugins.
- Apply TACL behavioral contracts in `runtime/behavior_contract.py` gates.
- Update `docs/contracts/interface-contracts.md` with version references for cross-module APIs.

### Migration Path
- Incrementally formalize existing integrations by documenting contracts and adding validation.

### Validation Criteria
- Contract validation failures surface in CI and runtime logs.
- ADR-referenced modules expose current contract versions.

## Related Decisions
- ADR-0002: Versioned Market Data Storage
- ADR-0006: TACL / Thermodynamic Control Layer

## References
- `core/strategies/engine.py`
- `execution/adapters/plugin.py`
- `runtime/behavior_contract.py`
- `docs/contracts/interface-contracts.md`

## Notes
- **Release:** 0.1.0
- **Modules:** `core/`, `execution/`, `runtime/`
