# D-002G Acceptance Rules

**Locked at pre-registration merge.** Any post-merge edit is a
fresh pre-registration, not a mutation.

---

## 1. Tier mapping

| Outcome | Tier |
|---|---|
| All rules PASS at some cell + Phase 0 verification PASS | `SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN` |
| Any rule FAIL OR Phase 0 verification FAIL | `D002G_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET` |
| Infrastructure refusal (preflight, capsule sha mismatch, …) | `D002G_INFRASTRUCTURE_REFUSED` |

---

## 2. Rules (all must PASS at the SAME cell for tier PASS)

### R1 — Signal vs CI

```
|signal_mean| / CI_half_width > 1.0
```

- Inherited verbatim from D-002C.
- `signal_mean` = mean precursor metric value − mean null metric value.
- `CI_half_width` = (`bca_ci_hi` − `bca_ci_lo`) / 2.

### R2 — False-positive rate at non-degenerate null

```
FPR(λ=0, M1 null) ≤ 0.05
```

- **Redefined for D-002G.** Under M1 (independent-seed null
  cohort), the null cohort at λ=0 is NOT bit-identical to the
  precursor cohort.
- FPR estimated as fraction of λ=0 null cells with
  `signal_over_ci > 1`.
- Bonferroni-corrected per-cell α = 0.05 / `n_cells` (locked at
  216 for the canonical grid).

### R3 — Direction stability

```
direction stability ≥ 0.80
```

- Inherited verbatim from D-002C.
- At least 80% of seeds agree on sign of per-seed `signal_diff` at
  the selected cell.

### R2-B — Placebo coupling false-positive rate

```
FPR_R2B(λ>0, M6 placebo) ≤ 0.05
```

- **NEW for D-002G.** Under M6 (placebo coupling at random edges
  with same Frobenius norm shift), the metric SHOULD NOT detect
  the fake precursor.
- FPR_R2B estimated as fraction of (substrate, metric, N, λ>0)
  cells under M6 with `signal_over_ci > 1`.
- Bonferroni-corrected per-cell α = 0.05 / 216.

### NULL_AUDIT — Permutation null audit (executable)

```
post_sweep_null_audit.aggregate_verdict == "PASS"
```

- Inherited from C2.4-C2 + C2.4-A2 contract chain.
- `run_null_audit_all(sweep_capsule_path=ckpt)` with
  `n_shuffles=100`, `rng_seed=42`, `p_threshold=0.05`.
- Every audited cell must report `verdict=PASS`.
- `aggregate_only=true` is REFUSED in the post-sweep path.

---

## 3. Anti-overclaim guards (inherited from D-002C §7)

Same three guards apply:

- **MARGINAL_PASS** — every passing rule is within 5% of its
  threshold. Independent re-sweep with re-randomised substrate
  seed required before promoting beyond `MARGINAL_PASS_SYNTHETIC`.

- **SINGLE_PATH_PASS** — only one (substrate, metric) combination
  passes. Claim scoped to that combination ONLY; no
  generalisation.

- **NULL_AUDIT_FAIL** — any audited cell FAIL → verdict refused
  regardless of R1/R2/R3/R2-B.

---

## 4. Phase 0 pre-launch verification (HARD GATE)

Before any canonical D-002G sweep, three verification checks
**must** PASS per substrate × N:

### Phase 0a — Bit-identity broken

```python
realisation_p = substrate.realize(N=N, lambda_=0.0, seed=42)
realisation_n = substrate.realize_null(N=N, seed=42 + 10000)
assert not np.array_equal(
    realisation_p.K_baseline, realisation_n.K_baseline
)
```

### Phase 0b — H0 preserved

```python
# 50-seed paired null-vs-null comparison
diffs = []
for s in range(50):
    p = substrate.realize(N=N, lambda_=0.0, seed=s)
    n = substrate.realize_null(N=N, seed=s + 10000)
    diffs.append(metric.evaluate(simulate_kuramoto(p.K_baseline, seed=s)).value
                 - metric.evaluate(simulate_kuramoto(n.K_baseline, seed=s + 10000)).value)
# Null hypothesis: mean(diffs) == 0
t_stat = abs(np.mean(diffs)) / (np.std(diffs, ddof=1) / np.sqrt(50))
assert t_stat < 2.0  # p-value > 0.05 under t-distribution
```

### Phase 0c — Permutation discriminability is non-trivial

For each (substrate, N), run `run_null_audit` with
`n_shuffles=1000` on the null-vs-null paired arrays from Phase 0b:

```python
audit = run_null_audit(precursor_values=diffs[::2],
                      null_values=diffs[1::2],
                      n_shuffles=1000, rng_seed=42)
assert 0.05 < audit.p_value_empirical < 0.95
```

This rejects pathological collapse (p=0 or p=1) and confirms the
permutation distribution has finite width.

### Phase 0 acceptance

If ALL (substrate × N) cells pass 0a + 0b + 0c → Phase 0 PASS →
canonical sweep allowed.

If ANY cell fails → Phase 0 FAIL → fall back to mechanism M2
(topology-preserving shuffle) and restart Phase 0; if M2 also
fails, escalate to a new pre-registration (not edit).

---

## 5. Cell-grid scope (inherited from D-002C, re-asserted)

```
substrates:
  ricci_flow
  block_structured
  temporal_coupling

metrics:
  tau_onset
  sync_auc
  phase_lag

N_grid: [50, 100, 200]
lambda_grid: [0.0, 0.05, 0.10, 0.20, 0.40, 1.0]
n_seeds: 20
n_bootstrap: 16

total_cells = 3 × 3 × 3 × 6 = 162
multiple_testing_correction:
  method: bonferroni
  n_cells: 216 (inherited from D-002C grid)
  effective_alpha_per_cell: 0.05 / 216 = 2.31e-4
```

---

## 6. Out-of-scope rules (NOT applied)

D-002G does **NOT** apply:

- D-002C R2 in its original paired-CRN bit-identical form
  (degenerate, falsified in attempt-2; replaced by R2 redefined
  above under M1).
- Any rule that was NOT in this acceptance document at the merge
  commit of the pre-registration.

---

## 7. Verdict derivation

The verdict deriver (`research/systemic_risk/d002c_verdict.py` or
a new `d002g_verdict.py` if extension is cleaner) must:

1. Iterate cells with λ > 0 as candidates.
2. Per candidate cell: evaluate R1, R3.
3. Per candidate cell: evaluate R2 over matching λ=0 null cells
   using **M1 null cohort**.
4. Per candidate cell: evaluate R2-B over **M6 placebo cohort**.
5. Per candidate cell: pull null-audit verdict from emitted capsule.
6. If R1 ∧ R2 ∧ R3 ∧ R2-B ∧ NULL_AUDIT all PASS → selected_cell.
7. Apply MARGINAL_PASS / SINGLE_PATH_PASS guards.
8. Emit `verdict.json` with tier per §1 above.

---

## 8. Cryptographic anchors (at pre-registration merge)

The merge commit of this pre-registration PR is the anchor. After
merge, the locked sha256 over `D002G_PREREGISTRATION.yaml` is the
contract identity. Subsequent edits create a fresh anchor.

---

## 9. Forbidden interpretations (re-asserted)

- ❌ "D-002G validates D-002C" — they are SEPARATE contracts.
- ❌ "D-002G PASS lifts D-002C attempt-2 falsification" — no.
  Attempt-2 falsification is preserved append-only.
- ❌ "D-002G PASS = real-data / bank-level / production" — never.
- ❌ "we can edit D002C_PREREGISTRATION.yaml after D-002G"
  — never.
- ❌ "tau_onset / phase_lag are validated by D-002G" — only the
  combos that survive POS preflight + R2-B are in scope.

---

## 10. Required next PRs (post pre-registration merge)

| Order | PR | Scope |
|---|---|---|
| 1 | **Implementation PR** | substrate API extension (`realize_null`, M6 site-random) + sweep_runner routing + R2-B gate + Phase 0 tests |
| 2 | **Canonical D-002G run** | fresh RUN_DIR, Phase 0 PASS, full sweep, post-sweep null audit, verdict |
| 3 | **D-002G freeze docs** | run report + claim ledger append-only entry |

This pre-registration PR is **#0** — locks the contract.

---

## 11. Rollback

If this pre-registration is judged methodologically unsound after
merge:

1. Open a NEW pre-registration document (e.g.
   `D002H_PREREGISTRATION.yaml`).
2. Do NOT edit `D002G_PREREGISTRATION.yaml`.
3. Reference this D-002G as superseded in the new document.

Same discipline as D-002C → D-002G transition.
