# D-002H Canonical Run Report -- ricci_flow scope

**Schema:** `D002H-CANONICAL-RUN-REPORT-v1`
**Artifact:** `artifacts/d002h/canonical/d002h_canonical_run_verdict.json`
**Run ID:** `d002h_ricci_flow_canonical_v1_2026-05-14`
**Anchor main SHA:** `ee12a9e6a08e5916109c99eec84796d1e1375cd0` (R2-B clarification merge)
**Scope:** `ricci_flow` substrate only.

---

## 1. Anchor + governance posture

This report records the D-002H canonical-sweep execution on the
`ricci_flow` substrate, downstream of the closed 7-gate authorisation
conjunction A AND B AND C AND D AND E AND F AND G (Gate G terminal at PR
#689, `4686455e...`) and the R2-B inapplicability clarification (PR #690,
`ee12a9e6...`).

Locked governance anchors (byte-exact at run time):

| Artifact | sha256 anchor |
|---|---|
| `docs/governance/D002G_ACCEPTANCE_RULES.md` | `875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31` |
| `docs/governance/D002H_PREREGISTRATION.yaml` | `44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec` |
| `docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md` | (locked at PR #690 merge) |
| `docs/governance/D002C_CLAIM_LEDGER.yaml` | `f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd` |

The sweep refuses launch on any anchor drift; observed anchors are
recorded inside the sweep capsule (`anchors_observed` block).

## 2. Grid (locked, byte-exact from D-002H prereg)

| Axis | Values |
|---|---|
| substrate | `ricci_flow` (only) |
| N | `50, 100, 200` |
| lambda | `0.0, 0.05, 0.10, 0.20, 0.40, 1.0` |
| metrics evaluated | `tau_onset, sync_auc, phase_lag` (inherited from D-002C/G) |
| n_seeds | `20` (precursor cohort, `base_seed=42..61`) |
| n_bootstrap | `16` (BCa CI on per-seed signal diffs) |
| total cells (canonical) | `18 = 3N x 6 lambda` |

Reproducibility seeds (pinned in `D002H_PREREGISTRATION.yaml`):

| Constant | Value |
|---|---|
| `base_seed` | `42` |
| `null_seed_offset_M1` | `10000` |
| `null_seed_M3` | `12345` |
| `M3_TOPOLOGY_CONDITIONED_SALT` | `523` |

## 3. Mechanism + acceptance conjunction

Null mechanisms used: `M1_INDEPENDENT_SEED`, `M3_TOPOLOGY_CONDITIONED`.

`M2_*` and `M6_PLACEBO_COUPLING` are NOT in `null_mechanisms_allowed`
under D-002H scope (per prereg). R2-B (FPR under M6) is therefore
STRUCTURALLY INAPPLICABLE under D-002H -- see
`docs/governance/D002H_R2B_INAPPLICABILITY_NOTE.md`.

Cell PASS iff:

```
R1 AND R2 AND R3 AND NULL_AUDIT
```

per the 4-term conjunction documented in the R2-B inapplicability note
(R2-B is omitted because M6 is structurally excluded from D-002H scope).

| Rule | Source | Threshold |
|---|---|---|
| R1 (signal vs CI) | `D002G_ACCEPTANCE_RULES.md` Section 2 | `\|signal_mean\| / CI_half_width > 1.0` |
| R2 (FPR under M1 null at lambda=0) | `D002G_ACCEPTANCE_RULES.md` Section 2 | `FPR <= 0.05/216 = 2.315e-4` (Bonferroni-corrected) |
| R3 (direction stability) | `D002G_ACCEPTANCE_RULES.md` Section 2 | `>= 0.80` |
| R2-B (FPR under M6) | `D002H_R2B_INAPPLICABILITY_NOTE.md` | **INAPPLICABLE** (M6 not in scope) |
| NULL_AUDIT | `D002G_ACCEPTANCE_RULES.md` Section 2 | `aggregate_verdict == PASS`; `n_shuffles=100`, `rng_seed=42`, `p_threshold=0.05` |

Bonferroni denominator `n_cells = 216` inherited verbatim from D-002G.

## 4. Runtime

See top-level verdict capsule for the recorded runtime + peak RSS:

```
artifacts/d002h/canonical/d002h_canonical_run_verdict.json
  -> runtime_seconds_total
  -> peak_rss_MB
```

Per-cell wallclock is preserved in the sweep capsule
(`artifacts/d002h/canonical/results/d002h_ricci_flow_canonical_v1_2026-05-14/sweep_capsule_v1.json`)
under `evaluations_M1[*].wallclock_seconds` and `evaluations_M3[*].wallclock_seconds`.

## 5. Per-cell verdict table (18 cells)

The authoritative machine-readable per-cell table is the
`per_cell_verdicts` array in the per-run verdict capsule
(`artifacts/d002h/canonical/results/<RUN_ID>/verdict.json`). Each entry
carries the 3-metric breakdown (R1, R2, R3, NULL_AUDIT per metric) and
the cell-level verdict.

A cell verdict is:

- `PASS` -- some metric within the cell passes R1 AND R2 AND R3 AND NULL_AUDIT.
- `FAIL` -- no metric satisfies the conjunction at lambda > 0.
- `INDETERMINATE_LAMBDA_ZERO_NULL_COHORT` -- the three lambda=0 cells per N
  are the null cohort by construction (no precursor injection); they feed
  R2 FPR estimation at lambda > 0 but cannot themselves PASS.

The aggregate cell counts are summarised in the top-level verdict
capsule (`n_cells_pass`, `n_cells_fail`, `n_cells_indeterminate`).

## 6. Aggregate verdict

The aggregate verdict tier is one of (locked enum):

| Tier string | Trigger |
|---|---|
| `SYNTHETIC_GATE6_CERTIFIED_D002H_REDESIGN` | `>= 1` cell PASS clean AND all anti-overclaim guards green |
| `MARGINAL_PASS_SYNTHETIC_D002H` | passing cell exists but every passing rule is within 5% of its threshold |
| `D002H_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET` | no cell PASS |
| `REFUSED_NULL_AUDIT_FAIL_D002H` | NULL_AUDIT_FAIL on any cell -- refused regardless of R1/R2/R3 |

The realised tier + aggregate verdict are emitted byte-exactly into the
top-level verdict capsule (`tier_string`, `aggregate_verdict` fields).
Refer to the capsule for the current run's verdict.

Anti-overclaim guards (per `D002G_ACCEPTANCE_RULES.md` Section 3, all
continue to apply under D-002H scope per the R2-B inapplicability note
Section 6):

- `MARGINAL_PASS` -- every passing rule within 5% of its threshold.
- `SINGLE_PATH_PASS` -- only one (substrate, metric) combination passes.
- `NULL_AUDIT_FAIL` -- any audited cell FAIL -> tier `REFUSED_*`.

## 7. Claim boundary (verbatim)

> This report records the D-002H canonical sweep verdict on the
> `ricci_flow` substrate per the 7-gate authorisation conjunction
> (closed at PR #689) and the R2-B inapplicability clarification (PR
> #690). The aggregate verdict tier is recorded byte-exactly in
> `artifacts/d002h/canonical/d002h_canonical_run_verdict.json`. Verdict
> is SCOPED to `ricci_flow` only; does NOT generalise to
> `block_structured` or `temporal_coupling` (structurally excluded by
> D-002G structural closure). This report does NOT update
> `D002C_CLAIM_LEDGER.yaml`; ledger update is a SEPARATE downstream PR.

## 8. Forbidden interpretations

- ❌ "D-002H canonical sweep validates D-002C or D-002G." It does NOT.
  D-002G is structurally closed; D-002H is a fresh pre-registered
  lineage scoped to `ricci_flow`. Whatever D-002H reports is scoped to
  D-002H.
- ❌ "D-002H verdict generalises across substrates." It does NOT --
  scope is `ricci_flow` only per prereg `substrate_scope.included`.
  `block_structured` and `temporal_coupling` are structurally excluded
  by D-002G closure (seed-deterministic K_baseline).
- ❌ "This PR appends to the D-002C claim ledger." It does NOT. The
  ledger remains byte-exact at sha256
  `f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd`.
  Any ledger update is a SEPARATE downstream PR that consumes this
  verdict.
- ❌ "D-002H verdict is bank-level / real-data / production." It is
  NOT. The substrate is a synthetic test-bed; the verdict scope is
  synthetic-redesign per the inherited tier-string enum.

## 9. Reproduction

```
PYTHONPATH=. python scripts/x10r_d002h_canonical_sweep.py
```

Expected: exit `0`; artifacts written to
`artifacts/d002h/canonical/d002h_canonical_run_verdict.json` and
`artifacts/d002h/canonical/results/d002h_ricci_flow_canonical_v1_2026-05-14/`.
Anchor sha verification refuses launch on any drift.
