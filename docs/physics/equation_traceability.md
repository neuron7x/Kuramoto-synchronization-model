# GeoSync Equation Traceability Index

Status: TRACEABILITY_DRAFT
Scope: canonical weighted Kuramoto core.

| equation_id | equation | source_reference | implemented_in | tested_by | validated_against | known_limits | failure_condition |
|---|---|---|---|---|---|---|---|
| EQ-GEO-KUR-001 | `d theta_i / dt = omega_i + K * sum_j A_ij * sin(theta_j - theta_i)` | Restrepo-Ott-Hunt 2005; Strogatz 2000; `docs/laws/T1_kuramoto_ricci_boundary.md` | `core/kuramoto/kuramoto_ricci_engine.py::kuramoto_ricci_rhs` | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py`; `tests/physics/test_invariants.py`; `tests/physics/test_convergence.py` | boundary/null/invariant/convergence gates | Ricci bridge not canonical; market graph adapter not audited here | RHS output non-finite or nulls produce false sync |
| EQ-GEO-KUR-002 | `R = abs(mean(exp(i*theta)))` | Kuramoto order parameter | `core/kuramoto/kuramoto_ricci_engine.py::order_parameter` | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py`; `tests/physics/test_invariants.py`; `tests/physics/test_interface_contracts.py` | invariant `R in [0,1]` | finite-size baseline must be respected | `R < 0`, `R > 1`, NaN, Inf |
| EQ-GEO-KUR-003 | `Phi(K,gamma,A)=K*lambda_max(A)-2*gamma` | Restrepo-Ott-Hunt threshold specialization | `core/kuramoto/kuramoto_ricci_engine.py::phase_transition_boundary` | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py`; `tests/physics/test_interface_contracts.py` | complete graph and zero adjacency boundary tests | assumes non-negative symmetric adjacency | inconsistent `K_c`, signed adjacency accepted, invalid gamma/K repaired |
| EQ-GEO-KUR-004 | `K_c = 2*gamma/lambda_max(A)` | Restrepo-Ott-Hunt 2005 | `core/kuramoto/kuramoto_ricci_engine.py::phase_transition_boundary` | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py`; `tests/physics/test_invariants.py` | complete graph and zero graph tests | `lambda_max(A)=0` returns infinity | finite `K_c` for zero graph |
| EQ-GEO-KUR-005 | `V = 0.5 * sum_ij A_ij * (1-cos(theta_i-theta_j))` | homogeneous Kuramoto potential | `core/kuramoto/kuramoto_ricci_engine.py::coupling_potential` | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | monotonicity with `omega=0` and non-vacuity with `omega!=0` | only homogeneous limit claim | potential monotonicity claimed outside stated condition |
| EQ-GEO-RICCI-001 | `A_ij = max(kappa_ij,0), A_ii=0, A=A^T` | `docs/laws/T1_kuramoto_ricci_boundary.md`; Ricci references | `core/kuramoto/kuramoto_ricci_engine.py::ricci_to_adjacency` | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | static mapping and signed-adjacency rejection | graph construction and curvature computation not fully audited in this pass | Ricci accepted as canonical without bridge proof |

## Current traceability verdict

```text
TRACEABILITY_STATUS: PARTIAL_PASS
MISSING: runtime-generated pytest report, UQ artifact, full local inventory hash
FINAL_RANK_CLAIM: FORBIDDEN
```
