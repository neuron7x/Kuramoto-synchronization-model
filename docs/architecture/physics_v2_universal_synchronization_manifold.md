# Physics v2 — Universal Synchronization Manifold

Status: **draft architecture handoff**  
Target executor: **Claude Code / local repo agent**  
Base branch: `main`  
Scope: architecture, task graph, acceptance gates, and implementation boundaries.  
Non-scope: no alpha claim, no trading recommendation, no production execution path.

## 0. First-principles frame

GeoSync already contains three load-bearing ingredients:

1. **Synchronization dynamics** through Kuramoto-family modules.
2. **Graph geometry** through Ricci / curvature features and research lanes.
3. **Machine-checkable physical contracts** through `physics_contracts/catalog.yaml`, `physics_contracts/law.py`, and `tools/validate_tests.py`.

Physics v2 must not add another decorative research layer. It must convert the existing pieces into a falsifiable manifold program:

```text
L2/order-flow events -> causal market graph -> curvature field -> synchronization state -> contract witnesses -> immutable evidence capsule
```

The central rule is simple: a physical claim is not accepted because it sounds elegant. It is accepted only when a registered law has at least one mathematical witness, one falsifier, one provenance artifact, and one documented validity domain.

## 1. Core hypothesis

Markets can be represented as a time-indexed family of causal graphs. Each graph carries:

- order-flow transport edges;
- liquidity / spread / depth weights;
- curvature estimates;
- phase variables derived from synchronized market observables;
- causal cutoff constraints preventing information from propagating faster than the data substrate supports.

The model is not allowed to claim universal market truth. The only permitted claim is narrower:

> within a declared dataset, time scale, graph construction, and null-model battery, curvature-flow and synchronization descriptors may expose regime structure that survives falsification.

## 2. Required architecture

### P0 — Inventory and boundary audit

Claude Code must first inspect the existing repo before writing implementation code:

- `physics_contracts/catalog.yaml`
- `physics_contracts/law.py`
- `tools/validate_tests.py`
- `src/geosync/features/ricci.py`
- `core/physics/forman_ricci.py`
- `core/kuramoto/ricci_flow_engine.py`
- `core/config/kuramoto_ricci.py`
- `docs/research/l2_ricci_evidence_protocol.md`
- `paper/ricci_microstructure/`
- open PR / issue context around the L2 Ricci research lane

Output artifact:

```text
artifacts/physics_v2/inventory.md
```

Acceptance:

- every touched module is listed with purpose, owner layer, and risk;
- no duplicate physics subsystem is created;
- existing APIs are extended only if a compatibility note is written.

### P1 — Law proposals, not instant doctrine

Add proposed laws to the physical-contract layer only after the inventory. Initial severity should be `warn` unless a witness and falsifier are committed in the same PR.

Candidate law ids:

```text
manifold.causal_cutoff
manifold.curvature_transport_balance
manifold.metric_snapshot_schema
manifold.provenance_replay_identity
ricci.flow_energy_nonincrease_declared_domain
kuramoto.finite_size_scaling_with_causal_cutoff
```

Each law entry must include:

- formula;
- variables;
- tolerance derived from the formula or data resolution;
- validity domain;
- falsifier strategy;
- source inside repo or peer-reviewed source;
- severity.

Acceptance:

```bash
python tools/validate_tests.py
```

must pass. Blocking laws must never be added without witnesses.

### P2 — Causal graph substrate

Implement or extend a typed graph builder that maps L2/order-flow frames to graph snapshots.

Required output object:

```text
MarketCausalGraphSnapshot
```

Minimum fields:

- `timestamp_start`
- `timestamp_end`
- `nodes`
- `edges`
- `edge_weights`
- `latency_floor_seconds`
- `causal_cutoff_seconds`
- `dataset_fingerprint`
- `construction_config_hash`

Acceptance:

- monotonic timestamps;
- no negative latency;
- no look-ahead data access;
- deterministic hash under replay;
- schema validation test.

### P3 — Curvature-flow layer

Build a discrete curvature-flow adapter on top of existing Ricci modules. Do not replace existing Ricci functions unless the inventory proves they are wrong.

Required output object:

```text
CurvatureFlowTrace
```

Minimum fields:

- snapshot id;
- curvature vector before/after;
- flow step size;
- energy functional value;
- monotonicity verdict;
- residuals;
- numerical method;
- validity flag.

Acceptance:

- a closed static graph with no rewiring must satisfy the declared monotonicity law within tolerance;
- an intentionally corrupted flow must fail a falsifier;
- all numeric constants must trace to law variables or config.

### P4 — Synchronization-manifold layer

Integrate Kuramoto descriptors as a phase layer over the graph snapshots.

Required output object:

```text
SynchronizationManifoldFrame
```

Minimum fields:

- graph snapshot id;
- curvature summary;
- order parameter;
- phase dispersion;
- causal cutoff status;
- finite-size scaling metadata;
- regime label;
- confidence diagnostics;
- validity domain.

Acceptance:

- subcritical synthetic data preserves the expected finite-size noise floor;
- supercritical synthetic data shows controlled synchronization;
- causal-cutoff violations block validity rather than being smoothed away.

### P5 — Falsification battery

Every positive result must face at least four negative controls:

1. shuffled timestamp order;
2. shuffled causal direction;
3. randomized graph weights preserving degree distribution;
4. synthetic causal-cutoff violation.

Output artifact:

```text
artifacts/physics_v2/falsification_report.json
```

Acceptance:

- a claimed effect must not survive all negative controls;
- if it survives, the report must downgrade the claim to `artifact_suspected` until a stronger falsifier exists.

### P6 — Immutable evidence capsule

Every run must write a reproducibility capsule:

```text
artifacts/physics_v2/runs/<run_id>/
  manifest.json
  config.json
  input_manifest.json
  graph_snapshots.parquet
  curvature_flow_trace.parquet
  manifold_frames.parquet
  falsification_report.json
  VERDICT.md
```

Acceptance:

- `run_id` deterministic from config + dataset fingerprint + code commit;
- rerun with same inputs gives byte-identical manifest and verdict;
- missing licensed data fails closed with a clear `DATA_UNAVAILABLE` verdict.

## 3. Required command surface

Claude Code should add CLI entrypoints only after P0/P1:

```bash
geosync-physics-v2 inventory --out artifacts/physics_v2/inventory.md
geosync-physics-v2 build-graph --config configs/physics_v2/causal_graph.yaml --out artifacts/physics_v2/runs
geosync-physics-v2 run --config configs/physics_v2/manifold.yaml --out artifacts/physics_v2/runs
geosync-physics-v2 verify RUN_ID
```

No command may silently fall back to synthetic data when real data was requested.

## 4. Implementation order

```text
P0 inventory
-> P1 law proposals
-> P2 graph snapshot schema
-> P3 curvature-flow trace
-> P4 synchronization frame
-> P5 falsification report
-> P6 capsule + CLI
-> docs/paper integration
```

Do not skip P0. Do not merge P4 before P2/P3 are covered by tests.

## 5. Non-goals

This PR must not claim:

- predictive alpha;
- production trading readiness;
- universal market physics;
- relativistic physics equivalence;
- Ricci-flow theorem beyond the declared discrete graph domain;
- validation on licensed L2 data unless the data manifest and run artifacts exist.

The correct phrasing is **relativistic-inspired causal cutoff**, not relativistic market law.

## 6. Acceptance gate for final implementation PR

The implementation PR is acceptable only if all are true:

```bash
python tools/validate_tests.py
python -m pytest tests/physics_contracts -q
python -m pytest tests/research tests/unit -q
python -m ruff check .
python -m mypy --strict src core physics_contracts tools
```

Plus, for any real L2 claim:

```bash
geosync-physics-v2 verify RUN_ID
```

must produce a `VERDICT.md` that explicitly states:

- dataset fingerprint;
- code commit;
- config hash;
- laws exercised;
- falsifiers passed/failed;
- claim maturity level.

## 7. Claude Code directive

Claude Code must treat this document as the architecture contract. The first implementation PR should be narrow:

1. inventory artifact;
2. proposed law entries with `warn` severity;
3. graph snapshot dataclass/schema;
4. minimal deterministic synthetic tests;
5. no positive market claim.

Only later PRs may add numerical Ricci-flow and L2 evidence. If a required dataset, lockfile, or release gate is unavailable, the correct output is a fail-closed blocker note, not a fabricated green check.

## 8. Fixed invariant

```text
No physical market claim may enter the repo unless its validity domain, falsifier, witness, and provenance capsule are present in the same reviewable chain.
```
