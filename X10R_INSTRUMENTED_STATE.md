# X-10R — INSTRUMENTED STATE

**X-10R is currently in INSTRUMENTED state. No bank-level claims
are allowed on real data until both (a) the country-to-bank
allocator's synthetic certificate is issued AND (b) the X-10R
reconstruction's synthetic certificate is issued AND (c) a Gate 6
forward signal lands on the composed certificate.**

This file is the canonical audit surface for every binding
discipline rule the X-10R stack imposes. Each item below points
to the merged PR + commit + tested invariant that pins the rule
in regression.

---

## Discipline rules pinned in code

### 1. Synthetic-vs-real boundary is hard-coded

Real BIS LBS marginals get ZERO recovery test. The strongest
available gate on real data is **domain-of-validity** — do real
inputs fall inside the regime where synthetic recovery has been
demonstrated?

- **PR #635** (sha `f580c33`) FIX B2 — `recovery_audit.check_domain_of_validity`
- **INV-RECONSTRUCTION-2** is the named invariant
- `assert_real_data_status_legal` raises `ValueError` if real-data
  path emits `GROUND_TRUTH_RECOVERED`
- Test pin: `test_real_data_path_emits_within_or_out_never_recovered`

### 2. Mathematical contract on weight allocation is correct

Naive gravity rule
`w_ij = a_ij·s_i^out·s_j^in / W_total` does NOT preserve
`E[Σ_j w_ij] = s_i^out` once the support of `A` is sparsified.

The production allocator uses Almog-Squartini 2017 IPF
(Sinkhorn-Knopp) projection on the realised support of A, which
enforces the marginals exactly post-hoc.

- **PR #635** FIX B1 — `weighted_allocation.allocate_weights` docstring
  corrected; implementation already used IPF
- **Empirical certification**: `test_naive_gravity_does_not_preserve_marginals_on_sparse_support`
  proves the claim falsifiably (naive gravity loses ≥ 10 % row mass
  on sparse supports; IPF is ≥ 10× tighter)

### 3. Reciprocity-aware controls

Density-only sweep is insufficient for spectral recovery (the
quantity Gate 6 inherits via `_normalise_to_unit_spectral_radius`
and `_kc_lorentzian_proxy`).

- **PR #641** (epic X-10R-2, sha `15068b0`) `compute_reciprocity_ratio` +
  `reciprocity_keep_p_for_target` + `_apply_reciprocity_filter`
  + `reciprocity_keep_p` parameter on every ground-truth generator
- **PR #641** `run_reciprocity_aware_recovery` walks a
  `(reciprocity × density)` grid; `tested_at_reciprocity` is
  populated only on PASS
- Closed issue #636

### 4. Allocator is a separate testable unit

`research/reconstruction/allocator/` (8 source modules + 7 test
modules + 128 tests):

| PR | sha | Module |
|---|---|---|
| #642 (X-10R-1 PR #1) | `fe204b7` | foundation: `AllocatorPrior`, `UniformPrior`, `CountryToBankAllocator`, `BankLevelMarginalsCertificate`, synthetic |
| #643 (X-10R-1 PR #2) | `d129b1e` | `SizeWeightedPrior` + `registry_to_bank_country_map` |
| #644 (X-10R-1 PR #3) | `d63026b` | `BankLevelGate5Audit` (4-metric report) |
| #645 (X-10R-1 PR #4) | `a36adf9` | `load_mfi_registry` (TSV/CSV ingestion) |
| #646 (X-10R-1 PR #5+#6) | this PR | demo fixture + composed DoV gate |

Four allocator-side gates pinned:

- **GATE_A1** — conservation per country (Σ shares ≡ 1 to 1e-9 rel)
- **GATE_A2** — `coverage_ratio` surfaced as evidence (NOT fail-closed
  on the allocator side; consumed by the *composed* gate at PR #6)
- **GATE_A3** — non-negative shares + non-negative emitted marginals
- **GATE_A4** — bit-exact replay via sha256 `cert_id`

### 5. Composed Domain-of-Validity gate (PR #6 in this PR)

Bank-level admissibility requires BOTH the X-10R reconstruction
DoV verdict AND the allocator-side coverage envelope. The gate
emits a 4-cell verdict (`BOTH_WITHIN` / `RECONSTRUCTION_OUT` /
`ALLOCATOR_OUT` / `BOTH_OUT`). Only `BOTH_WITHIN` is admissible.

**Admissibility ≠ validation.** Two distinct properties on the
verdict:

- `is_admissible_for_downstream_bank_level_test` — True iff
  `BOTH_WITHIN`. Gates the *next-step test* (Gate 6 forward
  signal in epic PR #7), NOT a bank-level claim.
- `is_scientifically_validated_bank_level_result` — hard-coded
  `False` at this layer; flipped True only by Gate 6 PASS in
  epic PR #7.

`coverage_ratio ≥ 0.80` is **necessary, not sufficient.**

### 6. Synthetic positive control with injected precursor

`research/reconstruction/positive_control.py` ships:

- 3 ground-truth substrates (BA, CP, hierarchical) at N=200
- 4-density sweep `(0.03, 0.05, 0.08, 0.12)`
- Reciprocity-aware sweep `(0.30, 0.60, 1.00)` (PR #641)

Gate 6 (`kuramoto_on_reconstruction.gate_6_precursor_discriminative`)
explicitly injects a Kuramoto R(∞) precursor and bootstraps the
ΔR distribution against a topology-randomised null. The PASS
predicate is "95 % CI of ΔR excludes the `[-min_gap, +min_gap]`
zone". `min_gap` defaults to 0.05.

### 7. Empirical certification of recovery

Multi-seed multi-substrate empirical recovery summary lands in
`X10R_EMPIRICAL_RECOVERY_SUMMARY.md` (committed in PR #635):

- 20 cells (substrate × N × seed)
- **18/20 PASS = 90 %** Gate 5 recovery rate
- ρ relative error: median 0.075, p95 0.183
- top-k hub jaccard: median 1.000

### 8. Provenance vs admissibility separation

Every certificate dataclass distinguishes *provenance fields*
(populated for auditability, NOT gate-driving) from *gate fields*
(consumed by an explicit threshold check):

- `RecoveryReport.failure_reasons` (gate) vs `mean_strength` (provenance)
- `BankLevelMarginalsCertificate.coverage_ratio` (gate) vs
  `n_banks` / `n_countries` / `prior_id` / `fallback_policy` (provenance)
- `ComposedDomainCheck.allocator_checks` (gate) vs `allocator_measured` (provenance)
- `tested_at_*` evidence surface tuples (provenance) vs
  `valid_for_*` intent surface (declarative)

### 9. INV-IDENTIFICATION-1 stays in force

The bank-level inference claim is FORBIDDEN until ALL of:

1. Allocator GATE_A1–A4 pass (PR #642–#645 — done)
2. Reconstruction Gate 5 + Gate 6 pass on synthetic ground truth
   (PR #635 — done)
3. Composed DoV gate emits `BOTH_WITHIN` (PR #6 in this PR — done)
4. **Gate 6 forward signal on the *bank-level reconstructed network*
   PASSES** (epic PR #7 — STILL DEFERRED)

Item 4 is the missing piece. Until it lands, the X-10R-1
country-to-bank allocator stack is **INSTRUMENTED, NOT
VALIDATED**.

### 10. INSTRUMENTED state declaration

(This document is the declaration. Top-of-file paragraph quotes
it verbatim.)

---

## What is NOT pinned in this PR

The following items are explicitly out of scope for this PR.
They are tracked in `ISSUE_DRAFTS_X10R.md` and as GitHub issues
#636–#640:

- Real ECB MFI dataset ingestion (license-clean download path)
- Real EBA transparency size weights
- Moody's BankFocus / Orbis Bank Focus (license-gated)
- BIS CBS reconstruction comparison (X-10R-3 epic)
- RO-Crate / OSF / AsPredicted governance layer (X-10R-4 epic)
- E2E allocator → reconstruction → Gate 6 forward signal (epic
  PR #7 — final epic PR; lifts the INSTRUMENTED state)

---

## 10-point ILS-2026 audit (per PR #646 review)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Replace demo-fixture illusion | **Documented**: hermetic + license-clean, NOT validation | this file §1 |
| 2 | Real prior for fitness model | **Interface ready, real data deferred** | PR #643 SizeWeightedPrior; PR #645 mfi_loader |
| 3 | Mathematical correctness of weight allocation | **Done** | this file §2; PR #635 FIX B1 |
| 4 | DoV gate replaces "recovery on real data" | **Done** | this file §1; PR #635 FIX B2 |
| 5 | Reciprocity constraint | **Done** | this file §3; PR #641 |
| 6 | Allocator as separate testable unit | **Done** | this file §4; PRs #642–#646 |
| 7 | Reduce LoC and boilerplate | **Out of scope here** — the foundation cannot be < 350 LoC and still satisfy items 1–9; reduction lands as a separate refactor PR after item 10 lands |
| 8 | Synthetic positive control with injected precursor | **Done** | this file §6 |
| 9 | Forbid real-data verdicts before synthetic certificate | **Done** | this file §9; INV-IDENTIFICATION-1 |
| 10 | INSTRUMENTED state declaration | **Done** | this file (the declaration paragraph at the top) |

---

## How to flip from INSTRUMENTED to VALIDATED

The flip is a single named event: the Gate 6 forward signal
on the bank-level reconstructed network passes against a
topology-randomised null at the published `min_gap = 0.05`,
bootstrapped over ≥ 8 ω-seeds, on a real BIS LBS run that
already cleared the composed DoV gate.

That signal is owned by epic PR #7. When it lands, this file's
top paragraph will be amended to read **VALIDATED**, the
`is_scientifically_validated_bank_level_result` property will
be wired to that Gate 6 verdict, and `INV-IDENTIFICATION-1` will
be lifted in the same commit.

Until then: **no bank-level claims.**
