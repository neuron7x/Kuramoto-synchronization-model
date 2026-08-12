# D-002C Attempt-2 — Executable Null-Audit Falsification Report

## 1. Run identity

- **Run class:** `D002C_CANONICAL_SYNTHETIC_SWEEP_ATTEMPT_2_EXECUTABLE_NULL_AUDIT`
- **RUN_DIR:** `tmp/d002c_canonical_attempt_2_20260512T160318Z`
- **Main HEAD at run:** `5c5393e` (post-C2.4-A2 merge)
- **Sweep exit code:** `0` (sweep itself completed cleanly)
- **Final verdict tier:** `D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET`
- **Wallclock (sweep):** 151.6s on E-core (8–13) throttled, single-thread BLAS

## 2. Stage-by-stage outcome

| Stage | Result | Note |
|---|---|---|
| Preflight POS | 3 PASS / 6 EXCLUDE | excludes all `tau_onset` + `phase_lag` combos |
| Preflight NEG | 23 PASS / 4 EXCLUDE | overlaps POS exclusions |
| Preflight SMOKE | PASS | 36/36 cells |
| Pre-sweep null_audit | `aggregate_only=true`, results=[] | bootstrap only |
| Sweep R1∧R2∧R3 (pre-null-audit) | **45/45 PASS** | tier=PASS would be emitted |
| **Post-sweep null audit** | **FAIL** | **9 / 54 cells (all λ=0)** |
| Final verdict re-derived (`null_audit_failed=True`) | `D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET` | tier=FAIL |

## 3. Cryptographic anchors

| Anchor | sha256 |
|---|---|
| preregistration_sha | `b1561ddde08a60a8eed416f2103655e0f3ee1ecd4e2b2037f4e7193c424a154e` |
| sweep_sha (pre-null-audit) | `9abd7ca683f2c0f769496b471bad39462730a2971d7e17d05368fc1d13948473` |
| null_audit_capsule_sha (post-sweep) | `7d5404d1e9714e79…` |
| verdict_sha (final, null_audit_failed=True) | `b427f22419bf7866b8913cd76bc31572d5dd6c48a64950dd597904829fd4df48` |
| archive_sha256 | `f0fbea551dd0c4b74d1ec231a73c1f0917de16f6b15e24921e68c7706fc029f9` |

## 4. Why the FAIL — scientifically

The 9 FAIL cells are **exactly** the λ=0 cohort cells: 3 substrates × 3 N values × 1 (λ=0) = 9.

Under the C2.3-locked paired-CRN protocol, at λ=0 the substrate
`realize(N=N, lambda_=0.0, seed=s)` produces `K_precursor` element-wise
identical to `K_baseline` (the "null trajectory has no precursor"
invariant pinned by substrate tests). Therefore:

- the Kuramoto integrator runs twice on bit-identical K → identical R(t) trajectories
- per-seed metric values: `precursor_values[i] == null_values[i]` for every seed
- permutation shuffle: every shuffled draw is also bit-identical → `|shuffled diff|` distribution collapses
- empirical p-value = 1.0 (zero discriminability)
- aggregator correctly emits per-cell verdict=`FAIL`

This is the **expected behavior** of a fail-closed null-audit safeguard on a
**degenerate null cohort** — and it is exactly what the
`D002C_R2_STRUCTURAL_LIMITATION_NOTE.md` predicted under P0 freeze:

> R2 is mechanically satisfied for ALL evaluated λ=0 cells under
> paired CRN because K_precursor == K_baseline bitwise. ... has
> limited evidential strength as an independent false-positive
> safeguard until redesigned or supplemented.

The C2.4-A2 contract operationalised this prediction — the
permutation test now PROVES it on real per-seed paired data.

## 5. Relationship to attempt-1

| | attempt-1 | attempt-2 |
|---|---|---|
| RUN_ID | `d002c_canonical_20260512T122837Z` | `d002c_canonical_attempt_2_20260512T160318Z` |
| Main HEAD | `98ef559` (pre-C2.4-A2) | `5c5393e` (post-C2.4-A2) |
| sweep_runner emits per-seed payload | ❌ NO | ✅ YES |
| Post-sweep null_audit executed | ❌ aggregate_only bootstrap only | ✅ real per-cell audit |
| R1∧R2∧R3 result | 45/45 PASS | 45/45 PASS (same) |
| null-audit outcome | NOT exercised | **9/54 FAIL** |
| Final tier | `SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200` | `D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET` |
| Status | `SUPPORTED_SYNTHETIC_SCOPED` (defensible at the time) | **`FALSIFIED_BY_EXECUTABLE_NULL_AUDIT`** |

Attempt-1 was technically defensible at the time it was recorded —
the executable null-audit safeguard did not yet exist. Attempt-2,
once the safeguard exists, **eclipses** attempt-1: the same R1∧R2∧R3
pattern that was reported as PASS in attempt-1 is now shown to ride
on a structurally degenerate null cohort.

**Both entries remain in the claim ledger.** Append-only history is
the truth here, not a revision. Attempt-1 is not deleted; it is
historically situated.

## 6. Operational truth

- The sweep did NOT fail. The sweep exited cleanly with the same
  R1∧R2∧R3 result as attempt-1.
- The locked acceptance contract did NOT fail. R1, R2, R3 each
  PASSED at every evaluated cell.
- What FAILED is the meta-safeguard: the executable null audit
  said "your null cohort is not statistically distinguishable from
  your precursor cohort". That is a methodological refutation of
  the implicit assumption underlying the R1∧R2∧R3 PASS.

This is exactly what the C2.4-A2 + C2.4-C2 + C2.4-D contract chain
was designed to surface. The system caught its own false
confidence.

## 7. Claim boundary

The new claim_id (append-only) records:

```
status: FALSIFIED_BY_EXECUTABLE_NULL_AUDIT
tier:   D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET
```

Forbidden interpretations (re-asserted):
- ❌ "attempt-1 PASS still holds" — eclipsed by attempt-2
- ❌ "sync_auc evidence survives null shuffle" — falsified at λ=0
- ❌ "narratively rescue verdict by re-tuning thresholds"
- ❌ "promote to real-data validation"
- ❌ "universal / cross-asset / bank-level inference"
- ❌ "production certification / external certification"

## 8. Next required work

Operator decision branch (drafted in `D002G_DEGENERATE_NULL_REDESIGN_SPEC.md`):

1. **D-002G** — redesign the null mechanism so that λ=0 substrate
   dynamics are mechanistically distinct from λ>0 (NOT bit-identical).
   This is the canonical fix.

2. **R2-B supplementary null** (already specified in
   `D002C_R2_B_SUPPLEMENTARY_NULL_SPEC.md`) — five candidate
   mechanisms (label-shuffle, seed-permutation, phase-randomized,
   topology-preserving graph-randomised, amplitude-preserving
   shuffled precursor).

3. **NOT permitted:** retroactive edit of `D002C_PREREGISTRATION.yaml`
   to flip the verdict.

## 9. Reproducibility envelope

This run was executed twice within session:
- Once via spawned sub-agent (worktree, archive cleaned)
- Once directly in `canon7` (this run, archive preserved as
  `tmp/d002c_canonical_attempt_2_20260512T160318Z.tar.gz`)

The SCIENTIFIC outcome is identical across both runs:
9 FAIL cells, all at λ=0, p=1.0 by construction. Cryptographic
anchors differ across the two runs because `generated_at`
timestamps are folded into per-cell shas; this is expected and
documented. The reproduced run's anchors above are authoritative.
