# OMS Theory Boundary

## Scope

This contract covers order-management invariants that are currently executable in GeoSync.

## Model

The OMS layer is treated as a deterministic state-transition system. A submitted order, a lifecycle event, and a fill record must preserve idempotency and causal ordering.

## Invariants

- INV-OMS1: exposed portfolio kinetic energy is finite and non-negative for finite position and return vectors.
- INV-OMS2: repeated submission of the same client or correlation key produces at most one state-changing transition.
- INV-OMS3: lifecycle timestamps for one order are monotonically non-decreasing.

## Witness rules

Tests must use deterministic connectors, isolated storage, explicit correlation keys, and observable lifecycle history. A witness must distinguish no-op replay from a second state change.

## Boundary

Current OMS evidence does not yet prove full per-fill accounting conservation against a live venue or order book. That stronger claim requires a complete OMS plus book fixture with cash, position, fee, and mark-to-market conservation checked after every fill.
