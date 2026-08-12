# GeoSync Canonical Physics Core

Status: CANONICALIZATION_DRAFT
Subsystem: GeoSync
Canonical object selected for this validation lane: **Pure weighted graph Kuramoto with non-negative adjacency**.

Ricci is not removed. Ricci is demoted from canonical dynamics to an adjacency-generation / experimental bridge until the curvature computation, graph construction, boundedness, and null-model evidence are fully audited.

## 1. Chosen object

```text
Pure weighted graph Kuramoto ODE on an undirected non-negative weighted graph.
```

## 2. Equation

For `N` oscillators:

```text
d theta_i / dt = omega_i + K * sum_j A_ij * sin(theta_j - theta_i)
```

with:

```text
A_ij >= 0
A_ii = 0
A = A^T
K >= 0
theta_i in radians
omega_i in radians / time
gamma > 0
```

## 3. Onset boundary

For Lorentzian intrinsic-frequency half-width `gamma`:

```text
Phi(K, gamma, A) = K * lambda_max(A) - 2 * gamma
K_c = 2 * gamma / lambda_max(A)
```

If `lambda_max(A) <= 0`:

```text
K_c = inf
Phi = -2 * gamma
```

## 4. State variables

| variable | meaning | units | shape | valid range |
|---|---|---|---|---|
| `theta` | oscillator phase | radians | `(N,)` or `(T,N)` | finite real |
| `omega` | intrinsic angular frequency | radians / time | `(N,)` | finite real |
| `A` | non-negative weighted adjacency | dimensionless or declared edge weight unit | `(N,N)` | `A_ij >= 0`, symmetric, zero diagonal |
| `K` | coupling strength | 1 / time if `A` dimensionless | scalar | finite, `K >= 0` |
| `gamma` | Lorentzian half-width | radians / time | scalar | finite, `gamma > 0` |

## 5. Parameters

| parameter | role | required guard |
|---|---|---|
| `dt` | integration time step | `dt > 0`, stability/convergence must be tested |
| `n_steps` | integration length | positive integer |
| `lambda_max(A)` | spectral radius | computed from symmetric non-negative `A` |
| `N` | oscillator count | positive integer |

## 6. Observables

| observable | formula | valid range | failure condition |
|---|---|---|---|
| `R` | `abs(mean(exp(i*theta)))` | `[0,1]` | any `R < 0`, `R > 1`, NaN, Inf |
| `Phi` | `K*lambda_max(A)-2*gamma` | finite unless invalid input | mismatch with `K_c` boundary |
| `K_c` | `2*gamma/lambda_max(A)` | positive or `inf` | finite value for zero adjacency |
| `V(theta,A)` | `0.5 * sum_ij A_ij*(1-cos(theta_i-theta_j))` | `>=0` for `A>=0` | increase under homogeneous `omega=0` test beyond tolerance |
| `lambda_1` | leading Lyapunov estimate | scenario-dependent | wrong sign regime around boundary |

## 7. Code carriers

| carrier | role |
|---|---|
| `core/kuramoto/kuramoto_ricci_engine.py::kuramoto_ricci_rhs` | RHS closure |
| `core/kuramoto/kuramoto_ricci_engine.py::kuramoto_ricci_step` | midpoint/Heun step |
| `core/kuramoto/kuramoto_ricci_engine.py::kuramoto_ricci_trajectory` | trajectory integration |
| `core/kuramoto/kuramoto_ricci_engine.py::order_parameter` | observable `R` |
| `core/kuramoto/kuramoto_ricci_engine.py::phase_transition_boundary` | `Phi`, `K_c`, `lambda_max(A)` |
| `core/kuramoto/kuramoto_ricci_engine.py::ricci_to_adjacency` | optional mapping from bounded curvature to non-negative adjacency |
| `core/kuramoto/kuramoto_ricci_engine.py::coupling_potential` | homogeneous-limit potential |

## 8. Test carriers

| test file | expected role |
|---|---|
| `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | boundary, invariants, nulls, negative controls, determinism |
| `tests/physics/test_geosync_nulls.py` | to be added or aliased to T1 null tests |
| `tests/physics/test_invariants.py` | to be added or aliased to invariant subset |
| `tests/physics/test_convergence.py` | missing; required before high score |
| `tests/physics/test_interface_contracts.py` | missing; required before vertical validation |

## 9. Invalid or quarantined claims

| claim | decision | reason |
|---|---|---|
| Ricci-modulated Kuramoto is fully canonical | QUARANTINE | bridge proof not fully audited in this pass |
| GeoSync physical rank is 88-92 | FORBIDDEN | no generated S_total yet |
| BN-Syn validates here | BLOCKED | external source tree not present in GeoSync branch |
| MFN+ validates here | BLOCKED | external source tree and explicit PDE terms absent |
| UQ confidence intervals are meaningful | FORBIDDEN | no declared stochastic source in this lane |

## 10. Failure conditions

Stop immediately if any is true:

```text
A has negative entries and is passed directly to boundary calculation
theta, omega, R, Phi, K_c contain NaN or Inf unexpectedly
R leaves [0,1]
K < 0 or gamma <= 0 is silently repaired
K=0 or shuffled phases produce strong synchronization
subcritical Phi produces high R in the declared test regime
supercritical Phi fails to lock in the declared test regime
homogeneous omega=0 potential increases beyond tolerance
convergence under dt refinement is not measured
score is manually estimated instead of computed by tools/physics_score.py
```

## 11. Current canonicalization decision

```text
CP1_CANONICAL_GATE: PARTIAL_PASS_FOR_GEOSYNC_T1
CANONICAL_OBJECT_COUNT: 1
RICCI_STATUS: EXPERIMENTAL_BRIDGE_OR_ADJACENCY_GENERATOR
BN_SYN_STATUS: OUT_OF_SCOPE_BLOCKED
MFN_PLUS_STATUS: OUT_OF_SCOPE_BLOCKED
NEXT_GATE: CP2_BASELINE_ORACLE
```
