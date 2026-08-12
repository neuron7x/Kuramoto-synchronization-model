# X10R Curvature-Synchronization Free-Energy Reconstruction Capsule

**Repository:** `neuron7xLab/GeoSync`  
**Base commit:** `196063b36512ba55048d3f49d08224c2c316ab16`  
**Date:** 2026-06-17  
**Status:** `EXECUTION_CONTRACT_READY / NOT_CI_VERIFIED_IN_THIS_COMMIT`  

This capsule turns the physics decomposition into an executable research contract. It is deliberately not a trading claim, alpha claim, AGI claim, or proof that markets obey universal physics. It is a verification-first reconstruction lane for falsifiable market-structure hypotheses using graph geometry, nonlinear synchronization, thermodynamic-style objectives, neuro-symbolic control, and fail-closed governance.

## 1. Claim Boundary

GeoSync may claim only the following after this capsule is executed and CI evidence is attached:

```text
A reproducible software pipeline can construct market-derived graphs, compute topology/curvature/synchronization/energy observables, enforce explicit invariants, and reject corrupted or unsupported states through executable falsifiers.
```

GeoSync must not claim:

- profitable trading edge;
- universal market physics;
- biological realism beyond explicit neuro-control analogues;
- production readiness without CI, artifact hashes, and negative-evidence ledger entries.

## 2. First-Principles Source Map

| Layer | Repository boundary | Required invariant |
| --- | --- | --- |
| Topological geometry | `core/indicators/gauss_bonnet.py`, `physics_contracts/catalog.yaml`, `tests/physics_contracts/` | Exact `Σ K(x) - χ(G) == 0` over rationals for finite simple undirected graphs |
| Curvature stress | `core/indicators/ricci.py`, `core/physics/forman_ricci.py` | Curvature bounds and margin escalation are policy gates, not universal physical constants |
| Kuramoto synchronization | `core/kuramoto/`, `core/indicators/multiscale_kuramoto.py`, `core/config/kuramoto_ricci.py` | Canonical ownership of scale: `θ_dot = ω + K * A_norm * sin(Δθ)`, reject negative coupling |
| Energy ontology | `core/energy.py`, `core/physics/`, `tests/physics/test_energy_contract.py` | Do not conflate `operational_cost_energy` with canonical `thermo_free_energy = U - T*S` |
| Neuro-control | `core/neuro/`, `tests/physics_contracts/`, contradiction ledger | Neuromodulatory trajectories must expose falsifiable correlation and boundedness witnesses |
| Governance | `governance/verification_protocol.py`, `data/governance/`, `.claude/commit_acceptors/` | Weighted score, conformance bands, and weakest-link clamp execute from declared artifacts |
| Provenance | `artifacts/`, `docs/audit/`, `data/audit/` | Residuals, reports, and evidence must be hash-pinned and reproducible |

## 3. Reconstruction Objective

Implement **First-Principles Reconstruction of Market Curvature-Synchronization Free-Energy Landscape with Topological Integrity Enforcement**.

The pipeline must produce a verifiable X10R artifact bundle:

```text
artifacts/x10r_reconstruction/
  manifest.json
  input_graph.json
  curvature_edges.json
  gauss_bonnet_residuals.json
  kuramoto_trajectory.json
  free_energy_landscape.json
  neuro_control_trace.json
  falsifiers.json
  verdict.json
  ro_crate_metadata.json
```

The final verdict is valid only if all blocking gates pass, every generated artifact is SHA-256 pinned in `manifest.json`, AND every emitted `*.json` validates against `schemas/research/research_inference_artifact.schema.json` with all canonical provenance fields present. Hash-pinning proves immutability; schema validation proves conformance. Both are blocking — neither substitutes for the other.

## 4. Execution Lanes

### Lane A: Input Graph Construction

- Accept synthetic or empirical market microstructure input.
- Build a finite simple undirected weighted graph.
- Reject directed graphs, self-loops, multigraphs, empty graphs, non-finite weights, and invalid timestamps.
- Normalize adjacency with zero diagonal and one declared scale owner.
- Derive natural frequencies `ω_i` from returns, volatility, or explicitly declared synthetic fixtures.

### Lane B: Curvature and Topological Integrity

- Compute Forman-Ricci and Ollivier-Ricci observables where valid.
- Compute Knill vertex curvature through exact rational arithmetic.
- Assert `gauss_bonnet_residual(graph) == 0`.
- Run inverse falsifier: tamper one vertex curvature value and require fail-closed rejection.

### Lane C: Curved-Manifold Kuramoto Dynamics

- Integrate `θ_dot = ω + K * Σ_j A_norm[i,j] * sin(θ_j - θ_i)`.
- Reject `K < 0`, non-finite phase vectors, and mismatched graph/phase dimensions.
- Track `R(t) = |mean(exp(iθ))|` and verify `0 <= R(t) <= 1`.
- Add curvature feedback only as an explicit optional operator, never by silently rescaling `K` twice.

### Lane D: Free-Energy Landscape

- Compute canonical `F = U - T*S` separately from operational cost.
- Assert unit ontology: canonical physics quantity and dimensionless operational-cost objective are not interchangeable.
- Verify boundedness of all declared state variables.
- Run sign falsifier: increasing entropy must decrease canonical free energy when `T > 0`, while it must not lower the operational entropy-penalty objective.

### Lane E: Neuro-Symbolic Control

- Emit dopamine/serotonin or declared neuromodulatory control traces only as operational control analogues.
- Enforce bounded signals and declared correlation invariant.
- Fail on positive or flat correlation where the contract requires inverse relation.
- Write all contradictions or failed witnesses into the negative-evidence ledger.

### Lane F: Governance and Provenance

- Execute `VerificationProtocol` from the declared kernel, not copied constants.
- Apply weakest-link clamp: a high numerical score cannot promote an artifact above missing evidence.
- Emit RO-Crate-compatible metadata for code commit, input fixtures, command lines, outputs, and hashes.
- Produce a final verdict: `PASS`, `FAIL`, or `BLOCKED_BY_MISSING_EVIDENCE`.

## 5. Acceptance Gates

A commit can call this capsule complete only when:

1. `gauss_bonnet_residuals.json` reports exact rational zero for all valid graph families.
2. The tampered-curvature falsifier fails closed.
3. Kuramoto trajectories are deterministic under fixed seed and golden reference tolerance.
4. `R(t)` remains in `[0, 1]` for every emitted step.
5. Negative coupling is rejected before integration.
6. Canonical free energy and operational-cost energy are verified as separate functions with opposite entropy semantics.
7. Neuro-control invariants produce both positive witnesses and inverse falsifiers.
8. Governance verdict is produced through `VerificationProtocol.evaluate`.
9. Manifest includes SHA-256 for every output artifact.
10. Every emitted `artifacts/x10r_reconstruction/*.json` validates against `schemas/research/research_inference_artifact.schema.json` AND carries all canonical provenance fields — `run_id`, `git_sha`, `data_sha256`, `config_sha256`, `seed`, `decision`, `claim_tier`, `falsification_status`. Schema validation is a BLOCKING acceptance condition (repo artifact contract, README Stage 4 "Artifact / Evidence"): a hash-pinned but schema-invalid or canonical-field-incomplete artifact fails closed and CANNOT promote evidence. A SHA-256 alone proves immutability, not conformance — both are required.
11. CI evidence is attached; otherwise the maximum honest state is `BLOCKED_BY_MISSING_EVIDENCE`.

## 6. Minimal Command Contract

The target implementation should converge to a single local command:

```bash
python -m research.reconstruction.x10r_reconstruct \
  --input fixtures/x10r/market_microstructure.json \
  --out artifacts/x10r_reconstruction \
  --seed 1729 \
  --strict
```

Expected terminal terminal state:

```text
X10R_RECONSTRUCTION: PASS|FAIL|BLOCKED_BY_MISSING_EVIDENCE
manifest: artifacts/x10r_reconstruction/manifest.json
verdict: artifacts/x10r_reconstruction/verdict.json
```

## 7. Stop Rules

Stop immediately and mark the capsule failed if:

- topology is outside finite simple undirected graph domain;
- any exact topological residual is non-zero;
- any physics contract is missing a witness;
- any artifact lacks a hash;
- any emitted artifact fails schema validation against `schemas/research/research_inference_artifact.schema.json` or omits a canonical provenance field (`run_id`, `git_sha`, `data_sha256`, `config_sha256`, `seed`, `decision`, `claim_tier`, `falsification_status`);
- any governance score bypasses weakest-link clamp;
- any market/trading claim is emitted from this pipeline.

## 8. Integrated Operational Decision Model

This section connects symptoms, data, context, constraints, and roles into one execution model. Its purpose is to prevent the reconstruction lane from degenerating into disconnected tests, isolated physics metaphors, or heroic narrative drift. Humans do love turning architecture into incense; this model is the exhaust fan.

### 8.1 Symptom Graph

| Symptom | Operational meaning | Required response |
| --- | --- | --- |
| Missing executable pipeline | The capsule is still a contract, not a reconstruction system | Implement `research.reconstruction.x10r_reconstruct` before any completion claim |
| Missing artifact hashes | Results are not reproducible evidence | Emit `manifest.json` with SHA-256 for every output |
| Missing CI evidence | Local or connector-only changes are not verified | Mark verdict `BLOCKED_BY_MISSING_EVIDENCE` |
| Non-zero Gauss-Bonnet residual | Topological integrity failed | Abort the run, emit failed residual witness |
| Invalid graph domain | Physics contract is being applied outside its declared domain | Reject before curvature, synchronization, or energy computation |
| Negative or double-owned coupling scale | Kuramoto dynamics are semantically corrupted | Reject negative `K`; enforce one explicit adjacency normalization owner |
| Energy-sign ambiguity | Canonical free energy and operational cost are being conflated | Run entropy-sign falsifier and fail on semantic collision |
| Neuro-control flat/positive correlation where inverse relation is required | Claimed control invariant is unsupported | Emit contradiction ledger entry and fail the neuro-control gate |

### 8.2 Data Spine

The run must preserve a single evidence spine:

```text
market_or_synthetic_input
  -> finite_simple_weighted_graph
  -> exact_topology_witnesses
  -> curvature_observables
  -> normalized_adjacency
  -> kuramoto_phase_trajectory
  -> synchronization_observables
  -> free_energy_and_operational_cost_landscape
  -> neuro_control_trace
  -> falsifier_results
  -> governance_verdict
  -> manifest_hashes
  -> ro_crate_metadata
```

No stage may silently repair or reinterpret upstream invalidity. If a predecessor stage fails, downstream stages must receive an explicit blocked state instead of fabricated defaults.

### 8.3 Context Model

The repository context is verification-first research infrastructure. Therefore every physics layer is treated as an executable hypothesis operator, not as market mysticism. The correct operating frame is:

```text
physics-inspired observable + declared domain + falsifier + hash-pinned artifact + governance verdict
```

The incorrect operating frame is:

```text
market data + physics vocabulary + attractive charts + implied trading edge
```

Completion is not measured by conceptual elegance. Completion is measured by executable invariants, failing inverse tests, reproducible artifacts, and an honest verdict.

### 8.4 Constraint Lattice

| Constraint class | Blocking rule |
| --- | --- |
| Domain constraints | Only finite simple undirected graphs may enter exact Gauss-Bonnet enforcement |
| Numerical constraints | Phases, frequencies, weights, energies, and trajectories must be finite |
| Semantic constraints | Policy thresholds must not be advertised as physical constants |
| Dynamical constraints | `R(t)` must remain bounded in `[0, 1]`; negative coupling must be rejected pre-integration |
| Thermodynamic constraints | `thermo_free_energy` and `operational_cost_energy` must remain separate contracts |
| Governance constraints | A missing witness clamps the verdict no matter how high the aggregate score is |
| Provenance constraints | An output without SHA-256 is not evidence |
| Claim constraints | The pipeline must not emit profitability, alpha, or universal-law claims |

### 8.5 Role Topology

| Role | Authority | Deliverable |
| --- | --- | --- |
| Physics owner | Defines valid observable domains and falsifiers | Curvature, synchronization, and energy contracts with inverse tests |
| Implementation owner | Converts the capsule into executable code | CLI module, fixtures, deterministic seeds, artifact writer |
| Verification owner | Blocks unsupported claims | Test suite, CI evidence, failed-state witnesses |
| Governance owner | Applies weakest-link evaluation | `verdict.json`, conformance bands, negative-evidence ledger |
| Provenance owner | Preserves reproducibility | `manifest.json`, hashes, RO-Crate metadata |
| Research operator | Reads the verdict without promotion bias | `PASS`, `FAIL`, or `BLOCKED_BY_MISSING_EVIDENCE` only |

A single human or agent may perform multiple roles, but the artifacts must remain role-separated. Role collapse without artifact separation is just multitasking wearing a lab coat.

### 8.6 Decision Automaton

```text
START
  -> validate_input_domain
    -> if invalid: FAIL_DOMAIN
  -> build_graph_and_hash_input
  -> compute_exact_topology
    -> if residual != 0: FAIL_TOPOLOGY
  -> compute_curvature_observables
  -> run_kuramoto_dynamics
    -> if K < 0 or R outside [0,1]: FAIL_DYNAMICS
  -> compute_energy_landscape
    -> if entropy signs collide: FAIL_ENERGY_ONTOLOGY
  -> compute_neuro_control_trace
    -> if required inverse witness missing: FAIL_NEURO_CONTROL
  -> run_inverse_falsifiers
    -> if falsifiers do not fire: FAIL_FALSIFIABILITY
  -> write_artifacts_and_hashes
    -> if any hash missing: FAIL_PROVENANCE
  -> evaluate_governance
    -> if any required witness missing: BLOCKED_BY_MISSING_EVIDENCE
  -> PASS
```

### 8.7 Current Integrated Verdict

```text
MODEL_STATE=INTEGRATED_OPERATIONAL_CONTRACT
CODE_STATE=NOT_IMPLEMENTED_IN_THIS_PR
EVIDENCE_STATE=CI_NOT_ATTACHED
DECISION_STATE=BLOCKED_BY_MISSING_EVIDENCE_UNTIL_EXECUTABLE_PIPELINE_EXISTS
NEXT_ACTION=IMPLEMENT_X10R_RECONSTRUCTION_CLI_WITH_FIXTURES_FALSIFIERS_HASHED_ARTIFACTS_AND_CI_GATE
```

This is the unified operating model: symptoms identify failure modes, data forms the evidence spine, context blocks category errors, constraints define hard gates, and roles prevent responsibility from dissolving into inspirational fog.

## 9. Current Execution Verdict

```text
CAPSULE_SPEC_CREATED
BASE_COMMIT_PINNED=196063b36512ba55048d3f49d08224c2c316ab16
CODE_EXECUTION_NOT_PERFORMED_IN_THIS_COMMIT
CI_EVIDENCE_NOT_ATTACHED
HONEST_STATE=EXECUTION_CONTRACT_READY
NEXT_STATE=IMPLEMENT_PIPELINE_AND_ATTACH_ARTIFACT_HASHES
```

This is the operational bridge from the repository's existing physics contracts to an end-to-end reconstruction pipeline. It intentionally refuses ceremonial completion until executable code, falsifiers, hashes, and CI evidence exist. Humanity may continue calling Markdown "done"; this file does not.
