# Kuramoto coupling config guard — closing the legacy double-scaling bypass

## Problem

The Kuramoto right-hand side sums an effective coupling `C`:

```
dθ_i/dt = ω_i + Σ_j C_ij · sin(θ_j − θ_i)
```

`CouplingSpec` (Stream-1 contract) already guarantees *coupling appears exactly
once* at the spec layer. But `KuramotoConfig(K, adjacency)` — the bare
constructor — still applied `C = K · adjacency` without knowing whether
`adjacency` was a **normalized topology** `A` (scale intended, `C = K·A`) or an
**already-physical weight matrix** `W` (`C = W`). Passing `W` with a non-unit
`K` silently double-scaled the coupling (`C = K·W`): plausible dynamics, green
tests, wrong reported coupling strength.

## Fix

`KuramotoConfig` now carries the convention explicitly and fails closed:

| Construction | Outcome |
|---|---|
| `from_coupling_spec(spec)` | Canonical: scale applied once, `K` pinned to `1.0`, `claim_boundary` propagated |
| `adjacency_kind="full_weight"` + `K != 1.0` | **`ValueError`** (would double-scale) |
| undeclared convention + `K != 1.0` | **`ValueError`** — rejected fail-closed (cannot tell `A` from `W`, so the ambiguity must not pass silently) |
| `adjacency_kind="normalized_topology"` | `C = K·A` accepted for any `K` |
| attractive `claim_boundary` over negative edges / negative `K` | **`ValueError`** (signed coupling cannot claim attractive Kuramoto) |

All in-repo `K != 1` adjacency call sites were migrated to declare
`adjacency_kind="normalized_topology"`, preserving the existing `C = K·A`
behaviour while making the convention auditable.

## Verification

- `tests/unit/core/test_config_coupling_migration.py` — config-layer guard
  (undeclared-K!=1-rejected, declared-normalized-K!=1-constructs, scale-once,
  full-weight-requires-unit-K, signed-cannot-claim-attractive).
- `tests/unit/core/test_kuramoto_coupling_spec.py` — spec-layer contract (unchanged, still green).
- `ruff format` + `black` + `ruff check` + `mypy --strict` clean.

**Falsifier:** both silent-double-scaling paths must raise `ValueError` — a
`full_weight` matrix scaled by a non-unit `K`, **and** an undeclared convention
with `K != 1.0`. If either construction exits 0 the anti-double-scaling guard
has regressed.

## Why fail-closed, not a warning

The earlier guard demoted the undeclared `K != 1.0` path to a
`DeprecationWarning`. That left FP-1's residual hole open: a caller passing a
physical weight matrix `W` with `K != 1.0` and no `adjacency_kind` would still
get `C = K·W` double-scaled, only now with a warning that production code
routinely suppresses. The constructor has no way to distinguish a normalized
topology `A` from a physical weight matrix `W` by inspection, so the *only*
sound behaviour on the ambiguous input is to refuse construction. This makes the
guard consistent with FP-1's invariant — "one equation, one owner of scale" —
at the config boundary, not merely at the engine RHS.
