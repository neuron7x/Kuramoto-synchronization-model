# D-002G Non-Degenerate Null Design

**Class.** Pre-registered redesign protocol (falsification contract).
**Date.** 2026-05-12.
**Status.** D-002C attempt-2 was falsified by executable null audit;
D-002G is the redesigned null-mechanism contract.
**Hard invariant.** `INV-IDENTIFICATION-1` remains globally active.

> **This document is a falsification contract, not a promise of
> success.** D-002G may PASS, FAIL, or be infrastructure-REFUSED.
> Each outcome has equal scientific dignity. The only forbidden
> outcome is post-hoc threshold tuning or YAML rescue.

---

## 1. Why D-002G exists

D-002C attempt-2 (RUN_ID `d002c_canonical_attempt_2_20260512T160318Z`)
ran the C2.4-A2 + C2.4-C2 + C2.4-D contract chain end-to-end and
emitted `tier = D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET`.

The 9 FAIL cells were exactly the λ=0 cohort. Under the locked
paired-CRN protocol, at λ=0 the substrate produces
`K_precursor == K_baseline` **bit-identically** — the Kuramoto
integrator yields identical R(t), per-seed metric values are
identical, the permutation test reports p=1.0 (zero
discriminability), and the aggregator emits `verdict=FAIL`.

This is the **expected and correct** behaviour of a fail-closed
permutation null audit applied to a **degenerate null cohort**.
The system caught its own false confidence.

D-002G is the redesign of the null mechanism so that:

1. The λ=0 cohort is **not** bit-identical to the precursor cohort.
2. The null hypothesis "no precursor effect at λ=0" is still
   preserved.
3. Permutation null audit can produce non-trivial discriminability
   measurements.
4. The pre-registered acceptance rule (R1 ∧ R2 ∧ R3 + null audit)
   can produce a SCIENTIFICALLY MEANINGFUL pass/fail.

D-002G does NOT rescue D-002C. The D-002C ledger entries remain
append-only and unchanged. D-002G is a SEPARATE contract.

---

## 2. Non-goals (re-asserted)

D-002G must NOT:

- ❌ Edit `docs/governance/D002C_PREREGISTRATION.yaml`.
- ❌ Reinterpret or remove attempt-1 / attempt-2 ledger entries.
- ❌ Modify R1, R2, R3 numeric thresholds.
- ❌ Change verdict tier strings shared with D-002C.
- ❌ Claim D-002G has validated D-002C.
- ❌ Claim real-data, bank-level, production, or universal
  certification.
- ❌ Promote a D-002G PASS to anything beyond
  `SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN`.
- ❌ Run the canonical D-002G sweep on the substrate API as-is
  without first verifying the chosen null mechanism is
  non-degenerate (Phase 0 below).

---

## 3. Diagnosis matrix — why each redesign option might work

| Mechanism | Removes bit-identical collapse? | Preserves H0 (no precursor at λ=0)? | Cost |
|---|---|---|---|
| **M1** Independent-seed null cohort | ✓ ω, θ₀, integrator stream all differ | ✓ K is still the baseline matrix | Loses paired-CRN variance reduction at λ=0 only |
| **M2** Topology-preserving shuffled null | ✓ graph edges rewired with degree preservation | ✓ degree sequence preserved (mean coupling same) | Requires new substrate `realize_shuffled` API |
| **M3** Seed-permuted CRN null | ✓ same seed within run but permuted between precursor and null | ✓ baseline distribution invariant under permutation | Subtle — need careful permutation that preserves marginal stats |
| **M4** λ-independent baseline perturbation | ✓ small bounded random additive jitter on K | ✓ mean perturbation = 0 preserves H0 | Need to pin perturbation amplitude to NOT swamp signal |
| **M5** Block-resampled precursor null | ✓ resample R(t) blocks within trajectory | ✓ block-level statistical properties preserved | Block-size selection becomes new hyperparameter |
| **M6** Placebo coupling null | ✓ inject "fake precursor" on random edges (not top-10%) | ✓ same Frobenius norm shift, just wrong locations | Requires substrate.realize() to accept random injection sites |

### Selected primary mechanism: **M1 (independent-seed null cohort)** + **M6 (placebo coupling)** as R2-B supplementary gate

**Rationale:**

- **M1** is the minimal-intervention fix that directly attacks the
  bit-identical collapse. Loss of paired-CRN variance reduction at
  λ=0 only (λ>0 cells retain CRN). It's the cleanest baseline
  comparison to D-002C attempt-2.
- **M6** as R2-B supplementary gate addresses the harder question:
  "if I inject a precursor in the WRONG places, does the metric
  still detect it?" A passing R2-B implies the metric is detecting
  the precursor TOPOLOGY, not just any Frobenius-norm shift.
- The combination provides BOTH false-positive (M1) and
  false-discovery (M6) control under genuinely informative null.

Fallback mechanism: **M2 (topology-preserving shuffle)** if M1+M6
empirically fail Phase 0 verification.

---

## 4. Pre-launch verification protocol (Phase 0)

**MANDATORY before any canonical D-002G sweep.** Without this, the
redesign is just words.

### Phase 0a — bit-identity check

Run a tiny test that exercises the new substrate API and verifies:

```python
# For each substrate × N, with the M1 null mechanism:
substrate = ResolveSubstrate(id)
realisation_precursor = substrate.realize(N=N, lambda_=0.0, seed=42)
realisation_null = substrate.realize_null(N=N, seed=99)  # different seed under M1
assert not np.array_equal(
    realisation_precursor.K_baseline, realisation_null.K_baseline,
)  # bit-identity broken
```

Acceptance: every (substrate, N) combo passes this check.

### Phase 0b — H0 preservation check

For each substrate × N, with the M1 null:

```python
n_seeds = 50
diffs = []
for s in range(n_seeds):
    p = substrate.realize(N=N, lambda_=0.0, seed=s)
    n = substrate.realize_null(N=N, seed=s + 10000)
    metric_p = AucPreEventMetric().evaluate(simulate_kuramoto(p.K_baseline, seed=s))
    metric_n = AucPreEventMetric().evaluate(simulate_kuramoto(n.K_baseline, seed=s + 10000))
    diffs.append(metric_p.value - metric_n.value)

# H0 preservation: per-seed diff distribution should be symmetric around 0
assert abs(np.mean(diffs)) < 3 * np.std(diffs) / np.sqrt(n_seeds)  # t-test on mean=0
```

Acceptance: H0 cannot be rejected at the locked α=0.05 for ALL
(substrate, N) cells **before** the canonical sweep.

### Phase 0c — permutation test discriminability check

For each substrate × N, run a tiny smoke permutation test:

```python
run_null_audit(precursor_values, null_values, n_shuffles=1000, rng_seed=42)
```

Acceptance:
- p-value distribution is NOT collapsed to 1.0.
- 90% of the null cohort cells produce p ∈ [0.05, 0.95] under H0
  (proper null behaviour, not pathological).

---

## 5. R2-B inside D-002G

R2-B is **not** run as a separate science path. It is the
supplementary null gate **inside** the D-002G acceptance rule
(see `D002G_ACCEPTANCE_RULES.md`).

R2-B mechanism: **M6 placebo coupling**. For each (substrate,
metric) combo:

1. Generate a "fake precursor" with the same Frobenius norm shift
   as the locked precursor mechanism, but applied to a RANDOM
   subset of edges (NOT the top-10% curvature edges for Ricci,
   NOT the inter-block edges for block_structured, NOT the locked
   sites for temporal_coupling).
2. Run the metric on this fake precursor.
3. Under H0 (the metric detects topology not just energy):
   FPR_R2B ≤ α_bonferroni.

If R2-B FPR > α_bonferroni → metric is a false-positive prone
detector that responds to any energy injection. The cell is
EXCLUDED from the canonical D-002G claim.

---

## 6. Acceptance rule (formal)

See `D002G_ACCEPTANCE_RULES.md` for the full numeric form. Summary:

D-002G tier `SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN` iff ALL:

| Rule | Threshold | Source |
|---|---|---|
| R1 | `\|signal_mean\| / CI_half_width > 1.0` at some cell | inherited from D-002C |
| R2 | `FPR(λ=0) ≤ 0.05` under M1 non-degenerate null | redefined for non-bit-identical null |
| R3 | direction stability ≥ 0.80 | inherited |
| **R2-B** | `FPR_R2B ≤ 0.05` under M6 placebo coupling at the selected cell | NEW supplementary gate |
| **Null audit** | every audited cell `verdict=PASS` under M1 null | required, non-trivial permutation |

If ANY rule fails → tier `D002G_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET`.

---

## 7. Forbidden outputs (re-asserted)

```
SYNTHETIC_GATE6_CERTIFIED                       (unqualified)
REAL_DOV_READY
VALIDATED_REAL_BANK_LEVEL_RESULT
BANK_LEVEL_PRECURSOR_CONFIRMED
"D-002G validates D-002C"  (no claim cross-promotion)
any tier not in {SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN,
                 D002G_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET,
                 D002G_INFRASTRUCTURE_REFUSED}
```

---

## 8. Killed hypotheses preserved

The D-002C attempt-1 PASS-shape result is NOT resurrected by
D-002G. The attempt-2 falsification is NOT walked back. The
append-only ledger remains intact.

D-002G ADDS a new claim entry (after its canonical run completes)
with its own RUN_ID, its own preregistration_sha, its own
verdict_sha, and explicit `not_a_validation_of_D002C` cross-link.

---

## 9. Implementation cost estimate

| Component | Effort |
|---|---|
| Substrate API extension: `realize_null(N, seed)` per substrate | 4 modules × ~50 LoC |
| M1 null mechanism: 3 substrate implementations | inline in `realize_null` |
| M6 placebo coupling: new substrate parameter `precursor_sites="placebo"` | ~30 LoC per substrate |
| Phase 0 verification tests | 3 test files × 5-10 tests each |
| Sweep runner: route null cohort through `realize_null` at λ=0 | ~40 LoC |
| R2-B gate inside verdict deriver | ~80 LoC |
| Pre-registration documents (this PR) | 3 files |
| Acceptor + falsifier | 1 file |
| **Implementation PR (separate)** | ~5-7 days focused work |
| **Canonical D-002G sweep (after merge)** | ~3-15 min on E-core |

---

## 10. Process discipline

This PR contains ONLY the pre-registration document set:

```
docs/governance/D002G_PREREGISTRATION.yaml
docs/governance/D002G_NONDEGENERATE_NULL_DESIGN.md
docs/governance/D002G_ACCEPTANCE_RULES.md
.claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml
```

The implementation PR (substrate API + null mechanism + R2-B gate
+ tests + canonical run) is a SEPARATE PR that lands after this
pre-registration is merged.

**The merge commit of this PR is the anchor.** After that, the
pre-registration YAML is locked. Any subsequent edit constitutes
a FRESH pre-registration (with a fresh content-addressed sha),
not a mutation of the existing contract.

This is the same discipline applied to D-002C. We do not learn by
re-writing what we wrote yesterday; we learn by writing what we
write today next to it.

---

## 11. Reproducibility envelope (pre-committed)

| Parameter | Value | Source |
|---|---|---|
| substrate_seed | 42 | inherited from D-002C canonical |
| n_seeds | 20 | inherited |
| n_bootstrap | 16 | inherited |
| N_grid | [50, 100, 200] | inherited (N ≤ 200 fence preserved) |
| lambda_grid | [0.0, 0.05, 0.10, 0.20, 0.40, 1.0] | inherited |
| n_shuffles (null audit) | 100 | inherited from C2.4-C2 |
| n_shuffles_R2B | 100 | NEW for D-002G |
| placebo_random_seed (M6) | 99 | NEW for D-002G |
| null_seed_offset (M1) | 10000 | NEW for D-002G |
| ci_method | bca_bootstrap | inherited |
| ci_alpha | 0.05 | inherited |
| multiple_testing_correction | bonferroni on 216 cells | inherited |
| direction_stability_min_fraction | 0.80 | inherited |
| signal_ci_ratio_threshold | 1.0 | inherited |
| direction_consistency_min_seeds | 3 of 20 | inherited |
| expected_wallclock_hours_p95 | 0.5 (E-core single-thread) | scaled from attempt-2 |
| forbidden_to_post_hoc_change | this document set | non-negotiable |

---

## 12. Claim boundary on this pre-registration

This pre-registration document set establishes the CONTRACT for
D-002G. It does NOT:

- ❌ Run any sweep
- ❌ Emit any verdict
- ❌ Modify the D-002C claim ledger
- ❌ Resurrect or validate attempt-1
- ❌ Walk back the attempt-2 falsification

It DOES:

- ✓ Lock the redesign mechanism (M1 + M6 R2-B)
- ✓ Specify Phase 0 pre-launch verification
- ✓ Specify the new acceptance rule (R1+R2+R3+R2-B+null audit)
- ✓ Pre-commit forbidden_outputs
- ✓ Establish the merge commit as content-addressed anchor

The path to a D-002G synthetic PASS requires:

1. THIS pre-registration merges (locks the contract).
2. Separate implementation PR ships the substrate API + null
   mechanism + R2-B gate + Phase 0 tests.
3. Canonical D-002G sweep runs under the locked contract.
4. Post-sweep executable null audit reports PASS.
5. R2-B gate reports PASS.
6. Verdict deriver applies all rules → tier.
7. New claim ledger entry (append-only) records the outcome.

D-002G is a contract for HONEST inquiry, not a guarantee of any
particular result.
