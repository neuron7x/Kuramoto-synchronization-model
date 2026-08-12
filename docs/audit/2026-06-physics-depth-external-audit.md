<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# 2026-06 Physics-Depth External Audit (Closes #1186)

> **Role.** Principal Research Physicist / Complex-Systems Scientist /
> Verification-Engineering Auditor.
> **Target.** `neuron7xLab/GeoSync` at `origin/main` **after** the merge of
> #1096 (physics core contract remediation — canonical Kuramoto/Ricci
> semantics + audit gates) and #1123 (claim-state overclaim guards). This audit
> reads the **canonical current surface**, not a stale snapshot.
>
> **Discipline.** This document *describes*; it does not fix, promote, or weaken
> anything. No physics code, claim state, or gate was modified to produce it.
> Every finding maps to a real file path read during the audit. Banned product
> phrasing appears here only as quoted *evidence of a boundary being held* — the
> `docs/audit/` prefix is exempt from `scripts/ci/check_claim_boundary.py`
> (`EXCLUDE_DIR_PREFIXES`), which is why this file may quote it.

---

## Method and provenance

Files read in full for this audit (load-bearing — every criticism below cites
one of these):

* `physics_contracts/law.py` — `@law` witness decorator, `WITNESS_REGISTRY`,
  `coverage_report`.
* `physics_contracts/manifold/ricci_trace.py` — `RicciFlowTrace`, flow-energy
  monotonicity, exact Gauss–Bonnet residual guard.
* `physics_contracts/manifold/sync_frame.py` — `SynchronizationManifoldFrame`,
  `build_sync_frame`, finite-size floor.
* `physics_contracts/manifold/negative_controls.py` — four-control null battery
  → `ComparisonReport`.
* `physics_contracts/manifold/evidence_binding.py` — `bind_physics_evidence`,
  claim-tier-above-evidence-tier falsifier.
* `physics_contracts/catalog.yaml` — 42-law catalog.
* `core/kuramoto/kuramoto_ricci_engine.py` — Restrepo-Ott-Hunt boundary,
  `ricci_to_positive_adjacency` / `ricci_to_signed_coupling` / `assert_roh_compatible`.
* `.claude/physics/INVARIANTS.yaml` — single source of truth, 112 invariants
  (`python scripts/count_invariants.py` → 112).
* `governance/FALSIFIER_LEDGER.yaml`, `governance/NEGATIVE_EVIDENCE.yaml`.
* `tools/physics_score.py`, `VERDICT.md`.
* `docs/PHYSICS_BOUNDARY_AUDIT.md`, `FORBIDDEN_CLAIMS.md`, `PRODUCT_CATEGORY.md`.

What #1096 landed on this surface (verified against `core/kuramoto/kuramoto_ricci_engine.py`
and the `CLAUDE.md` registry header): **INV-KR4** ("No silent physics loss",
FP-2) — two NAMED Ricci paths (`ricci_to_positive_adjacency` with
`RicciAdjacencyAudit` metadata, and `ricci_to_signed_coupling` preserving every
negative κ), plus `assert_roh_compatible` fail-closing a signed matrix sent to
the onset boundary. The catalog gained `kuramoto_ricci.semantics_split`. The
registry count moved 111 → 112.

---

VERDICT:

GeoSync is a **structurally serious verification-first research platform whose
physics layer is, on the audited surface, mostly *contract-and-bound* rather
than *solver-and-claim*** — and that is its principal strength, not a weakness.
The manifold contracts (`ricci_trace.py`, `sync_frame.py`,
`evidence_binding.py`) are honest "trace objects, not solvers": they bind the
outputs of existing primitives and refuse fail-closed to record physically
impossible states (κ > 1, sub-bound Δt·Δf, increasing Ricci-flow energy under a
non-increase verdict, a synthetic-data run claiming a real-data tier). #1096
genuinely closed a real category error (signed Ollivier κ silently clipped
before the Restrepo-Ott-Hunt boundary, which is derived for non-negative
weights). The product boundary (`PRODUCT_CATEGORY.md`, `FORBIDDEN_CLAIMS.md`)
is machine-enforced and held.

The **weaknesses are evidential, not mathematical**: the system proves
*invariants of its own computation* well, but the bridge from those invariants
to *real-market* claims remains thin — `tools/physics_score.py` itself returns
`S_total: 81.5` against an `88–92` target with
`FINAL_PHYSICS_VALIDATION: NO` (`VERDICT.md`), the Ricci-microstructure claim is
`Not Deployable` on one session (`FORBIDDEN_CLAIMS.md`), and the falsifier
ledger has 6 entries / negative-evidence ledger 4 entries — adequate as
*seeds*, thin as *coverage*. **Status: a credible research instrument with an
honest self-reported sub-target physics score; not a proven market-physics
system, and the repository says so itself.**

TOP_10_CRITICAL_DEFECTS:

1. **`build_sync_frame` regime gate is one-sided at the exact threshold and
   asymmetric in strictness.** In `physics_contracts/manifold/sync_frame.py`,
   the subcritical falsifier fires on `coupling_K < critical_K and R > floor`,
   the supercritical on `coupling_K > critical_K and R <= floor`. The case
   `coupling_K == critical_K` is unguarded (no regime check at criticality),
   and the two branches use `>` vs `<=` so the boundary point is handled
   inconsistently. At true criticality the finite-size order parameter is
   neither floored nor lifted, so the frame silently admits any `R` there. This
   is a real seam in the catalog-`kuramoto.subcritical_finite_size` /
   `kuramoto.frequency_entrainment` enforcement.

2. **The finite-size floor coefficient `3/√N` is a single hard-coded scalar
   with no distributional justification per call.** `sync_frame.py` sets
   `_FINITE_SIZE_COEFF = 3.0` and `CLAUDE.md` (INV-K5) says `C ∈ [2,3]`. Using
   the upper end (3.0) makes the subcritical test *permissive* (a higher floor
   admits more `R`) and the supercritical test *strict*. The coefficient is
   asserted as "the law's own coefficient, not a magic number," but no test in
   the audited surface ties `C=3` to a measured `⟨R⟩` quantile at the actual
   `N`, so it functions as a tuned constant.

3. **`order_parameter` in `kuramoto_ricci_engine.py` has no `R∈[0,1]`
   fail-closed guard at the engine layer.** `order_parameter(theta)` returns
   `jnp.abs(jnp.mean(jnp.exp(1j*theta)))`; INV-K1 (R∈[0,1]) is only enforced
   downstream in `SynchronizationManifoldFrame.__post_init__`. A caller using
   the engine primitive directly (e.g. feeding a non-finite θ) gets a value
   with no contract check — the invariant lives in the frame, not the producer.

4. **`phase_transition_boundary` returns a *fabricated* Φ for the
   disconnected/zero-spectrum case rather than failing closed.** In
   `kuramoto_ricci_engine.py`, when `lam_max <= 0.0` it returns
   `phi = -2.0*γ`, `K_c = inf`. This is defensible physics (a zero adjacency
   never synchronises), but it is a *silent* substitution: an all-zero or
   numerically-degenerate `A` produces a confident "incoherent" verdict with no
   warning that λ_max collapsed. The INV-KR3 fail-closed discipline elsewhere in
   the file (ValueError on every contract violation) is not applied here.

5. **Ricci `κ ≤ 1` is enforced exactly but the lower bound is domain-gated only
   by a *string token*.** `ricci_trace.py` selects the lower bound via
   `validity_domain == PRICE_GRAPH_DOMAIN` (the literal `"build_price_graph"`).
   A caller that mis-types or omits the token gets `lower = -inf` (no lower
   bound enforced at all). INV-RC3 (κ∈[−1,1] for price graphs) is therefore as
   strong as the caller's string hygiene; there is no structural link from the
   actual graph builder to the token.

6. **The negative-control battery beats nulls by a strict `>` with no
   multiple-comparison correction.** `negative_controls.py`
   `assemble_comparison_report` sets `survived = all(candidate > nc.statistic
   for nc in null_controls)` against the 95th percentile of each of four nulls.
   Four independent one-sided 5% tests with no Holm/BH-FDR correction inflate
   the family-wise false-survival rate; the 2026-04-30 audit (`docs/audit/2026-04-30-external-audit.md`,
   S3.3) explicitly flagged "require Holm/BH-FDR correction on every published
   p-value" and that backlog row is not closed in this battery.

7. **`evidence_binding.py` accepts an arbitrary `validity_domain` /
   `replay_command` string without verifying it is runnable.** `bind_physics_evidence`
   enforces non-empty `replay_command` and non-empty `falsifiers_passed`, but
   never checks the replay command parses or that the named falsifiers exist in
   `governance/FALSIFIER_LEDGER.yaml`. A capsule can claim falsifiers by free
   string; the cross-check to the executable ledger is absent at the binding
   layer.

8. **Falsifier-ledger coverage is sparse relative to the law catalog.**
   `governance/FALSIFIER_LEDGER.yaml` has 6 entries; `physics_contracts/catalog.yaml`
   has 42 laws and `.claude/physics/INVARIANTS.yaml` has 112 invariants. Most
   laws have a *witness* (via `@law`) but no entry in the executable
   *promotion-blocking* falsifier ledger. The ledger's own header says it gates
   promotion through "probe H.falsification" — so 36+ catalog laws have no
   promotion-blocking kill-test registered there.

9. **`tools/physics_score.py` hard-codes its own target interval and several
   sub-scores are static literals, not measured.** `TARGET_INTERVAL =
   [88.0, 92.0]` is a constant, and `VERDICT.md` shows `S_math_object 75.0`,
   `S_dimensional_consistency 70.0` carrying statuses like
   `PARTIAL_PASS_NO_TYPED_UNITS` — i.e. the dimensional-consistency score is a
   self-assessed literal, not derived from a typed-units check. The oracle's
   own docstring concedes it "scores only visible carriers"; the risk is that a
   number (81.5) reads as a measurement when several inputs are editorial.

10. **No dimensional/units contract is machine-checked anywhere on the audited
    surface.** `VERDICT.md` records `S_dimensional_consistency` at 70.0
    `PARTIAL_PASS_NO_TYPED_UNITS`. The physics modules use bare `float`/`Array`
    with no unit type (no `pint`-style dimensions). Free-energy `F = U − T·S`,
    Landauer `E_min = k_B·T·ln(...)`, and Kelly `f* = μ/σ²` mix quantities whose
    dimensional coherence is asserted in prose (`CLAUDE.md`) but never enforced
    by a contract that would catch a dimension error.

TOP_10_PHYSICS_TIGHTENING_POINTS:

1. **Criticality handling.** Add an explicit `coupling_K == critical_K` branch
   in `build_sync_frame` (`sync_frame.py`) with a documented behaviour
   (finite-size scaling-collapse expectation) instead of falling through both
   inequalities.

2. **Finite-size constant provenance.** Tie `_FINITE_SIZE_COEFF` in
   `sync_frame.py` to a measured `⟨R⟩` upper-quantile over ≥50 realisations at
   the actual `N` (INV-K5 is `statistical`), rather than a fixed `3.0`.

3. **Engine-layer R guard.** Add the `R∈[0,1]` (INV-K1) check to
   `order_parameter` in `kuramoto_ricci_engine.py` so the producer, not only
   the frame, fails closed on non-finite phases.

4. **Disconnected-spectrum honesty.** In `phase_transition_boundary`, surface
   `lambda_max_A == 0` as an explicit status/flag in `BoundaryReport` rather than
   a silent `Φ = −2γ` substitution, so a degenerate adjacency is observable.

5. **Domain-token binding.** Replace the string `PRICE_GRAPH_DOMAIN` gate in
   `ricci_trace.py` with a typed domain enum (mirroring `CausalCutoffStatus` in
   `physics_contracts/manifold/contracts.py`) so a typo cannot disable the κ≥−1
   bound.

6. **Multiple-comparison correction.** Apply Holm or BH-FDR across the four
   controls in `negative_controls.py::assemble_comparison_report` before
   declaring `SURVIVED_NULLS` (closes the 2026-04-30 S3.3 backlog row).

7. **Replay/falsifier executability cross-check.** In `evidence_binding.py`,
   validate `falsifiers_passed` against the ids in
   `governance/FALSIFIER_LEDGER.yaml` and that `replay_command` is a parseable
   argv, not just non-empty.

8. **Gauss–Bonnet exactness scope.** `ricci_trace.py` carries the GB residual as
   an exact `Fraction` and rejects any non-zero — confirm (in a witness, not
   prose) that `core.indicators.gauss_bonnet.gauss_bonnet_residual` actually
   returns ℚ-exact values for every graph the trace accepts, since a float leak
   upstream would defeat the exact-zero guard.

9. **Ott-Antonsen analytic anchor.** `phase_transition_boundary` is mean-field
   (Restrepo-Ott-Hunt); cross-validate Φ=0 against the exact OA steady state
   `R_∞ = √(1 − 2Δ/K)` (INV-OA2) on the Lorentzian case to anchor the network
   threshold to the analytic one.

10. **Dimensional contract.** Introduce a minimal typed-units guard for the
    thermodynamic laws (`thermo.landauer_bound`, `thermo.free_energy_descent`
    in `physics_contracts/catalog.yaml`) so `S_dimensional_consistency` can be
    *measured* rather than self-rated in `VERDICT.md`.

MISSING_TESTS_AND_FALSIFIERS:

* **Criticality finite-size scaling collapse** — no `N ∈ {8,16,32,64,128}`
  scaling-collapse witness wires into a gate; the 2026-04-30 audit
  (`docs/audit/2026-04-30-external-audit.md`, S4.1) named
  `experiments/criticality_fss/` as required and it is still backlog.
* **Multiple-comparison-corrected null survival** — no test exercises
  `negative_controls.py` survival under FWER/FDR correction.
* **`phase_transition_boundary` degenerate-adjacency falsifier** — no witness
  asserts the `lam_max <= 0` path is *flagged* rather than silently returning a
  verdict (`kuramoto_ricci_engine.py`).
* **`build_sync_frame` exact-criticality witness** — no test pins behaviour at
  `coupling_K == critical_K` (`sync_frame.py`).
* **Catalog-law → falsifier-ledger coverage gate** — nothing fails closed when
  a `physics_contracts/catalog.yaml` law has a witness but no promotion-blocking
  entry in `governance/FALSIFIER_LEDGER.yaml`.
* **Dimensional-units falsifier** — no test injects a unit error into a
  thermodynamic computation and asserts rejection.
* **Real-data null comparison beyond synthetic** — `governance/NEGATIVE_EVIDENCE.yaml`
  records the interbank Kuramoto null as untested on real e-MID/BIS data; the
  real-data path remains a registered *negative*, not a falsifier that ran.

FILES_TO_READ_FIRST:

1. `core/kuramoto/kuramoto_ricci_engine.py` — the #1096 INV-KR4 semantics split
   (`ricci_to_positive_adjacency`, `ricci_to_signed_coupling`,
   `assert_roh_compatible`) and the Restrepo-Ott-Hunt boundary.
2. `physics_contracts/manifold/sync_frame.py` — regime falsifiers, finite-size
   floor (defects 1, 2, 3).
3. `physics_contracts/manifold/ricci_trace.py` — flow-energy monotonicity and
   exact Gauss–Bonnet guard (defect 5, tightening 8).
4. `physics_contracts/manifold/evidence_binding.py` — claim-tier-above-evidence
   fail-closed rule (defect 7).
5. `physics_contracts/manifold/negative_controls.py` — the four-control battery
   (defect 6).
6. `.claude/physics/INVARIANTS.yaml` + `physics_contracts/catalog.yaml` — the
   112-invariant / 42-law registries (defect 8).
7. `governance/FALSIFIER_LEDGER.yaml` + `governance/NEGATIVE_EVIDENCE.yaml` —
   executable kill-tests and preserved negatives.
8. `tools/physics_score.py` + `VERDICT.md` — the self-reported 81.5/88–92 score
   (defects 9, 10).
9. `FORBIDDEN_CLAIMS.md` + `PRODUCT_CATEGORY.md` — the held product boundary.

IMMEDIATE_FIX_PR_ORDER:

1. **PR-A (fail-closed seams, P0):** engine-layer `order_parameter` R-guard +
   exact-criticality branch in `build_sync_frame` + `lam_max<=0` flag in
   `BoundaryReport`. Defects 1, 3, 4. Each gets a witness.
2. **PR-B (typed domain, P0):** replace `PRICE_GRAPH_DOMAIN` string gate with a
   typed enum in `ricci_trace.py`. Defect 5.
3. **PR-C (statistics, P1):** Holm/BH-FDR correction in `negative_controls.py`
   survival; closes 2026-04-30 S3.3. Defect 6.
4. **PR-D (coverage gate, P1):** fail-closed gate that every promotable
   catalog law has a `governance/FALSIFIER_LEDGER.yaml` entry. Defect 8.
5. **PR-E (evidence executability, P1):** cross-check `falsifiers_passed`
   against the ledger and validate `replay_command` in `evidence_binding.py`.
   Defect 7.
6. **PR-F (dimensional contract, P2):** typed-units guard for thermodynamic
   laws so `S_dimensional_consistency` is measured. Defects 9, 10.
7. **PR-G (criticality FSS, P2):** the `experiments/criticality_fss/` battery
   the 2026-04-30 audit (S4.1) still requires.

MERGE_BLOCKERS:

* Any PR that touches `physics_contracts/` or `core/kuramoto/` must keep
  `python scripts/count_invariants.py` consistent across all five surfaces
  (`invariant-count-sync` gate; currently **112**).
* No PR may convert a `governance/NEGATIVE_EVIDENCE.yaml` entry into a
  positive/promotion verdict (`scripts/ci/check_negative_evidence.py`).
* No PR may move the Ricci-microstructure claim above `Not Deployable`
  (`FORBIDDEN_CLAIMS.md`) without a multi-session real-data artifact with
  hashes, seed, and null-baseline (`PRODUCT_CATEGORY.md` Promotion Invariant 5).
* `tools/physics_score.py` `FINAL_PHYSICS_VALIDATION: NO` / `MERGE_READY: NO`
  (`VERDICT.md`) is a **stop rule**: no document may assert the physics layer is
  "validated" while the oracle reports below its `88–92` target.
* The product boundary (`PRODUCT_CATEGORY.md`, `FORBIDDEN_CLAIMS.md`,
  `scripts/ci/check_claim_boundary.py`) must stay green — no alpha / live-trading
  / market-law claim may enter the canonical surface.

RESEARCH_UPGRADE_PATH:

1. **From contract to claim.** The manifold contracts are excellent *gates*;
   the upgrade is real-data evidence that *passes* them — a `Measured-Single`
   then `Measured-Multi` artifact (`FORBIDDEN_CLAIMS.md` tiers) for the
   Ricci-microstructure line with hashes, seed, cost model, and FDR-corrected
   null superiority.
2. **Analytic anchoring.** Pin the network Restrepo-Ott-Hunt boundary
   (`kuramoto_ricci_engine.py`) to the exact Ott-Antonsen steady state
   (INV-OA2) and Strogatz `K_c = 2γ` so the threshold has an analytic witness,
   not only a sign-of-Φ regime test.
3. **Statistical rigor.** FWER/FDR across the four-control battery, plus a
   power analysis tying `n_null_draws` (floor 200 in `negative_controls.py`) to
   a target minimum detectable effect.
4. **Dimensional typing.** Adopt a units layer for the thermodynamic and Kelly
   laws so dimensional consistency is a *theorem of the type system*, not a
   self-rating in `VERDICT.md`.
5. **Coverage convergence.** Grow `governance/FALSIFIER_LEDGER.yaml` toward
   one promotion-blocking kill-test per promotable law in
   `physics_contracts/catalog.yaml`, gated fail-closed.

FINAL_STATUS:

**PASS-AS-RESEARCH-INFRASTRUCTURE / FAIL-AS-PROVEN-MARKET-PHYSICS.** The
audited surface is an honest, fail-closed verification platform that proves
invariants of its own computation and refuses to overclaim — #1096 closed a
genuine signed-curvature category error, #1123's claim guards hold, and the
product boundary is machine-enforced. It is **not** a validated market-physics
system, and the repository's own oracle agrees: `tools/physics_score.py` →
`81.5` vs `88–92`, `FINAL_PHYSICS_VALIDATION: NO` (`VERDICT.md`). The
ten defects above are *seams in enforcement and gaps in evidence*, not proven
mathematical errors; none promotes or weakens an existing claim. No physics
code and no claim state were modified to produce this audit.
