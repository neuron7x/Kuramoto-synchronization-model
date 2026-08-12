# 13 — Physics Runtime Hardening (after #1309)

Status discipline: this document is an audit record, not a result claim. It is
disciplined against high-standard scientific reproducibility. It contains no
praise and no promotion-by-wording. Every promotion below is backed by an
invariant + source + test + falsifier; everything else is left where it was and
the reason is stated.

Scope: convert declared physics/neuro mechanisms from *documented / partial /
decorative* into *executable, falsifiable, CI-enforced* mechanisms, or demote
them honestly. Ledger: `.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml`.

Before → after tier counts (distinguished_evidence_table.json):

| tier | before | after |
|------|-------:|------:|
| OPERATIONAL | 18 | 21 |
| PARTIAL | 6 | 3 |
| DECORATIVE | 3 | 3 |
| OVERCLAIM | 2 | 2 |
| LEGACY | 2 | 2 |
| REJECTED | 1 | 1 |

Invariant registry: 108 → 110 (`+INV-CBR1`, `+INV-HOM1`; `INV-DA8` already in
the registry, now also documented in CLAUDE.md). README / BASELINE / CLAUDE
counts synced; `scripts/check_invariant_count_sync.py` green.

---

## 1. What was executable before

- Kuramoto order parameter, Ott–Antonsen reduction, Lyapunov MLE/spectrum,
  Ricci bounds/flow, free-energy ECS, Kelly sizing, serotonin/dopamine/GABA
  controllers, cryptobiosis, DRO-ARA — all OPERATIONAL with INV bindings and
  witnesses (unchanged here).
- The Ott–Antonsen integrator already had a fail-closed INV-OA1 per-step unit
  disk gate and an INV-OA2 converged-steady-state oracle.
- The coherence-bridge contract verifier (`coherence_bridge/invariants.py`,
  theorems T1–T13) already existed but was not applied as a fail-closed gate by
  the adapter, and did not distinguish the two Ricci operators.

## 2. What was only documented (now executed)

- **Adaptive criticality κ_critical (INV-AC1-rev).** The isolation gate existed
  only as a CLAUDE.md derivation and a *test-local* reference implementation
  (`tests/unit/physics/test_adaptive_criticality_kappa.py` explicitly noted
  "Source has no isolate() symbol"). It is now EXECUTED SOURCE in
  `geosync/estimators/dfa_gamma_estimator.py`: `kappa_critical`,
  `should_isolate_node`, `assess_node`, `isolation_mask`,
  `aggregate_excluding_isolated`, `AdaptiveCriticalityGate`,
  `CriticalityAssessment`, `IsolationReason`. The closed form
  `κ_critical = −ln(ΔH_max/ε)/(λ_local+δ)` is mathematically identical to the
  contract. The witness test now imports the source symbols.

## 3. What now fails closed (this PR)

- **Adaptive criticality.** Non-finite κ_node/λ_local → isolate
  (`NON_FINITE_INPUT`); λ_local+δ ≤ 0 → isolate (`SINGULAR_DENOMINATOR`);
  all-isolated ensemble → `ValueError` (no fabricated aggregate); invalid shared
  ε/ΔH_max → `ValueError` (no silent fallback). Gate boundary is strict `<`.
- **Coherence bridge (INV-CBR1).** `coherence_bridge/physics_contract.py::
  validate_physics_contract` returns `status=INVALID_PHYSICS_CONTRACT`,
  `decision=NO_GO`, `safe_risk_scalar=0.0` when R∉[0,1], gamma non-finite OR
  gamma<0 (out-of-band spectral exponent), or Ollivier κ>1+ε. The adapter now
  emits an explicit name split: `ollivier_kappa` (the κ≤1 operator INV-RC1
  governs) vs `augmented_forman_ricci` (Forman blend, legitimately >1, checked
  for finiteness only, never κ-bound evidence); `ricci_curvature` is retained as
  a backward-compatible display alias of the Forman blend.
- **Ott–Antonsen (INV-OA2).** New machine-epsilon-derived domain floor
  `R0_MIN = 4·ε_mach`. With the opt-in `require_convergence=True`, a
  supercritical run seeded at/below the unstable fixed point z=0 raises
  `ValueError` (the attractor is unreachable from the repeller). The default
  `integrate()` still abstains on R0=0 (unchanged). The INV-OA2 converged-state
  oracle now also abstains on the repeller *neighbourhood*: it fires only once
  the trajectory has escaped the repeller basin (`R_converged > ½·R_∞`), so a
  tiny-R0 finite-T stall at R≈0 is no longer misread as a CFL failure (it is the
  unstable branch); a genuine CFL plateau near the attractor is still caught.
- **Hebbian eligibility.** Caller-supplied eligibility is validated fail-closed
  to `[0,1]^11` finite (`_validate_eligibility`); an out-of-envelope component
  now raises instead of silently inflating the weight update.

## 4. What remains PARTIAL (and exactly why)

- **hebbian-plasticity-update.** The eligibility input-contract hole is closed
  and the per-step update is envelope-bounded, but the *global cumulative* upper
  bound is NOT proven: the learning-rate floor (`lr_floor`) means sustained LTP
  grows weights linearly without bound (the docstring's "renormalize / sum
  preserved" is not implemented). No global-stability falsifier exists, so it is
  NOT promoted. Promotion is blocked on that proof, not on an INV name.
- **neuro-optimizer-balance-metrics.** Kept PARTIAL by design. The witness is a
  statistical *separation* (null model N=3000, seed 20260623, ~2.7σ) — that is
  admissibility evidence, not a per-input hard contract. DA/5HT and E/I are
  uncited arithmetic ratios (QUARANTINE_DOC). No honest hard invariant exists,
  so promotion is declined on epistemic grounds.
- **neuro-validation-bounds.** Engineering numeric guards with no biological
  citation (QUARANTINE_DOC); unchanged.

## 5. What was promoted (PARTIAL → OPERATIONAL, with evidence)

- **dopamine-execution-adapter-tanh → INV-DA8.** |δ|=|tanh(scale·raw)| ≤ 1 and
  finite for finite input (structural; tanh range). Scope-distinct from INV-DA7
  (∂δ/∂r = sech²(·) ≠ 1). INV-DA8 now in CLAUDE.md + INVARIANTS.yaml with
  source/tests bindings.
- **coherence-bridge-geosync-adapter → INV-CBR1.** See §3.
- **homeostatic-stabilizer → INV-HOM1 (conditional).** Common-mode reset wave is
  Lyapunov-energy non-increasing (E_post ≤ E_pre); contract violations raise;
  over-threshold |Δφ| fail-closes to `safety_lock`. SCOPE/NON-CLAIM: energy
  descent is proven for the coherent common-mode regime only; E/I, "serotonin",
  "GABA tone" are arithmetic proxies, not modelled dynamics.

## 6. What was rejected / declined

- Promotion of hebbian and neuro-optimizer (see §4) — declined, not deferred by
  wording.
- INV-AC1 (the original `κ_critical = −dH/dt·τ` form) remains rejected in favour
  of INV-AC1-rev (documented in CLAUDE.md; Pesin-identity failure in
  non-ergodic systems).

## 7. Exact tests

- `tests/unit/physics/test_adaptive_criticality_kappa.py` — threshold crossing,
  equality boundary (strict `<`), non-finite input, singular denominator,
  ensemble exclusion, all-isolated fail-closed, env determinism.
- `tests/integration/test_coherence_bridge_invariants.py` — INV-K1/INV-RC1
  preservation; INV-CBR1: negative gamma → fail-closed, Forman>1 with valid
  Ollivier → VALID, Forman>1 does not trip RC1, Ollivier>1 → fail-closed,
  out-of-band R / non-finite gamma → fail-closed, adapter emits the name split.
- `tests/unit/physics/test_ott_antonsen_oracle.py` — repeller counterexample
  raises under `require_convergence`; convergence holds above the floor; default
  integrate abstains on R0=0; subcritical convergence; R0_MIN is
  machine-epsilon-derived. Plus `test_T28_wave2_witnesses.py` unit-disk property
  sweep (Hypothesis).
- `tests/unit/neuro/test_hebbian_plasticity_bounds.py` — out-of-envelope
  eligibility fails closed; in-envelope accepted.
- `tests/unit/physics/test_dopamine_execution_adapter_bounds.py`,
  `tests/unit/neuro/test_homeostatic_stabilizer_setpoint.py` — INV-DA8 / INV-HOM1
  witnesses.
- `tests/ci/test_evidence_integrity_gate.py` — negative regressions proving the
  new gate (`scripts/ci/check_evidence_integrity.py`) rejects fake promotion:
  unknown INV, missing test file, no inv_ref/test/falsifier, PARTIAL citing an
  INV, un-quarantined DECORATIVE on a runtime path.

CI: `make phd-evidence` (now includes `evidence_integrity`),
`python tools/audit/neuro_symbolic_audit.py`,
`scripts/ci/check_invariant_source_binding.py`,
`scripts/check_invariant_count_sync.py`,
`scripts/ci/check_physics_law_witness_index.py`,
`scripts/ci/check_physics_inference_readiness.py` — all green.

## 8. Exact non-claims

- No alpha, no edge, no profitability.
- No market law, no universal physics of markets; observers are not predictors.
- No biological equivalence — every neuro term is an engineering analogue.
- No live-venue execution claim; all witnesses are synthetic-only.
- Homeostatic energy descent is common-mode only (§5).
- The dopamine adapter is a bounded normaliser, not raw TD-error (never an
  INV-DA7-scoped quantity).
- Coherence-bridge VALID means "physics contract preserved", not "trade".

## 9. Remaining open counterexamples / gaps

- **Enforcement status (split).** `validate_physics_contract` (INV-CBR1) is now
  **RUNTIME-ENFORCED**: `coherence_bridge/risk_gate.py::CoherenceRiskGate.apply`
  calls it FIRST and HARD-BLOCKS an out-of-band signal (negative/non-finite
  gamma, R∉[0,1], Ollivier κ>1) before any regime/order-sizing logic, and sizes
  on `verdict.safe_risk_scalar` not the raw field (consumer-level refusal tests
  in `tests/test_risk_gate.py`). `AdaptiveCriticalityGate` (INV-AC1-rev) remains
  **source-available / fail-closed / unit-tested but NOT yet wired** into a
  production ensemble consumer (there is no live ensemble-aggregation caller yet);
  its claim tier stays "executed, tested source", not "runtime-enforced".
- **Hebbian global stability.** There is no global (cumulative) upper bound under
  sustained LTP with `lr_floor > 0`; this UNBOUNDEDNESS is characterized by an
  executable negative witness (`test_hebbian_global_stability.py`). Hebbian stays
  PARTIAL by design.
- **Homeostatic heterogeneous error.** Energy descent is not guaranteed for
  non-common-mode phase error; INV-HOM1 is explicitly conditional.
- **Ott–Antonsen near-onset finite-T.** For K just above K_c the relaxation time
  diverges (~1/(K−K_c)); the oracle deliberately abstains on under-converged
  runs, so a finite-T run may legitimately not have reached R_∞ — this is a
  caller T/dt responsibility, not a runtime guarantee.
- **Invariant authority.** `INV-AC1-rev` is now a registry entry in
  `.claude/physics/INVARIANTS.yaml` (count 110→111); the evidence-integrity gate
  treats ONLY the registry as authoritative (CLAUDE.md prose is a doc mirror, not
  an authority).
