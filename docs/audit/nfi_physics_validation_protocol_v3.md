# NFI Physics Validation Protocol v3

Status: EXECUTION_PROTOCOL
Scope: GeoSync first, with explicit extension gates for BN-Syn and MFN+ only after their source trees are present in the same validation lane.
Rule: no physics-rank claim is allowed without an equation, code path, test, metric, baseline value, citation, and failure condition.

## Executive verdict

Current status: BLOCKED_FOR_BASELINE.
Current computed score S0: NOT_COMPUTED.
Target score: 88-92 after machine-computed scoring, not human estimation.
Can target be reached now: NO.
Main reason: the repository has Kuramoto theory and Ricci configuration surfaces, but no observed executable scoring oracle, baseline score artifact, claim ledger, null model matrix, or falsification gate in the inspected paths.

## Observed anchors

- `.claude/physics/KURAMOTO_THEORY.md` defines the canonical Kuramoto equation, order parameter, critical coupling, finite-size scaling, and falsification constraints.
- `core/config/kuramoto_ricci.py` exposes structured Kuramoto, Ricci, and composite threshold configuration.
- Search surfaced Ricci code and docs under `core/physics/forman_ricci.py`, `src/geosync/features/ricci.py`, and several research notes.
- This is enough for Phase 0 and Phase 1 planning, not enough for final physical rank.

## Baseline table

| metric | subsystem | current_value | target | measurement_fn | status |
|---|---:|---:|---:|---|---|
| S_math_object | GeoSync | unknown | >= 0.90 | `tools/physics_score.py::score_math_object` | BLOCKED |
| S_dimensional_consistency | GeoSync | unknown | >= 0.90 | `tools/physics_score.py::score_units` | BLOCKED |
| S_numerical_stability | GeoSync | unknown | >= 0.85 | `tools/physics_score.py::score_stability` | BLOCKED |
| S_invariant_preservation | GeoSync | unknown | >= 0.95 | `tools/physics_score.py::score_invariants` | BLOCKED |
| S_falsifiability | GeoSync | unknown | >= 0.90 | `tools/physics_score.py::score_falsification` | BLOCKED |
| S_baseline_models | GeoSync | unknown | >= 0.85 | `tools/physics_score.py::score_nulls` | BLOCKED |
| S_UQ | GeoSync | unknown | >= 0.75 | `tools/physics_score.py::score_uq` | BLOCKED |
| S_reproducibility | GeoSync | unknown | >= 0.90 | `tools/physics_score.py::score_reproducibility` | BLOCKED |
| S_interface_contracts | GeoSync | unknown | >= 0.90 | `tools/physics_score.py::score_interfaces` | BLOCKED |
| S_traceability | GeoSync | unknown | >= 0.90 | `tools/physics_score.py::score_traceability` | BLOCKED |

## Fatal gaps

| gap_id | subsystem | severity | root_cause | evidence | patch | test |
|---|---|---:|---|---|---|---|
| GAP-GEO-001 | GeoSync | P0 | no machine-computed S0 found | protocol requires score before rank | add `tools/physics_score.py` and schema | `tests/physics/test_physics_score.py` |
| GAP-GEO-002 | GeoSync | P0 | claims are not compiled into evidence ledger | docs/code claims can drift | add claim compiler output | `tests/physics/test_claim_ledger_schema.py` |
| GAP-GEO-003 | GeoSync | P0 | Ricci-Kuramoto bridge not yet selected as canonical or experimental | Ricci config exists separately from Kuramoto theory | create canonical selector doc | `tests/physics/test_canonical_object_contracts.py` |
| GAP-GEO-004 | GeoSync | P0 | null models not yet enforced as a gate | no visible `test_*_nulls.py` from search | implement null matrix | `tests/physics/test_geosync_nulls.py` |
| GAP-GEO-005 | GeoSync | P0 | convergence/stability not tied to score | theory doc states invariants, scoring not observed | implement convergence and invariant scoring | `tests/physics/test_convergence.py` |

## Canonical mathematical core

### GeoSync

Chosen object: Pure Graph Kuramoto as canonical core.

Equation:

```text
dtheta_i/dt = omega_i + K * sum_j A_ij * sin(theta_j - theta_i)
Z(t) = R(t) * exp(i * psi(t)) = (1/N) * sum_j exp(i * theta_j(t))
R(t) = abs(Z(t)), 0 <= R <= 1
```

State variables:

- `theta_i`: phase, radians
- `omega_i`: natural frequency, radians per time unit
- `A_ij`: dimensionless adjacency/coupling weight
- `K`: coupling scale, inverse time unit if `A_ij` is dimensionless

Observables:

- `R(t)`: phase coherence, dimensionless
- `psi(t)`: mean phase, radians
- finite-size incoherent baseline: `R ~ O(1/sqrt(N))`
- transition behavior around `K_c`

Invalid or experimental claims removed from canonical core:

- Ricci-modulated Kuramoto until `kappa_ij(t)`, `f(kappa)`, boundedness of `A_ij(t)`, and numerical well-posedness are defined.
- market alpha/trading edge claims until benchmarked against null and naive baselines.

Failure conditions:

- `R < 0` or `R > 1`
- `theta` non-finite
- `K = 0` produces persistent high synchrony beyond finite-size baseline
- subcritical `K` produces strong synchronization in large `N`
- score assigned manually

### BN-Syn

Chosen object: BLOCKED in this repository lane unless BN-Syn source is included or linked by immutable commit.
Required canonical object: AdEx + conductance-based synapses + Q10 temperature correction.
Invalid claim: Boltzmann gating inside AdEx without HH-level channel dynamics.
Failure condition: no source tree, no equation traceability, no solver integrity test.

### MFN+

Chosen object: BLOCKED in this repository lane unless MFN+ source is included or linked by immutable commit.
Required canonical object: two-component reaction-diffusion PDE.

```text
partial_t u = D_u * Laplacian(u) + f(u, v)
partial_t v = D_v * Laplacian(v) + g(u, v)
```

Failure condition: missing explicit `f(u,v)`, `g(u,v)`, boundary conditions, or stability bound.

## Scoring oracle

Weights sum to 1.0.

| S_i | weight | metric | formula | measurement_fn | threshold | baseline | target | uncertainty | failure_condition |
|---|---:|---|---|---|---:|---:|---:|---|---|
| S_math_object | 0.12 | canonical object completeness | passed_fields / required_fields | `score_math_object` | 0.80 | unknown | 0.95 | none | missing equation |
| S_dimensional_consistency | 0.10 | unit homogeneity | passed_equations / total_equations | `score_units` | 0.80 | unknown | 0.90 | none | unit mismatch |
| S_numerical_stability | 0.12 | finite stable solver outputs | passed_cases / total_cases | `score_stability` | 0.85 | unknown | 0.90 | tolerance model | NaN/Inf/silent instability |
| S_invariant_preservation | 0.12 | invariant pass ratio | passed_invariants / total_invariants | `score_invariants` | 0.90 | unknown | 0.95 | stochastic finite-size | R outside [0,1] |
| S_falsifiability | 0.12 | hypotheses with H0/H1/tests | tested_hypotheses / total_hypotheses | `score_falsification` | 0.80 | unknown | 0.90 | alpha declared | no rejection rule |
| S_baseline_models | 0.10 | null model coverage | passed_nulls / required_nulls | `score_nulls` | 0.80 | unknown | 0.85 | finite ensemble | null produces positive signal |
| S_UQ | 0.08 | uncertainty source and sensitivity | completed_uq_items / required_uq_items | `score_uq` | 0.60 | unknown | 0.75 | declared prior | MC without stochastic source |
| S_reproducibility | 0.10 | deterministic rerun + manifest | passed_repro_checks / total | `score_reproducibility` | 0.85 | unknown | 0.90 | platform notes | non-reproducible artifact |
| S_interface_contracts | 0.08 | shape/unit/range contract tests | passed_contracts / total | `score_interfaces` | 0.85 | unknown | 0.90 | none | hidden conversion |
| S_traceability | 0.06 | equation-to-code mapping | traced_equations / total_equations | `score_traceability` | 0.80 | unknown | 0.90 | none | equation without code/test |

## Null model matrix

| null_id | subsystem | H0 | H1 | observable | expected_behavior | test_file |
|---|---|---|---|---|---|---|
| GEO-NULL-K0 | GeoSync | independent oscillators | coupling creates synchrony | `R(t)` | `R ~ O(1/sqrt(N))` | `tests/physics/test_geosync_nulls.py` |
| GEO-NULL-PHASE-SHUFFLE | GeoSync | shuffled phases destroy structure | true phase structure survives | `R`, circular stats | no persistent high R | `tests/physics/test_geosync_nulls.py` |
| GEO-NULL-ER-GRAPH | GeoSync | matched random graph explains signal | topology-specific coupling matters | `R`, transition curve | no superior structure | `tests/physics/test_geosync_nulls.py` |
| GEO-NULL-OMEGA-RANDOM | GeoSync | randomized frequencies explain signal | measured frequencies matter | `R`, lock fraction | reduced/unstable signal | `tests/physics/test_geosync_nulls.py` |
| GEO-NULL-CONSTANT-PHASE | GeoSync | constant phase artifact fakes sync | model detects artifact | `R`, variance | flagged as artifact | `tests/physics/test_geosync_nulls.py` |

## Patch plan

| phase | file_to_create_or_modify | exact_change | test | acceptance_gate |
|---|---|---|---|---|
| 0 | `docs/audit/file_inventory.md` | list physics-relevant files and status | schema smoke | all entries classified |
| 0 | `docs/audit/claim_ledger.md` | claim-to-evidence ledger | `test_claim_ledger_schema.py` | no claim without evidence class |
| 1 | `docs/physics/geosync_core.md` | lock Pure Graph Kuramoto as canonical | `test_canonical_object_contracts.py` | one canonical object |
| 1 | `docs/physics/ricci_experimental.md` | mark Ricci modulation experimental until bridge proof | `test_canonical_object_contracts.py` | no hidden canonical mixing |
| 2 | `schemas/physics_metrics.schema.json` | define scoring artifact schema | `test_physics_score.py` | schema validates |
| 2 | `tools/physics_score.py` | compute S_total from JSON inputs | `test_physics_score.py` | score not manually editable |
| 3 | `tests/physics/test_geosync_nulls.py` | implement K=0, phase shuffle, ER graph nulls | pytest | nulls fail false physics |
| 4 | `tests/physics/test_convergence.py` | dt/dt2/dt4 convergence | pytest | expected order documented |
| 4 | `tests/physics/test_invariants.py` | R bounds, finite theta, finite-size scaling | pytest | no invariant breach |
| 5 | `docs/physics/interface_contracts.md` | define input/output units/shapes | `test_interface_contracts.py` | no hidden conversion |
| 6 | `docs/physics/uq_plan.md` | declare stochastic source before UQ | `test_uq_smoke.py` | no fake Monte Carlo |
| 7 | `VERDICT.md` | final score + blockers + manifest link | generated by score tool | PASS/FAIL reproducible |

## Solo-operator execution plan

| rank | task | why first | runtime_budget | output |
|---:|---|---|---|---|
| 1 | Generate file inventory | highest information gain | minutes | `docs/audit/file_inventory.md` |
| 2 | Compile claim ledger | kills decorative claims early | minutes | `docs/audit/claim_ledger.md` |
| 3 | Lock canonical Kuramoto core | prevents mixed-object physics soup | minutes | `docs/physics/geosync_core.md` |
| 4 | Implement score schema/tool | score becomes computable | < 1 hour | `baseline_score.json` |
| 5 | Add null models | first falsification gate | < 1 hour | null tests |
| 6 | Add invariant/convergence tests | prevents numerical hallucination | < 2 hours | numerical report |
| 7 | Add interface/UQ gates | prevents cross-system fantasy | < 1 hour | interface and UQ docs/tests |
| 8 | Generate final verdict | only after measurements | minutes | `VERDICT.md` |

## Final acceptance gate

The repository reaches 88-92 only if:

- [ ] baseline exists
- [ ] scoring oracle computes `S_total`
- [ ] canonical mathematical objects fixed
- [ ] null models implemented
- [ ] falsifier tests implemented
- [ ] convergence tests pass
- [ ] invariant tests pass
- [ ] interface contracts pass
- [ ] UQ has stochastic source
- [ ] independent replication passes
- [ ] `VERDICT.md` generated
- [ ] `S_total in [88, 92]`

## Do not proceed conditions

Stop immediately if:

- no baseline
- no explicit equations
- no falsification condition
- Ricci and Kuramoto are coupled only rhetorically
- Monte Carlo is requested without prior/noise/IC distribution/tolerance uncertainty
- score is manually estimated
- test passes without a failure condition

Final rule: a model that cannot be falsified is not a model; a score that cannot be computed is not a score; a roadmap without tests is motivational garbage with folders.
