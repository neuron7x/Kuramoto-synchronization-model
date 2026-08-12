# D-002G P1 Design — Adversarial Audit (8-rung attack ladder)

## Anchor

- Worktree: `.claude/worktrees/agent-ab16f75f6b0367760`
- Branch: `feat/x10r-d002g-p1-implementation`
- Anchor commit: `3e92ce5` (D-002G pre-registration lock)
- Modules under audit (unstaged at audit start):
  - `research/systemic_risk/d002g_null_mechanisms.py` (611 LoC)
  - `research/systemic_risk/d002g_phase0_capsule.py` (142 LoC)
  - `research/systemic_risk/d002g_phase0_verification.py` (690 LoC)
  - `research/systemic_risk/d002g_r2b_gate.py` (375 LoC)
  - `research/systemic_risk/d002c_sweep_runner.py` (modified — schema constants only at audit start)

This audit attacks the **design as instantiated by these modules**, NOT the locked pre-registration contract. The pre-registration is the anchor; the modules implement it. The job is to find places where the implementation is weaker than the spec, or where the spec's bounds are themselves inferentially weak, and encode every survived attack as a failing-then-passing test (Phase B) before patching the modules (Phase C).

For every rung the verdict against the **current** implementation is recorded. After Phase C (repair) a second verdict (PATCHED) is appended in `D002G_P1_IMPLEMENTATION_REPORT.md`.

---

## R1 — Phase 0a "non-degeneracy" is checked only by `np.array_equal`

**Attack statement.** `d002g_phase0_verification.py:276` decides Phase 0a by `np.array_equal(K_p, K_null)`. Two `K` matrices with identical spectra (same eigenvalues, different eigenvectors) are NEAR-DEGENERATE for any spectrally-driven metric (`sync_auc`, `tau_onset`, anything driven by Kuramoto λ_max). Passing `array_equal=False` does NOT prove the M1 null and the precursor have distinguishable spectra.

**Why it matters.** The whole point of M1 is to break the spectrally-relevant degeneracy of bit-identical paired CRN. A test that only refuses byte-level identity admits a spectrally-degenerate null and rebuilds the D-002C pathology one floor up — the null audit collapses to p≈1 because the metric sees the two cohorts as the same dynamical system.

**Concrete experiment.** Construct a synthetic substrate that produces, at λ=0, a K_baseline whose null cohort is a random orthogonal conjugation of the precursor (same spectrum, permuted eigenvectors). `np.array_equal` would return False; the spectrum gap would be zero. A Kuramoto metric driven by λ_max would not distinguish.

**Verdict (pre-patch).** UNTESTED. Phase 0a is too weak.

**Test to add (Phase B).** `test_d002g_strike_R1_spectral_identity.py` — require `‖λ_sorted(K_p) − λ_sorted(K_n)‖_∞ > floor` AND KS-distance between eigenvalue distributions > floor across substrates and N. Floor calibrated from null-vs-null baseline + 3·MAD.

---

## R2 — M6 Frobenius preservation destroys spectral structure (conditional informativeness)

**Attack statement.** `d002g_null_mechanisms.py:451-460` constrains M6 placebo to **exactly** preserve the Frobenius norm of ΔK under random-site relocation. Frobenius norm is a sum-of-squares — it is invariant under arbitrary permutations of the off-diagonal magnitudes. The spectral structure (eigenvector localisation, block-diagonal alignment) is DESTROYED. The placebo's Kuramoto dynamics will not resemble the precursor's.

**Why it matters.** R2-B is supposed to test whether the metric responds to **energy** vs **topology**. If the metric is spectrally driven, M6 is a trivial fool: any spectrally-driven metric will reject the placebo regardless of substrate, so R2-B PASS does NOT certify "metric responds to topology, not just energy". Conversely, if the metric is topology-blind (e.g. mean absolute phase), M6 will fail to distinguish, so R2-B PASS DOES certify the property — but then the metric is useless for D-002G's hypotheses anyway. **M6 informativeness is CONDITIONAL on metric-topology coupling.** The implementation does NOT measure this coupling per (substrate, metric).

**Concrete experiment.** Build two synthetic metrics: (a) spectrally-driven (`λ_max(K)`-based scalar); (b) topology-blind (mean of |θ_j|). Run M6 placebo on both. The spectrally-driven metric should easily discriminate; the topology-blind metric should not. R2-B current code returns the same shape of capsule for both — it does not warn the consumer that the property certified is metric-dependent.

**Verdict (pre-patch).** UNTESTED. R2-B over-claims when the metric is spectrally driven; under-claims when it is topology-blind. Conditional-informativeness indicator missing.

**Test to add.** `test_d002g_strike_R2_m6_conditional_informativeness.py` — assert R2-B emits a topology-coupling indicator AND degrades verdict to `INDETERMINATE_R2B_TOPOLOGY_BLIND_METRIC` below the floor.

---

## R3 — Phase 0b paired t-test on bounded skewed metric

**Attack statement.** `d002g_phase0_verification.py:422-434` decides Phase 0b by `|t| < 2.0` over 50 paired seeds. Three flaws:

1. The t-statistic assumes Gaussian residuals. `sync_auc` is bounded on `[0, T·R_max]` (concrete: ~80 with R_max ≤ 1 and 80 steps), and `tau_onset` is right-censored at the window length. Distributions are skewed; t-test is mis-calibrated.
2. Across 9 cells (3 substrates × 3 N) the family-wise α inflates roughly to 9·0.05 ≈ 0.37 without Bonferroni/Fisher.
3. `|t| < 2.0` corresponds to two-sided p > 0.05 (z-quantile, not t-quantile at df=49, but close). Passing on **noise alone** is too easy — under truly null arrays the t-statistic is centred near 0 with std ≈ 1/√50 of nothing meaningful; the test under-discriminates real bias from drift.

**Why it matters.** Phase 0b is the gate that certifies M1 does not inject a systematic bias at λ=0. A test that passes too easily lets a biased M1 through; a downstream R1/R2 verdict would then carry a hidden offset.

**Concrete experiment.** Inject lognormal noise on the per-seed metric so the t-test (which assumes Gaussian) passes spuriously; Wilcoxon signed-rank (non-parametric) does not.

**Verdict (pre-patch).** FAILS. The current Phase 0b is too weak for bounded skewed metrics.

**Test to add.** `test_d002g_strike_R3_phase0b_robust.py` — drive Phase 0b with Wilcoxon signed-rank + bootstrap CI on mean(diffs), exercise the lognormal-noise distinguishing case.

**Verdict (post-patch, P1-3 Codex review):** DOWNGRADED. Path 2 chosen by user — contract downgraded to match implementation. Phase 0b uses **percentile bootstrap CI**, not BCa; therefore skew/bounded paired-difference calibration remains a LIMITATION. True BCa (bias-corrected accelerated) is future hardening. The Wilcoxon signed-rank gate (non-parametric) remains in the conjunction and absorbs most of the skew/bounded concern; the percentile CI is the secondary check. See `D002G_P1_IMPLEMENTATION_REPORT.md` §"P1-3 percentile bootstrap CI" for the verbatim limitation paragraph and `D002G_CANONICAL_RUN_BLOCKERS.md` §B2 for the canonical-run implication.

---

## R4 — Phase 0c rejects collapse but does NOT certify non-trivial discriminability

**Attack statement.** `d002g_phase0_verification.py:499` decides Phase 0c by `0.05 < p_empirical < 0.95`. A **uniform-p** degenerate null passes this band trivially while being **powerless** — it cannot detect any signal because the permutation distribution covers the unshuffled signal almost surely. Range-check is not power-check.

**Why it matters.** A degenerate null that PASSes Phase 0c convinces the operator that Phase 0 is satisfied, while the gate has zero ability to detect a precursor effect at λ>0. The canonical sweep would then run on a discriminability-poor design and emit a meaningless verdict.

**Concrete experiment.** Inject a known small effect (`δ = 0.1·σ`) into one arm of a paired array, run the permutation audit, measure detection rate at α=0.05. A passable Phase 0c gate must detect this rate ≥ 0.5 (low bar — purely additional, NOT replacing the range check).

**Verdict (pre-patch).** UNTESTED. Power calibration is missing.

**Test to add.** `test_d002g_strike_R4_phase0c_power.py` — encode a power-calibration helper that takes a (precursor, null) pair, injects δ = 0.1·σ, and requires detection rate > 0.5. Existing range check stays.

---

## R5 — `null_seed = base_seed + 10000` is arithmetic offset (collision-prone) AND only seed=42 is checked in Phase 0a

**Attack statement.**
- `d002g_null_mechanisms.py:476-477` and the locked formula `null_seed = base_seed + NULL_SEED_OFFSET` use simple arithmetic offset (offset = 10000, prereg). With Phase 0b's seeds 0..49, the null seeds are 10000..10049. If the substrate's PRNG state-space has any harmonic that aliases on a stride that divides 10000, two seeds in `{0..49}` could collide with their offset counterparts. NumPy's `default_rng(int)` uses SeedSequence internally so practical collisions are vanishing — but the principle is: arithmetic offset is **not** the right primitive for independent stream generation. The correct primitive is `np.random.SeedSequence(base_seed).spawn(2)`, which guarantees statistically independent streams.
- `d002g_phase0_verification.py:238-289` exercises Phase 0a with `base_seed=PHASE0_BASE_SEED=42` only. Phase 0b sweeps 50 seeds; Phase 0a sweeps 1. A single base seed can pass while the formula happens to collide on another seed.

**Why it matters.** Reproducibility-by-arithmetic looks deterministic but offers no statistical-independence guarantee. The prereg locks `null_seed_offset=10000` as INPUT; the implementation must use SeedSequence under the hood (mapping the offset into a spawn key) so independence is theoretically guaranteed.

**Concrete experiment.** For ALL seeds `0..49`, assert `not np.array_equal(K_p, K_n)` AND `‖K_p − K_n‖_F > N·eps`. Cheap; either the substrate is sensitive at every seed or it isn't.

**Verdict (pre-patch).** FAILS (partial). Phase 0a coverage is too narrow; offset arithmetic survives the cheap test but the test fixes the gap by sweeping 50 seeds.

**Test to add.** `test_d002g_strike_R5_seed_collision.py` — sweep all 50 seeds.

---

## R6 — Bonferroni-216 assumes test independence, but cells share K_0

**Attack statement.** `d002g_r2b_gate.py:282` records `bonferroni_alpha_per_cell = 0.05 / 216`. Cells at the same `(substrate, metric, N)` with varying `λ` share `K_0` (the baseline at λ=0). Strong dependence → effective number of independent tests ~36 (= 216 / 6 λ values), not 216. Bonferroni is over-conservative and inflates false-negative rate.

**Why it matters.** The pre-registration locks 216, so the implementation cannot change the divisor without breaking the contract. But the **report** must annotate the conservatism — otherwise downstream consumers read 0.05/216 = 2.31e-4 as a sharp threshold when the effective threshold is ~6e-4 under dependence. Implementation responsibility: emit the dependence diagnostic so consumers can adjust.

**Concrete experiment.** None at unit-test scope — this is a documentation/honesty rung. The implementation report MUST contain the annotation. Test: assert the report contains the annotation.

**Verdict (pre-patch).** UNTESTED (documentation deficit). Implementation locks divisor at 216 correctly; report must annotate.

**Test/action.** No code test required. The implementation report (Phase E) carries the annotation. This rung is recorded as "documented in report" rather than as a failing test.

---

## R7 — Joint distribution of (R1 ∧ R2 ∧ R3 ∧ R2-B) under H0 is uncharacterised

**Attack statement.** R1 (signal/CI), R2 (null-cohort FPR), R3 (direction stability), R2-B (placebo FPR) all depend on `signal_over_ci`. A metric that systematically inflates `signal_over_ci` passes R1 and **fails** R2-B simultaneously (the placebo also gets inflated `soc`). Without measuring this correlation, the verdict layer treats the four rules as if independent. They are not.

**Why it matters.** Two highly correlated rules acting like one defeat the multi-test discipline. A compromised metric could pass all four rules with a single bias.

**Concrete experiment.** Per cell, after R2-B aggregation, emit an empirical correlation matrix across rule-statistics (`signal_over_ci`, `null_signal_over_ci`, `placebo_signal_over_ci`, direction sign). Phase 0 must emit this as a diagnostic.

**Verdict (pre-patch).** UNTESTED. The correlation diagnostic is missing.

**Test to add.** `test_d002g_strike_R7_joint_distribution.py` — assert capsule emits a per-cell `rule_correlation_matrix` (square, diag = 1, no NaN, off-diagonal reported).

---

## R8 — Claim-boundary leakage: test Phase 0 ≠ canonical Phase 0

**Attack statement.** Phase 0 PASS in the **test suite** (synthetic substrates, possibly tweaked N) is NOT a canonical Phase 0 PASS on the locked prereg grid. The test substrates might have higher entropy or different spectral structure than the canonical run will see.

**Why it matters.** A PR body that says "Phase 0 PASSES" without a disclaimer would let downstream consumers read this as a scientific verdict. The PR is **infrastructure only**.

**Concrete experiment.** Test that the implementation PR body and the implementation report both carry the verbatim claim-boundary block (Phase E §9). Verify locked governance files were not mutated.

**Verdict (pre-patch).** UNTESTED. Documentation responsibility.

**Test to add.** `test_d002g_locked_governance_untouched.py` — hash the 7 locked files, compare against pinned shas, assert equality.

---

## Auxiliary rungs (added during deeper read)

### R9 — Phase 0a is M1-only; the placebo (M6) has no equivalent Phase 0a check

**Attack statement.** Phase 0a refuses bit-identical M1 nulls. M6 has no analogous Phase 0 check — its only contract is "Frobenius preserved" inside `_realize_m6`. If M6 happens to relocate every magnitude to its original site (extremely unlikely with `rng.choice(replace=False)` but not impossible at small N), the placebo equals the precursor.

**Verdict.** SURVIVES (M6 `replace=False` guarantees support inequality with probability 1 for N≥3). Not encoded as failing test; documented here for completeness.

### R10 — `realize_null` defaults to wall-clock `generated_at` inside the sha-excluded zone

**Attack statement.** `d002g_null_mechanisms.py:596` includes `generated_at=_now_iso()` in the dataclass; the sha excludes it. Confirmed at `_realization_sha` (line 263-289). SURVIVES.

---

## Plan-out

| Rung | Verdict (pre-patch) | Action | Repair site |
|------|---------------------|--------|-------------|
| R1   | UNTESTED  | Test + spectral helper + Phase 0a hardening | `d002g_null_mechanisms.py` (helper); test |
| R2   | UNTESTED  | Test + coupling indicator + verdict-gate | `d002g_r2b_gate.py` |
| R3   | FAILS     | Test + Wilcoxon + bootstrap CI in Phase 0b | `d002g_phase0_verification.py` |
| R4   | UNTESTED  | Test + power-calibration helper for Phase 0c | `d002g_phase0_verification.py` |
| R5   | FAILS (partial) | Test sweeping 50 seeds; SeedSequence under offset | `d002g_null_mechanisms.py` |
| R6   | Doc deficit | Annotation in Phase E report (no code test) | report only |
| R7   | UNTESTED  | Test + rule-correlation matrix in capsule | `d002g_phase0_verification.py` + capsule |
| R8   | UNTESTED  | Test + claim-boundary block + locked-files hash test | report + test |
| R9   | SURVIVES  | None | — |
| R10  | SURVIVES  | None | — |

Patch sites are tagged with `# Strike-Rx: ...` comments at landing.

## Post-patch verdicts

Filled in by `D002G_P1_IMPLEMENTATION_REPORT.md` after the test-construct + repair cycle.
