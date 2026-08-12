# Initial Physics Claim Ledger

Status: BOOTSTRAP_CLAIM_LEDGER
Scope: GeoSync T1 lane plus external-scope blockers for BN-Syn and MFN+.

A claim is valid only when it has at least one carrier:

```text
equation | code_path | test | metric | baseline_value | citation | failure_condition
```

## Ledger verdict

```text
CLAIM_LEDGER_STATUS: PARTIAL
GEOSYNC_T1_CLAIMS: EVIDENCE_MAPPED_STATICALLY
CURRENT_TEST_RUN: NOT_OBSERVED_BY_CONNECTOR
BN_SYN_CLAIMS: BLOCKED_EXTERNAL_SCOPE
MFN_PLUS_CLAIMS: BLOCKED_EXTERNAL_SCOPE
PHYSICAL_RANK_CLAIM: FORBIDDEN
```

## GeoSync T1 claims

| claim_id | raw_claim | source_file | mathematical_object | evidence_type | status | required_action |
|---|---|---|---|---|---|---|
| CLM-GEO-T1-001 | Kuramoto-Ricci dynamics are `theta_dot_i = omega_i + K * sum_j A_ij * sin(theta_j - theta_i)` | `docs/laws/T1_kuramoto_ricci_boundary.md`; `core/kuramoto/kuramoto_ricci_engine.py` | weighted Kuramoto ODE on graph | equation, code_path | VERIFIED_STATIC | execute pytest to confirm runtime behavior |
| CLM-GEO-T1-002 | Ricci curvature matrix is converted to non-negative sync adjacency by `A_ij = max(kappa_ij, 0)`, zero diagonal, symmetric | `docs/laws/T1_kuramoto_ricci_boundary.md`; `core/kuramoto/kuramoto_ricci_engine.py` | bounded weighted graph adjacency | equation, code_path, test | VERIFIED_STATIC | add explicit bridge proof or keep Ricci interpretation experimental |
| CLM-GEO-T1-003 | Synchronization onset boundary is `Phi(K,gamma,A)=K*lambda_max(A)-2*gamma` | `docs/laws/T1_kuramoto_ricci_boundary.md`; `core/kuramoto/kuramoto_ricci_engine.py` | Restrepo-Ott-Hunt threshold specialization | equation, code_path, citation, test | VERIFIED_STATIC | require local run of boundary tests |
| CLM-GEO-T1-004 | `K_c = 2*gamma/lambda_max(A)` and `K_c=inf` when `lambda_max(A)=0` | `core/kuramoto/kuramoto_ricci_engine.py` | critical coupling | equation, code_path, test | VERIFIED_STATIC | include in scoring oracle |
| CLM-GEO-T1-005 | Order parameter `R=abs(mean(exp(i*theta)))` must remain in `[0,1]` | `core/kuramoto/kuramoto_ricci_engine.py`; `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | Kuramoto order parameter | equation, code_path, test, failure_condition | VERIFIED_STATIC | include in invariant score |
| CLM-GEO-T1-006 | Subcritical `Phi < 0` should produce finite-size incoherent `R` | `docs/laws/T1_kuramoto_ricci_boundary.md`; `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | asymptotic finite-size bound | test, metric, failure_condition | IMPLEMENTED_NOT_RERUN | run test battery on current branch |
| CLM-GEO-T1-007 | Supercritical `Phi > 0` should produce high `R` in the configured test regime | `docs/laws/T1_kuramoto_ricci_boundary.md`; `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | synchronization regime | test, metric, failure_condition | IMPLEMENTED_NOT_RERUN | run test battery on current branch |
| CLM-GEO-T1-008 | With `omega=0`, coupling potential is non-increasing | `core/kuramoto/kuramoto_ricci_engine.py`; `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | Lyapunov-like potential for homogeneous coupling | equation, code_path, test, failure_condition | IMPLEMENTED_NOT_RERUN | run test battery and add convergence sensitivity |
| CLM-GEO-T1-009 | Nonzero `omega` can make potential increase, proving the homogeneous Lyapunov claim is non-vacuous | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | negative control | test, failure_condition | IMPLEMENTED_NOT_RERUN | require negative-control pass in CI |
| CLM-GEO-T1-010 | Zero coupling `K=0` must not create synchronization | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | null model: independent rotators | test, failure_condition | IMPLEMENTED_NOT_RERUN | include in null-model score |
| CLM-GEO-T1-011 | Trajectory and step are deterministic for identical inputs | `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py` | deterministic numerical map | test, metric | IMPLEMENTED_NOT_RERUN | include in reproducibility score |
| CLM-GEO-T1-012 | T1 test battery has 18 tests and all are green | `docs/laws/T1_kuramoto_ricci_boundary.md` | test-suite status claim | test | UNVERIFIED_CURRENT_RUN | replace with machine-generated pytest artifact before final verdict |

## Claims quarantined as non-final

| claim_id | raw_claim | source | reason | status | required_action |
|---|---|---|---|---|---|
| CLM-RICCI-001 | Ollivier-Ricci weighting is physically-derived and not ad-hoc tuning | `docs/laws/T1_kuramoto_ricci_boundary.md` | interpretation may be useful, but validation requires the exact kappa computation, graph construction, boundedness, and empirical nulls | IMPLEMENTED_NOT_VALIDATED | move to `docs/physics/ricci_experimental.md` until bridge evidence is complete |
| CLM-RICCI-002 | Ricci-modulated Kuramoto is canonical | prior protocol scope | canonical bridge is not fully audited in this pass | WRONG_LEVEL | keep Pure Weighted Kuramoto canonical; Ricci as adjacency generator/experimental extension |
| CLM-SCORE-001 | Repository has physical score 88-92 | requested target | no computed S_total artifact exists yet | UNDEFINED | compute with `tools/physics_score.py`; current bootstrap S0 is below target |
| CLM-BNSYN-001 | BN-Syn validates AdEx + conductance + Q10 | external user context | source tree not present in this GeoSync branch | BLOCKED_EXTERNAL_SCOPE | attach immutable BN-Syn source ref |
| CLM-MFN-001 | MFN+ validates reaction-diffusion PDE | external user context | source tree and explicit `f(u,v), g(u,v)` not present in this GeoSync branch | BLOCKED_EXTERNAL_SCOPE | attach immutable MFN+ source ref and PDE definitions |

## Noise deletion rule

| noise_id | text class | action |
|---|---|---|
| NOISE-001 | any phrase claiming `research-grade`, `physical rank`, `verified physics`, or `world model` without computed artifact | delete or rewrite as BLOCKED |
| NOISE-002 | any Ricci/Kuramoto coupling claim without `kappa_ij(t)`, `f(kappa)`, boundedness, and null tests | quarantine as experimental |
| NOISE-003 | any Monte Carlo/UQ claim without prior, IC distribution, observation-noise model, or solver-tolerance uncertainty | mark UQ_INVALID |

## CP0 claim decision

```text
CLAIMS_CLASSIFIED: PARTIAL
GEOSYNC_T1_EVIDENCE: STATICALLY_PRESENT
RUNTIME_VALIDATION: NOT_OBSERVED
FINAL_RANK: FORBIDDEN
NEXT_GATE: CP1_CANONICALIZATION + CP2_BASELINE_ORACLE
```
