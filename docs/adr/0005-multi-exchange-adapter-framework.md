# ADR-0005: Multi-Exchange Adapter Framework

## Status
Accepted

**Date:** 2025-12-08

**Decision makers:** Execution Guild, Integrations Team, Principal System Architect

## Context

TradePulse must execute across multiple broker and exchange venues with differing APIs, credentials, rate limits, and transport modes. A monolithic execution layer risks:
- Tight coupling between execution logic and exchange specifics.
- High regression risk when adding new venues.
- Inconsistent capabilities and diagnostics across adapters.

Existing connector code already points toward a plugin model (`execution/adapters/*`) with declared contracts (`AdapterContract`) and a registry. We need to formalize this as the standard architecture for multi-exchange support.

## Decision

Implement a **multi-exchange adapter framework** with explicit contracts and plugin registration:

1. **Adapter contracts** define `identifier`, `provider`, `version`, required credentials, transports, and declared capabilities.
2. **Adapter registry** (`AdapterRegistry`) manages discovery, registration, and instantiation of adapters.
3. **Self-diagnostics** are optional but standardized via `AdapterDiagnostic` for health checks.
4. **Capability-based routing** allows `execution/` and `core/` workflows to select adapters based on declared features.

The execution core interacts only with adapter contracts and registries, not exchange-specific logic.

## Consequences

### Positive
- Adding a new exchange requires only a new adapter plugin.
- Standardized contracts simplify integration testing and ops automation.
- Capability metadata enables deterministic routing and sandbox qualification.

### Negative
- Adapter contracts must be kept up to date with provider changes.
- Additional abstraction introduces minor overhead in adapter discovery.

### Neutral
- Requires coordination between execution and runtime orchestration for adapter availability.

## Alternatives Considered

### Alternative 1: Single unified connector
**Pros:**
- Fewer moving parts.

**Cons:**
- High coupling and slow iteration for new venues.

**Reason for rejection:** Conflicts with multi-venue expansion roadmap.

### Alternative 2: Per-exchange bespoke integrations without contracts
**Pros:**
- Fast initial integration.

**Cons:**
- No shared diagnostics or capability metadata.

**Reason for rejection:** Increases operational risk and onboarding costs.

## Implementation

### Required Changes
- Ensure each adapter in `execution/adapters/` declares an `AdapterContract`.
- Register adapters through `execution/adapters/__init__.py` and entry points.
- Standardize adapter diagnostics and self-test hooks.
- Keep connector interfaces aligned with `interfaces/execution/` contracts.

### Migration Path
- Wrap legacy connectors in adapter plugins and backfill contract metadata.

### Validation Criteria
- Registry exposes consistent adapter metadata via `registry.contracts()`.
- Self-tests produce `AdapterDiagnostic` results for CI smoke checks.

## Related Decisions
- ADR-0004: Contract-First Modular Architecture

## References
- `execution/adapters/plugin.py`
- `execution/adapters/__init__.py`
- `execution/adapters/binance.py`
- `execution/adapters/coinbase.py`
- `execution/adapters/kraken.py`
- `interfaces/execution/`

## Notes
- **Release:** 0.1.0
- **Modules:** `execution/`, `core/`, `runtime/`
