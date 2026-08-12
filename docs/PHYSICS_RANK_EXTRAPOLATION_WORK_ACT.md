# GeoSync — Expert Work Act: Physics Rank Extrapolation

Status: canonical work act / execution protocol  
Repository: neuron7xLab/GeoSync  
Scope: existing second-order Kuramoto physics, Ricci-Kuramoto manifold kernel, evidence promotion path  
Mode: laboratory-academic, theoretically bounded, engineering-technical, practice-bound  
Target: move the existing physics line from local verified mechanism to reviewer-grade research-engineering artifact

---

## 1. Purpose

This act defines the work required to extrapolate the existing GeoSync physics layer into a higher scientific and industrial rank without converting ambition into evidence.

The target is not to claim a new law, not to claim alpha, and not to market an advanced vocabulary. The target is to produce a deterministic, falsifiable, reproducible physics-informed computation stack whose claims are bounded by measured artifacts.

Canonical transformation:

```text
existing_physics
  -> numerical audit
  -> Ricci/Kuramoto fusion
  -> microstructure substrate
  -> null-superior evidence
  -> recursive falsification
  -> external reproducibility
  -> reviewer-grade rank
```

Scientific promotion is allowed only when the artifact survives tests that are stronger than the original claim.

---

## 2. Current Verified Physics Foundation

The repository already contains a non-trivial physics base.

### 2.1 Second-order Kuramoto / swing-equation layer

Existing physical equation:

```text
m_i * theta_ddot_i + d_i * theta_dot_i = omega_i + K * sum_j A_ij * sin(theta_j - theta_i)
```

Operational meaning:

- `m_i` represents inertia;
- `d_i` represents damping;
- `omega_i` represents natural frequency / injection-demand imbalance;
- `A_ij` represents coupling topology;
- the system supports transient oscillations, frequency spread, RoCoF, nadir/zenith, and inertia-dependent stability margins.

Current validated value:

```text
GeoSync already has a physical oscillator substrate with inertia, damping, coupling topology, trajectory output, velocity output, and fail-closed numerical guards.
```

Current limitation:

```text
This is a physical simulation and numerical diagnostic layer. It is not yet an externally validated market-predictive physics theory.
```

### 2.2 BBK / semi-implicit velocity update

The live second-order engine now uses a semi-implicit damping update instead of evaluating velocity-dependent damping only at the old velocity.

Rank significance:

```text
The engine moved from a weaker explicit-damping numerical map toward a physically better damped velocity-Verlet / BBK-style update.
```

Claim boundary:

```text
This supports improved numerical physics. It does not by itself prove market predictivity.
```

### 2.3 Epistemic-integrity precedent

The frozen calibration conflict was correctly resolved by snapshot/replay isolation rather than by rewriting frozen artifacts.

Rank significance:

```text
This establishes a research-governance precedent: historical evidence is not rewritten to rescue live-code evolution.
```

This is a necessary property for scientific rank.

---

## 3. Rank Gap

Current rank:

```text
VERIFIED local physics mechanism + HYPOTHESIS-tier predictive research line
```

Target rank:

```text
MEASURED / REPRODUCIBLE / EXTERNALLY REVIEWABLE physics-informed market-microstructure research artifact
```

Blocked claims:

```text
GeoSync must not claim:
- discovered market law;
- verified alpha;
- full physics certificate;
- industry-grade predictive system;
- externally validated scientific breakthrough.
```

Admissible current claim:

```text
GeoSync contains a verification-first physics-informed research infrastructure with a second-order Kuramoto substrate, Ricci/Kuramoto planning path, replay governance, and claim-promotion discipline.
```

---

## 4. Extrapolation Principle

Extrapolation is valid only when it extends implementation, validation, or artifact rigor without extending scientific status beyond evidence.

Canonical form:

```text
current_physics_signal + current_governance_signal
  -> implied_missing_computation
  -> stricter experiment
  -> measurable artifact
  -> narrower or stronger claim
```

Valid extrapolation:

```text
second-order Kuramoto exists
  -> derive phase/inertia/damping observables
  -> connect to L2 microstructure oscillator extraction
  -> combine with Ricci curvature field
  -> test fragility/regime-transition prediction under nulls
```

Invalid extrapolation:

```text
second-order Kuramoto exists
  -> therefore markets are physically predicted
```

---

## 5. Fundamental Research Question

Primary question:

```text
Can curvature-modulated oscillator synchronization over real market microstructure graphs predict regime transition, volatility expansion, or liquidity fragility better than nulls and standard baselines?
```

Not primary question:

```text
Can the system guess price direction?
```

Correct first target:

```text
regime_break / volatility_expansion / liquidity_fragility / systemic_transition_state
```

Reason:

```text
The existing physics layer is naturally suited to stability, synchronization, perturbation, damping, fragility, and transition analysis. Price-direction alpha is a downstream economic claim and must not be used as the first scientific target.
```

---

## 6. Required Work Packages

### WP-01 — Physics Contract Inventory

Objective: enumerate every physical object already present in the repository and assign claim-tier boundaries.

Outputs:

- `docs/physics/PHYSICS_OBJECT_REGISTRY.md`
- `docs/physics/PHYSICS_CLAIM_BOUNDARIES.md`
- mapping: equation -> code path -> test path -> admissible claim -> forbidden claim

Acceptance gate:

```text
Every physics term must have a code object, unit/scale assumption, validation status, and forbidden-overclaim entry.
```

### WP-02 — Numerical Validity Upgrade

Objective: upgrade the second-order Kuramoto layer from local correctness to reviewer-grade numerical validation.

Required experiments:

1. damped convergence order;
2. undamped conservative-regime energy drift;
3. heterogeneous mass/damping regression;
4. small-dt convergence sweep;
5. cross-solver RK4 reference;
6. stiffness-regime classification;
7. finite-state fail-closed test;
8. RoCoF bound behavior;
9. deterministic seed/replay proof.

Outputs:

- `artifacts/physics/second_order_audit/<run_id>/manifest.json`
- `artifacts/physics/second_order_audit/<run_id>/metrics.json`
- `artifacts/physics/second_order_audit/<run_id>/claim_card.json`

Acceptance gate:

```text
No stability or physical-validity claim is promoted unless the audit reports which regimes passed, which regimes failed, and which regimes remain outside scope.
```

### WP-03 — L2 Microstructure Substrate

Objective: define the market data object that can legitimately host Ricci/Kuramoto physics.

Required streams:

- best bid/ask;
- depth levels;
- spread;
- depth imbalance;
- order-flow imbalance;
- trade intensity;
- realized volatility;
- liquidity withdrawal / refill events.

Outputs:

- `data/contracts/l2_session.schema.json`
- `configs/physics_rank/l2_session.yaml`
- `artifacts/data/l2_sessions/<session_id>/manifest.json`

Acceptance gate:

```text
No market-physics claim may be tested on unversioned, mutable, or undocumented session data.
```

### WP-04 — Oscillator Extraction Layer

Objective: convert microstructure signals into physically bounded oscillator observables.

Candidate mappings:

```text
phase theta(t)        <- cyclic state of imbalance / flow pressure
velocity theta_dot(t) <- rate of pressure rotation
mass m(t)             <- liquidity inertia / depth resistance
damping d(t)          <- spread/impact dissipation
omega(t)              <- exogenous flow drive
K_ij(t)               <- cross-asset or cross-level coupling strength
```

Outputs:

- `core/physics/oscillator_extraction.py`
- `tests/physics/test_oscillator_extraction_contract.py`
- artifact: `oscillator_fields.parquet`

Acceptance gate:

```text
Every extracted physical variable must declare its market proxy, unit convention, normalization, and failure mode.
```

### WP-05 — Ricci Curvature Field

Objective: construct a dynamic graph/manifold field from L2 microstructure rather than from return-correlation alone.

Graph candidates:

- asset nodes;
- liquidity-level nodes;
- venue nodes;
- temporal-state nodes;
- edge weights from transport cost, flow similarity, depth transition, or pressure coupling.

Outputs:

- `core/geometry/ricci_microstructure.py`
- `artifacts/geometry/<run_id>/ricci_field.parquet`
- `artifacts/geometry/<run_id>/ricci_nulls.json`

Acceptance gate:

```text
Ricci curvature becomes evidence-bearing only after sensitivity, parameter elasticity, graph-null, and session replay checks.
```

### WP-06 — Ricci-Kuramoto Coupling Kernel

Objective: fuse curvature and synchronization into one mechanism.

Candidate kernel:

```text
K_ij_eff(t) = K_0 * g(curvature_ij(t), liquidity_ij(t), spread_ij(t), volatility_ij(t))
```

Core hypothesis:

```text
Curvature deformation modulates synchronization fragility; unstable curvature/synchronization regimes may precede volatility expansion or liquidity breaks.
```

Outputs:

- `core/kernels/ricci_kuramoto_manifold.py`
- `tests/kernels/test_ricci_kuramoto_contract.py`
- artifact: `fused_fragility_score.parquet`

Acceptance gate:

```text
The fused kernel must beat standalone Ricci, standalone Kuramoto, naive volatility, and randomized fusion under identical validation splits before any fusion claim is promoted.
```

### WP-07 — Null and Baseline Superiority Suite

Objective: prove the signal is not a structure illusion.

Required nulls:

1. shuffled phase null;
2. shuffled graph-edge null;
3. randomized coupling null;
4. block-bootstrap session null;
5. time-shifted target null;
6. label permutation null;
7. null-fusion Ricci/Kuramoto mismatch.

Required baselines:

1. naive volatility threshold;
2. realized volatility autoregression;
3. VAR baseline;
4. GARCH baseline;
5. HMM regime baseline;
6. liquidity imbalance baseline;
7. spread-widening baseline.

Outputs:

- `artifacts/validation/<run_id>/null_report.json`
- `artifacts/validation/<run_id>/baseline_report.json`
- `artifacts/validation/<run_id>/superiority_table.csv`

Acceptance gate:

```text
A predictive claim is blocked unless the kernel shows stable superiority over nulls and baselines across fixed OOS splits.
```

### WP-08 — Recursive Falsification Loop

Objective: force every output to become the next input of stricter validation.

Loop:

```text
kernel_output
  -> evidence_card
  -> residual_map
  -> counterexample_search
  -> stricter_null
  -> revised_kernel_or_demoted_claim
```

Outputs:

- `artifacts/recursion/<cycle_id>/residual_map.json`
- `artifacts/recursion/<cycle_id>/counterexamples.json`
- `artifacts/recursion/<cycle_id>/next_action.json`

Acceptance gate:

```text
Each cycle must emit either a reproduced hash, a narrowed claim, a failed claim, a stricter validation rule, or a residual-informed kernel update.
```

### WP-09 — Industrial Engineering Readiness

Objective: make the system usable as serious quantitative infrastructure without overstating deployment proof.

Required properties:

- deterministic CLI;
- typed configs;
- artifact manifests;
- versioned datasets;
- CI verification;
- immutable evidence bundles;
- failure-mode reporting;
- audit logs;
- reproducible benchmark command;
- no silent fallback from missing evidence.

Outputs:

- `docs/runbooks/PHYSICS_RANK_RUNBOOK.md`
- `scripts/physics_rank_audit.py`
- `artifacts/physics_rank/<run_id>/VERDICT.md`

Acceptance gate:

```text
Industrial-readiness language is allowed only for infrastructure reproducibility, not for market profitability or production trading performance.
```

### WP-10 — Scientific Rank Package

Objective: prepare the artifact for external review.

Required package:

- statement of need;
- relation to prior work;
- design rationale;
- reproducibility guide;
- test matrix;
- limitations;
- AI assistance disclosure;
- software citation metadata;
- DOI-ready release archive;
- JOSS-style paper draft.

Outputs:

- `paper/paper.md`
- `CITATION.cff`
- `docs/reproducibility/REPRODUCIBILITY.md`
- `docs/reproducibility/AI_USAGE_DISCLOSURE.md`
- tagged release + archived artifact

Acceptance gate:

```text
External-rank claim is blocked until the software can be installed, run, tested, cited, and reviewed by someone outside the author session.
```

---

## 7. Rank Ladder

```text
R0: Narrative hypothesis
R1: Instrumented local mechanism
R2: Reproducible local physics audit
R3: Real-data measured artifact
R4: Null-superior artifact
R5: OOS/cost-surviving artifact
R6: External reproduction artifact
R7: DOI/JOSS/arXiv-ready scientific software artifact
R8: Independently used or cited research infrastructure
```

Current estimated position:

```text
R1 -> R2 transition for second-order Kuramoto physics
R0 -> R1/R2 planning state for Ricci-Kuramoto market-microstructure predictivity
```

Target for this act:

```text
R6/R7 for research software rank;
R4/R5 before any predictive-strength claim;
R8 only after external use, citation, or adoption evidence.
```

---

## 8. Claim Promotion Rules

### Allowed now

```text
GeoSync implements a verification-first physics-informed research stack with second-order Kuramoto dynamics, fail-closed numerical guards, Ricci-Kuramoto planning, and artifact-governed claim promotion.
```

### Allowed after WP-02

```text
The second-order Kuramoto layer is numerically audited under declared regimes and limitations.
```

### Allowed after WP-03 to WP-07

```text
The Ricci-Kuramoto manifold kernel produced measured evidence on fixed L2 sessions and was tested against specified nulls and baselines.
```

### Allowed after WP-08 to WP-10

```text
The artifact is reproducible, externally reviewable, citation-ready, and suitable for scientific software review.
```

### Always forbidden without external proof

```text
industry-leading predictor
verified alpha
market law
production trading system
scientific breakthrough
universal physics of markets
```

---

## 9. Final Acceptance Definition

The work reaches the target rank only if the following are simultaneously true:

```text
1. Existing physics is fully mapped to code, tests, artifacts, and claim boundaries.
2. Second-order dynamics pass declared numerical audits without hidden promotion.
3. L2 data substrate is immutable, hashed, and replayable.
4. Oscillator extraction is physically bounded and empirically measured.
5. Ricci field is computed on real microstructure graphs.
6. Ricci-Kuramoto fusion beats standalone and null-fusion baselines.
7. Predictive evidence survives OOS and cost/slippage constraints.
8. Recursive falsification produces stable artifacts or honest demotion.
9. Evidence bundles can be reproduced outside the original session.
10. Scientific software package satisfies documentation, tests, citation, and review-readiness criteria.
```

If any condition fails, the correct output is not promotion. The correct output is a narrower claim, a failed-claim report, or a stricter next experiment.

---

## 10. Final Verdict

This act does not declare that GeoSync already occupies a fundamentally new rank in science or industry.

It defines the route by which the existing physics can be extrapolated into that rank:

```text
validated oscillator physics
  + Ricci microstructure geometry
  + L2 data contracts
  + null-superior evidence
  + recursive falsification
  + reproducible artifacts
  + external review package
  = credible high-rank research-engineering artifact
```

The highest valid operating law remains:

```text
Promote only what survives measurement.
Demote everything else.
```
