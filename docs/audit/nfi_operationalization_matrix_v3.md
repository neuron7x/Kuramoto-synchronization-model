# NFI Operationalization Matrix v3

Status: EXECUTION_MATRIX
Scope: GeoSync physics validation lane first. BN-Syn and MFN+ remain external extension lanes until their source trees or immutable commits are attached to this validation scope.
Parent protocol: `docs/audit/nfi_physics_validation_protocol_v3.md`

## 1. Executive operating rule

The abstract need is converted into a gated execution system:

```text
claim -> evidence carrier -> owner role -> file patch -> test -> metric -> checkpoint -> PASS/FAIL artifact
```

No task is complete because a document exists. A task is complete only when the declared artifact is produced, the metric is machine-readable, and the gate has an explicit failure condition.

## 2. Role map

| role_id | role | authority | owns | cannot approve |
|---|---|---|---|---|
| R0 | Research Owner | final scope and rank target | target score, blocker priority, final verdict | own unmeasured score |
| R1 | Physics Formalizer | canonical mathematical object | equations, variables, units, invalid claims | CI result |
| R2 | Numerical Verifier | solver correctness | convergence, stability, invariants | model marketing claims |
| R3 | Scientific Software Architect | repo implementation | code paths, schemas, test layout | physical truth claim |
| R4 | Reproducibility Engineer | rerun evidence | manifests, artifacts, command surface | unverifiable manual result |
| R5 | Falsification Designer | null models and H0/H1 | null matrix, rejection rules, failure modes | positive demo without nulls |
| R6 | Adversarial Critic | stop conditions | contradiction ledger, review notes | roadmap optimism |
| R7 | CI Gatekeeper | merge readiness | pytest jobs, generated artifacts, branch protection | scientific interpretation |

## 3. Resource inventory

| resource_id | resource | required for | owner | readiness condition |
|---|---|---|---|---|
| RES-001 | `docs/audit/file_inventory.md` | physics file discovery | R3 | every physics-relevant file classified |
| RES-002 | `docs/audit/claim_ledger.md` | claim-to-evidence mapping | R6 | every claim has status and required action |
| RES-003 | `docs/physics/geosync_core.md` | canonical Kuramoto object | R1 | one equation set, variables, units, observables, failure modes |
| RES-004 | `docs/physics/ricci_experimental.md` | Ricci quarantine | R1/R6 | no canonical mixing without bridge proof |
| RES-005 | `schemas/physics_metrics.schema.json` | score artifact validation | R3 | JSON schema validates baseline and final score |
| RES-006 | `tools/physics_score.py` | computed S_total | R3/R4 | score generated from artifacts, not edited by hand |
| RES-007 | `tests/physics/test_geosync_nulls.py` | falsification | R5 | K=0, phase shuffle, ER graph, omega randomization tested |
| RES-008 | `tests/physics/test_invariants.py` | invariant preservation | R2 | R bounds, finite theta, finite-size baseline checked |
| RES-009 | `tests/physics/test_convergence.py` | numerical convergence | R2 | dt/dt2/dt4 comparison produces expected tolerance result |
| RES-010 | `tests/physics/test_interface_contracts.py` | boundary contracts | R3/R7 | shape, unit, range, sampling checks pass |
| RES-011 | `docs/physics/uq_plan.md` | uncertainty qualification | R4/R5 | prior/noise/IC/tolerance uncertainty source declared |
| RES-012 | `reproducibility/manifest.json` | reproducibility | R4 | commit, command, seed, environment, artifacts recorded |
| RES-013 | `VERDICT.md` | final decision | R0/R7 | generated from score output and blocker register |

## 4. Phase execution matrix

| phase | action sequence | responsible | resources | metric | checkpoint | stop condition |
|---:|---|---|---|---|---|---|
| 0 | discover physics files -> classify docs/code/tests/artifacts -> write inventory | R3 | RES-001 | classification coverage = classified / discovered | all discovered files classified | unknown file with physics claim |
| 0 | extract README/docs/comment claims -> map to equation/code/test/metric/baseline/citation/failure | R6 | RES-002 | evidence coverage = claims_with_evidence / total_claims | no claim lacks evidence class | claim has no carrier and is not marked NOISE |
| 1 | select Pure Graph Kuramoto as canonical -> quarantine Ricci modulation | R1/R6 | RES-003, RES-004 | canonical_object_count = 1 | no mixed canonical object | Ricci-Kuramoto bridge only rhetorical |
| 2 | define metrics schema -> implement score tool -> generate S0 baseline | R3/R4 | RES-005, RES-006 | S_total computable, weights sum = 1.0 | `baseline_score.json` exists | score manually estimated |
| 3 | implement null models -> define H0/H1 -> enforce rejection/failure rules | R5 | RES-007 | null_pass_rate, false_sync_rate | nulls do not produce positive physics | K=0 or shuffled phases fake synchrony |
| 4 | add invariants -> add convergence -> add stability bounds | R2 | RES-008, RES-009 | invariant_pass_rate, convergence_error_ratio | no silent NaN/Inf or invalid R | solver fabricates physics |
| 5 | define interface contracts -> test shape/units/range/sampling | R3/R7 | RES-010 | contract_pass_rate | no hidden conversion between layers | consumer accepts untyped output |
| 6 | define stochastic source -> run solo-feasible UQ smoke | R4/R5 | RES-011 | uq_source_declared, sensitivity_summary_exists | UQ only where uncertainty exists | Monte Carlo without prior/noise/IC/tolerance model |
| 7 | generate manifest -> compute S1 -> write final verdict | R0/R4/R7 | RES-012, RES-013 | S1 - S0, blocker_count | PASS/FAIL artifact committed | VERDICT written without score tool output |

## 5. Metrics contract

| metric_id | formula | target | artifact | owner | failure mode |
|---|---|---:|---|---|---|
| M001 | classified_files / discovered_physics_files | 1.00 | `file_inventory.md` | R3 | unclassified physics file |
| M002 | claims_with_evidence_or_noise / total_claims | 1.00 | `claim_ledger.md` | R6 | unsupported claim survives |
| M003 | canonical_objects_per_subsystem | 1 | `geosync_core.md` | R1 | mixed abstraction level |
| M004 | sum(score_weights) | 1.00 | `metrics_schema.json` | R3 | invalid scoring oracle |
| M005 | generated_score_artifact_exists | 1 | `baseline_score.json` | R4 | score not reproducible |
| M006 | passed_null_tests / required_null_tests | >= 0.95 | pytest report | R5 | null regime produces target signal |
| M007 | passed_invariants / total_invariants | >= 0.95 | pytest report | R2 | R outside [0,1] or non-finite theta |
| M008 | observed_convergence_order >= documented_order_min | true | numerical report | R2 | dt refinement not reducing error |
| M009 | passed_contract_tests / total_contract_tests | >= 0.90 | pytest report | R7 | hidden unit/shape conversion |
| M010 | uq_sources_declared / uq_sources_used | 1.00 | `uq_summary.json` | R4 | fake confidence interval |
| M011 | manifest_fields_present / required_manifest_fields | 1.00 | `manifest.json` | R4 | artifact cannot be rerun |
| M012 | S_total in target interval | 88-92 | `VERDICT.md` | R0 | target claimed without computed score |

## 6. Control checkpoints

| checkpoint | required inputs | decision | pass output | fail output |
|---|---|---|---|---|
| CP0 Observation Gate | file inventory, claim ledger | continue to canonicalization? | Phase 1 unlocked | blocker list |
| CP1 Canonical Gate | GeoSync core, Ricci quarantine | one mathematical object? | Phase 2 unlocked | canonical conflict issue |
| CP2 Baseline Gate | schema, score tool, S0 artifact | score computable? | Phase 3 unlocked | BLOCKED_FOR_BASELINE |
| CP3 Falsification Gate | null tests, H0/H1 register | positive signal survives nulls? | Phase 4 unlocked | MODEL_ARTIFACT_DETECTED |
| CP4 Numerical Gate | invariants, convergence, stability | solver trustworthy? | Phase 5 unlocked | NUMERICAL_INVALIDITY |
| CP5 Interface Gate | contracts and tests | vertical boundary safe? | Phase 6 unlocked | INTERFACE_UNSAFE |
| CP6 UQ Gate | stochastic source and UQ smoke | uncertainty legitimate? | Phase 7 unlocked | UQ_INVALID |
| CP7 Verdict Gate | S0, S1, manifest, blockers | rank claim allowed? | PASS/FAIL verdict | NO_RANK_CLAIM_ALLOWED |

## 7. Execution order by information gain

| rank | task | command surface | expected output | runtime budget | reason |
|---:|---|---|---|---|---|
| 1 | create file inventory | script or manual repo scan | `file_inventory.md` | minutes | exposes real surface area |
| 2 | create claim ledger | claim compiler | `claim_ledger.md/json` | minutes | deletes unsupported language early |
| 3 | write canonical GeoSync core | markdown + contract test | `geosync_core.md` | minutes | prevents Ricci/Kuramoto soup |
| 4 | implement score schema/tool | Python + pytest | `baseline_score.json` | <1h | turns rank into computation |
| 5 | implement null tests | pytest | null test report | <1h | gives model the right to fail |
| 6 | implement invariants/convergence | pytest | numerical report | <2h | detects solver-created physics |
| 7 | implement interface/UQ gates | docs + pytest | contracts + UQ summary | <1h | blocks hidden cross-system fantasy |
| 8 | generate verdict/manifest | score tool | `VERDICT.md`, manifest | minutes | only valid after evidence |

## 8. Daily operator loop

```text
1. pick highest-ranked unlocked task
2. patch only declared files
3. run only task-local tests first
4. run physics validation subset
5. update artifact and blocker register
6. stop at first violated checkpoint
7. never advance phase with unknown metric
```

## 9. Definition of done

A phase is done when all are true:

- artifact exists in the declared path
- artifact has schema or deterministic structure
- at least one test targets the artifact or its generated output
- metric is computed or explicitly marked BLOCKED
- failure condition is written before the positive claim
- checkpoint decision is PASS or BLOCKED, never vibes

## 10. Merge policy

This PR remains draft until CP2 Baseline Gate passes. It may become ready for review after:

- `docs/audit/file_inventory.md` exists
- `docs/audit/claim_ledger.md` exists
- `schemas/physics_metrics.schema.json` exists
- `tools/physics_score.py` computes S0
- `artifacts/physics_validation/baseline_score.json` is generated or generation path is documented

It cannot claim physical rank until CP7 Verdict Gate passes.
