# Physics Boundary Audit — Role 1

## 1. System identity

GeoSync is a verification-first quantitative research platform with a CME governance layer and an MFN dependency-light gateway. Its valid transformation is:

```text
research intent + repo context + data/config state
  -> constrained operator
  -> schema-bound artifact / rejected claim / handoff
  -> validation evidence
```

The system boundary is not prestige language. The boundary is the set of files, schemas, tests, commands, and artifacts that can reject invalid states.

## 2. State model

| State variable | Definition | Status |
| --- | --- | --- |
| `intent_state` | One compressed iteration goal and first missing condition. | S0_REPO_FACT |
| `context_state` | Canonical repository surfaces used as operation boundary. | S0_REPO_FACT |
| `candidate_state` | Agent-generated plan, patch, or hypothesis before verifier approval. | S5_PROXY |
| `claim_state` | Claim text plus tier, evidence pointer, and falsifier. | S0_REPO_FACT |
| `evidence_state` | Artifact, raw logs, exit codes, schema result, hashes, replay command, manifest. | S0_REPO_FACT |
| `gate_state` | Pass/fail/reroute/blocking verifier state. | S0_REPO_FACT |
| `artifact_state` | JSON/markdown output with schema and replay contract. | S0_REPO_FACT |
| `verification_state` | Observed command result and gate evidence. | S5_PROXY |
| `release_state` | Release verdict plus evidence bundle. | S5_PROXY |

## 3. Boundary conditions

- No claim without tier, evidence pointer, falsifier, and replay path.
- Synthetic or placeholder artifacts cannot promote research status.
- Schema validity proves shape, not empirical truth.
- CME agent output remains residual until deterministic verification accepts it.
- Release status requires persisted evidence, not terminal mood.

## 4. Invariants

| Invariant | Conserved property | Failure if broken |
| --- | --- | --- |
| Intent coherence | One goal and one first missing condition per iteration. | Parallel agent chaos. |
| Claim status traceability | Every claim keeps tier and evidence boundary. | Hypothesis becomes fake promotion. |
| Source traceability | Artifacts cite files, schemas, and replay commands. | Audit cannot reproduce result. |
| Artifact reproducibility | Hashes, seed, timestamp, schema, and replay path persist. | Output becomes decorative. |
| Human responsibility | LLM proposes; verifier and human boundary decide. | LLM judge becomes false authority. |
| Proxy honesty | Proxy remains proxy. | Heuristic becomes fake measurement. |
| Validation evidence | PASS requires command and artifact evidence. | Green console line becomes mythology. |

## 5. Operator map

| Operator | Repo location | Decision |
| --- | --- | --- |
| ClaimBoundaryOperator | `FORBIDDEN_CLAIMS.md`; `scripts/ci/check_claim_boundary.py` | KEEP |
| ResearchGatewayOperator | `tools/research/research_cli.py` | KEEP |
| MFNGatewayOperator | `src/geosync/mfn/**`; `pyproject.toml` entrypoints | KEEP |
| CMEIterationContractOperator | `docs/CME_ITERATION_0001.json`; `tools/research/validate_cme_iteration_contract.py` | KEEP |
| ReleaseEvidenceOperator | `tools/release_evidence_harness.py` | MODIFY |
| PhysicsBoundaryAuditOperator | `docs/PHYSICS_BOUNDARY_AUDIT.md`; `data/physics_boundary_report.json` | CREATE |
| TrajectoryTraceOperator | missing trace schema/tool/test | CREATE |

## 6. Mechanism vs residual

Deterministic mechanisms:

- JSON schemas
- pytest gates
- console entrypoints
- Makefile test/lint targets
- claim-boundary scripts
- research artifact validator
- release evidence harness
- CME iteration contract validator

Residual spaces:

- candidate patches
- critiques
- architecture alternatives
- risk discovery
- compression variants
- hypothesis expansion

Promotion rule:

```text
residual -> verifier -> schema/test/command evidence -> claim tier check -> artifact
```

Anything else is vibes with version control. Humanity has enough of that.

## 7. Trajectory trace

Required trace fields:

```text
trace_id
state_t
operation_t
candidate_t
score_t
decision_t
artifact_delta_t
rollback_condition_t
state_t_plus_1
```

Current support: **PARTIAL**.

Missing condition: these fields are named as required but are not yet persisted as a schema-valid trajectory artifact.

## 8. Measurement model

| Metric | Status |
| --- | --- |
| intent_coherence_score | PROXY |
| constraint_satisfaction_rate | PROXY |
| operator_coverage_rate | PROXY |
| verification_pass_rate | MISSING |
| claim_safety_rate | PROXY |
| artifact_stability_score | MISSING |
| rollback_rate | MISSING |
| human_gate_load | MISSING |
| latency_drag | MISSING |
| source_coverage_rate | PROXY |
| release_readiness_score | PROXY |

## 9. Verification model

| Verifier | Command/file | Current status |
| --- | --- | --- |
| Physics boundary report schema test | `python -m pytest tests/test_physics_boundary_report_schema.py -q` | UNKNOWN |
| Full pytest | `python -m pytest -q` | UNKNOWN |
| Ruff | `ruff check .` | UNKNOWN |
| CME bibliography verifier | `python -m cme.cli bibliography validate \|\| true` | MISSING |
| CME verdict verifier | `python -m cme.cli verdict . \|\| true` | MISSING |
| Research CLI verifier | `geosync-research verify <artifact>` | UNKNOWN |
| MFN bundle verifier | `mfn validate --bundle <path>` | UNKNOWN |
| Claim status verifier | `scripts/ci/check_claim_boundary.py` | UNKNOWN |
| Release evidence verifier | `python tools/release_evidence_harness.py --verify-manifest artifacts/evidence_bundle/manifest.json` | UNKNOWN |

## 10. Claim audit

Repo facts:

- GeoSync is documented as verification-first quantitative research infrastructure.
- The README blocks trading-bot, alpha-product, and physical-law proof interpretations.
- `pyproject.toml` exposes `geosync-research`, `mfn`, `mfn-api`, and `mfn-validate`.
- `AGENTS.md` requires tier, evidence, artifact, schema, replay, and release evidence.
- `CLAIMS.md` contains active and retired claims.
- `FORBIDDEN_CLAIMS.md` contains claim firewall and promotion invariants.

Unsupported or incomplete:

- `python -m cme.cli ...` is requested but no `cme` package or entrypoint was detected.
- Full trajectory tracing is not persisted.
- CME benchmark/ablation metrics are not computed.
- Role 1 validation commands were not executed in this connector session.

Forbidden unblocked claims detected: **none**.

## 11. Quality score

| Category | Score |
| --- | ---: |
| state_model | 6 |
| constraint_model | 8 |
| operator_model | 6 |
| mechanism_residual_split | 6 |
| trajectory_trace | 3 |
| measurement_model | 4 |
| verification_model | 6 |
| claim_governance | 8 |
| github_agent_readiness | 7 |
| **total** | **54/90** |

## 12. First missing condition

A persisted CME trajectory trace contract is missing, so the system can audit final artifacts but cannot yet verify the full state transformation path.

## 13. Role 2 handoff

Role 2: `TRAJECTORY_TRACE_IMPLEMENTER`.

Task:

Create a schema, recorder, example artifact, and pytest gate for:

```text
trace_id
state_t
operation_t
candidate_t
score_t
decision_t
artifact_delta_t
rollback_condition_t
state_t_plus_1
```

Files to create:

```text
schemas/cme_trajectory_trace.schema.json
data/cme_trajectory_trace_example.json
tools/research/record_cme_trajectory_trace.py
tests/test_cme_trajectory_trace_schema.py
```

Files to modify:

```text
docs/CME_PHYSICS_RND_LOOP.md
VERDICT.md
```

Validation commands:

```bash
python -m pytest tests/test_cme_trajectory_trace_schema.py -q
python tools/research/record_cme_trajectory_trace.py --example data/cme_trajectory_trace_example.json
python -m pytest -q
ruff check .
```

## 14. Verdict

**FAIL.**

Reason:

The repository has strong claim governance and partial machine-checkable contracts, but it lacks a persisted trajectory trace. Without that trace, CME can validate final artifacts but cannot yet verify the full process transformation:

```text
x_t -> O_i(x_t) -> x_t+1
```

This is an engineering blocker, not a philosophical tragedy, though humans do enjoy turning missing JSON into metaphysics.
