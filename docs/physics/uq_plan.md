# GeoSync UQ Plan

Status: UQ_SOURCE_DECLARED_NOT_EXECUTED
Scope: canonical weighted Kuramoto validation lane.

## Rule

Uncertainty quantification is forbidden unless a stochastic source is declared.

## Declared stochastic sources

| source_id | type | parameter | distribution | range | reason | observable |
|---|---|---|---|---|---|---|
| UQ-IC-001 | initial condition distribution | `theta_0` | uniform | `[-pi, pi]` | phase initialization uncertainty | `R_mean`, `R_late` |
| UQ-OMG-001 | intrinsic frequency distribution | `omega_i` | Lorentzian or centered normal for smoke tests | declared by scenario | synchronization onset depends on frequency spread | `Phi`, `R_mean`, `lambda_1` |
| UQ-SOLVER-001 | solver tolerance / time-step refinement | `dt` | deterministic refinement set | `dt, dt/2, dt/4` | detect solver-created physics | final-state L_inf error |

## Solo-feasible plan

```text
Latin Hypercube or seeded grid, N=50-200 only after local runtime budget is known.
No fake 10k-run HPC claims.
```

## Required artifact

```text
artifacts/physics_validation/uq_summary.json
```

## Required tests

```text
tests/physics/test_uq_smoke.py
```

## Current verdict

```text
UQ_STATUS: SOURCE_DECLARED
UQ_EXECUTION: NOT_DONE
CONFIDENCE_INTERVAL_CLAIM: FORBIDDEN
```
