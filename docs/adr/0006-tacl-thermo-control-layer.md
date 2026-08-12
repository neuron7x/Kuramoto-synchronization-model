# ADR-0006: TACL / Thermodynamic Control Layer

## Status
Accepted

**Date:** 2025-12-08

**Decision makers:** Runtime Guild, Safety & Reliability Council, Principal System Architect

## Context

Runtime control in GeoSync must manage adaptive topology changes, risk throttling, and crisis responses without destabilizing live trading. Ad-hoc control actions can:
- Escalate system instability during degraded states.
- Circumvent safety approvals for systemic changes.
- Mask free-energy spikes that indicate unsafe adaptation.

GeoSync already includes a thermodynamic controller and a behavioral contract layer (TACL). We need a formal ADR capturing the governance, gating, and safety semantics.

## Decision

Adopt a **Thermodynamic Autonomic Control Layer (TACL)** that enforces safety gates for runtime control actions:

1. **Behavioral contracts** define allowed actions and states per module (`runtime/behavior_contract.py`).
2. **Action classification** (A0/A1/A2) gates systemic changes and mandates dual approval for A2.
3. **Thermodynamic checks** ensure monotonic or bounded free-energy descent via `runtime/thermo_controller.py`.
4. **Kill-switch integration** blocks all control actions when emergency stop is active.

The runtime layer must route all control decisions through TACL gates before applying topology or risk changes.

## Consequences

### Positive
- Prevents unsafe adaptations during crisis states.
- Provides auditable control decisions and reason codes.
- Aligns runtime behavior with safety governance.

### Negative
- Additional gating can slow reaction time for systemic changes.
- Requires ongoing calibration of free-energy thresholds.

### Neutral
- Adds operational dependency on dual-approval workflows.

## Alternatives Considered

### Alternative 1: Reactive heuristics without formal gates
**Pros:**
- Fast control-loop reactions.

**Cons:**
- No auditable safety guarantees.

**Reason for rejection:** Unsafe for production-grade runtime control.

### Alternative 2: Manual approvals for all actions
**Pros:**
- Maximum oversight.

**Cons:**
- Operationally infeasible for A0/A1 adjustments.

**Reason for rejection:** Slows routine stabilization tasks.

## Implementation

### Required Changes
- Keep mandates and gates centralized in `runtime/behavior_contract.py`.
- Enforce thermodynamic checks in `runtime/thermo_controller.py` control loop.
- Maintain supporting primitives in `tacl/` (energy model, behavioral contract extensions).

### Migration Path
- Route existing control calls through `tacl_gate` and backfill decision logs.

### Validation Criteria
- Unit tests confirm crisis downgrades and dual-approval checks.
- Free-energy monotonicity violations are blocked with explicit reasons.

## Related Decisions
- ADR-0004: Contract-First Modular Architecture

## References
- `runtime/behavior_contract.py`
- `runtime/thermo_controller.py`
- `docs/RFC_TACL_GOVERNANCE_LAYER.md`
- `tacl/`

## Notes
- **Release:** 0.1.0
- **Modules:** `runtime/`, `core/`, `execution/`
