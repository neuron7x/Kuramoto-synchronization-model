# Ricci Bridge Experimental Register

Status: EXPERIMENTAL_BRIDGE
Parent: `docs/physics/geosync_core.md`

## Decision

Ricci is not accepted as a fully validated canonical dynamics layer in this validation pass.

The canonical object is Pure Weighted Graph Kuramoto. Ricci may enter only as a traceable adjacency-generation mechanism when all bridge conditions are satisfied.

## Required bridge proof

Ricci-Kuramoto coupling becomes eligible for canonical status only when the repository defines and tests all of the following:

| requirement | required carrier | current status |
|---|---|---|
| exact graph construction from market data | code + interface contract | UNKNOWN_IN_THIS_PASS |
| exact curvature definition `kappa_ij` | equation + code path + citation | PARTIAL_STATIC_EVIDENCE |
| boundedness `kappa_ij in [-1,1]` or explicit runtime clamp policy | test + metric + failure condition | UNKNOWN_IN_THIS_PASS |
| mapping `A_ij = f(kappa_ij)` | equation + code path | PRESENT_STATICALLY for `max(kappa,0)` |
| proof or empirical evidence that mapped `A` is symmetric non-negative zero-diagonal | test | PRESENT_STATICALLY for mapping function |
| null model where Ricci graph is degree/weight matched against random graph | test | MISSING_IN_THIS_PASS |
| sensitivity of `Phi` and `R` to curvature perturbation | metric + artifact | MISSING |
| failure mode for curvature artifact | falsification test | MISSING |

## Allowed claims now

```text
Ricci values can be mapped into a non-negative adjacency candidate.
Pure weighted Kuramoto can consume that adjacency if it satisfies the A contract.
The current bridge is implementation-present but not fully physically validated.
```

## Forbidden claims now

```text
Ricci-modulated Kuramoto is fully validated.
Ricci curvature makes the model physical by itself.
Ricci improves predictive quality without null-model comparison.
Curvature weighting is not ad-hoc unless the graph construction and null tests are shown.
```

## Falsification requirements

| falsifier_id | H0 | H1 | observable | failure condition | test file |
|---|---|---|---|---|---|
| RICCI-NULL-001 | Ricci-derived adjacency behaves no better than degree/weight-matched ER graph | Ricci adjacency produces regime-specific `R` not reproduced by null graph | `R_mean`, `Phi`, `lambda_max(A)` | Ricci signal disappears under matched null | `tests/physics/test_geosync_nulls.py` |
| RICCI-NULL-002 | curvature perturbation has no structured effect | small bounded perturbation changes `Phi` and `R` monotonically only where expected | sensitivity of `Phi`, `R` | unstable or sign-flipping sensitivity without explanation | `tests/physics/test_geosync_nulls.py` |
| RICCI-NULL-003 | negative curvature leakage can fake anti/sync behavior | contract blocks signed `A` before boundary computation | exception path | signed adjacency accepted silently | `tests/physics/test_invariants.py` |

## Current verdict

```text
RICCI_STATUS: EXPERIMENTAL
CANONICAL_STATUS: NOT_ACCEPTED
REASON: bridge proof and null-model comparisons incomplete
```
