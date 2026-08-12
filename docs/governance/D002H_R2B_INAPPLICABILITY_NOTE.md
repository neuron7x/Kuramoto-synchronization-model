# D-002H R2-B Inapplicability Note

**Status:** RESOLVED — R2-B inherited-but-inapplicable under D-002H
**Anchor PR:** `docs/x10r-d002h-r2b-scope-clarification`
**Date:** 2026-05-14

---

## 1. Scope

This note resolves the R2-B applicability question for D-002H
canonical-run acceptance. It is a scope-clarification document, NOT a
contract change. D-002G acceptance rules remain byte-exact locked. The
D-002H pre-registration remains byte-exact locked. The D-002C claim
ledger remains byte-exact locked. This document does NOT change any
acceptance rule; it scopes the applicability of an inherited rule
(R2-B) to the D-002H canonical-run scope.

This note is also not a Gate H or Gate H-prime — the 7-gate
authorisation chain A..G is already closed at the locked Gate G final
lock artifact. This note is a SCOPE-DRIFT-RESOLUTION supplement
sha-pinned BEFORE any canonical-sweep PR opens, so the eventual
cell-verdict computation is unambiguous from the contract perspective.

---

## 2. The inherited rule (D-002G R2-B)

D-002G `D002G_ACCEPTANCE_RULES.md` §2 R2-B specifies, verbatim:

```
FPR_R2B(λ>0, M6 placebo) ≤ 0.05
```

with the following companion conditions:

- **NEW for D-002G.** Under M6 (placebo coupling at random edges with
  same Frobenius norm shift), the metric SHOULD NOT detect the fake
  precursor.
- `FPR_R2B` estimated as fraction of (substrate, metric, N, λ>0)
  cells under M6 with `signal_over_ci > 1`.
- Bonferroni-corrected per-cell α = 0.05 / 216.

R2-B therefore requires the M6 placebo coupling cohort to be
realisable at λ>0. The Bonferroni denominator (216) is the D-002C
inherited grid size; under D-002H scope the denominator becomes the
D-002H canonical grid size (18 cells = 1 substrate × 3 N × 6 λ),
which is what `D002H_PREREGISTRATION.yaml` `canonical_grid.total_cells`
records.

---

## 3. The structural conflict under D-002H scope

- `D002H_PREREGISTRATION.yaml` `null_mechanisms_allowed` is the
  set `[M1_INDEPENDENT_SEED, M3_TOPOLOGY_CONDITIONED]`.
- M6 placebo coupling is NOT in the allowed set.
- M6 was retired with `block_structured` + `temporal_coupling` per the
  D-002G structural-closure verdict (PR #682 merge anchor
  `8cf5364a3f3b605d8b134bccbfe5170098e0e197`).
- R2-B requires an M6 cohort at λ>0 to be evaluated; D-002H scope
  does not contain such a cohort.

Therefore R2-B is **STRUCTURALLY INAPPLICABLE** in D-002H. There is
no M6 row in the D-002H canonical sweep capsule by construction;
evaluating R2-B in D-002H would require synthesising an M6 cell that
the D-002H pre-registration forbids.

---

## 4. Resolution: INHERITED-BUT-INAPPLICABLE

> **R2-B INAPPLICABILITY UNDER D-002H SCOPE.** R2-B (FPR under M6
> placebo coupling) is inherited from D002G_ACCEPTANCE_RULES.md §2.
> Under D-002H scope, M6 is NOT in `null_mechanisms_allowed` (which is
> `[M1, M3]` only — per `D002H_PREREGISTRATION.yaml`). R2-B is
> therefore STRUCTURALLY INAPPLICABLE in D-002H. The D-002H
> canonical-run acceptance verdict is computed on the 4-term
> conjunction **R1 ∧ R2 ∧ R3 ∧ NULL_AUDIT** only. This documentation
> does NOT change D-002G acceptance rules (which remain byte-exact
> locked); it scopes their applicability to D-002H. Any future
> M3-based R2-B analogue would constitute a fresh D-002J
> pre-registration.

The verdict-computation conjunction term-count for D-002H is therefore
**4**, not 5. The dropped term is R2-B. The drop is structural, not
permissive: R2-B is unevaluable because the substrate × mechanism
conjunction that it requires (any × M6) is empty under D-002H scope.

---

## 5. Verdict-computation explicit table

For D-002H canonical-run cell-level verdict:

| Rule | Applicability | Threshold | Source |
|---|---|---|---|
| R1 (signal vs CI) | APPLICABLE | `\|signal_mean\| / CI_half_width > 1.0` | D002G_ACCEPTANCE_RULES.md §2 |
| R2 (FPR under M1 null at λ=0) | APPLICABLE | FPR ≤ 0.05 (Bonferroni-corrected) | D002G_ACCEPTANCE_RULES.md §2 |
| R3 (direction stability) | APPLICABLE | ≥ 0.80 | D002G_ACCEPTANCE_RULES.md §2 |
| R2-B (FPR under M6 placebo) | **INAPPLICABLE** (this document) | n/a — no M6 cohort in D-002H scope | this PR's scoping decision |
| NULL_AUDIT (post-sweep audit) | APPLICABLE | aggregate_verdict == PASS | D002G_ACCEPTANCE_RULES.md §2 |

Cell PASS iff R1 ∧ R2 ∧ R3 ∧ NULL_AUDIT all PASS. The Bonferroni
denominator on R2 is the D-002H canonical grid size (18 cells per
`D002H_PREREGISTRATION.yaml` `canonical_grid.total_cells`).

---

## 6. Anti-overclaim guards (inherited)

The three anti-overclaim guards from `D002G_ACCEPTANCE_RULES.md` §3
all continue to apply under D-002H scope:

- **MARGINAL_PASS** — every passing rule within 5% of its threshold
  triggers `MARGINAL_PASS_SYNTHETIC`; independent re-sweep required
  before any promotion.
- **SINGLE_PATH_PASS** — only one (substrate, metric) combination
  passes ⇒ claim scoped to that combination only; no generalisation.
- **NULL_AUDIT_FAIL** — any audited cell FAIL ⇒ verdict refused
  regardless of R1 / R2 / R3.

R2-B is removed from the anti-overclaim chain only because R2-B is
itself unevaluable; the remaining guards still bite on R1, R2, R3,
NULL_AUDIT.

---

## 7. Future evolution

A future PR that introduces an M3-based R2-B analogue (e.g. a shuffle
of ΔK across edges in a degree-preserving random graph constructed by
the M3 generator, with the precursor-specificity criterion enforced
against the M3 marginal set) would constitute a fresh **D-002J
pre-registration**. It would NOT be a patch to this document; it
would supersede it via the same pre-registration lock discipline that
D-002G → D-002H established.

The D-002J pre-registration document would carry its own anchor sha
at its merge commit, its own gate chain (A'..G' or equivalent), and
its own acceptance rules. This note would be referenced as the prior
scoping artifact that D-002J supersedes.

---

## 8. Forbidden interpretations

- ❌ "R2-B is dropped because it inconvenienced us." It is dropped
  because M6 is structurally excluded from D-002H scope by the
  pre-registration.
- ❌ "D-002G acceptance rules have been weakened." They remain
  byte-exact locked; only their scope of applicability under D-002H
  is clarified.
- ❌ "R2-B is replaced by an M3 analogue." It is NOT — only formally
  dropped. Any analogue requires fresh D-002J pre-reg.
- ❌ "D-002H acceptance is now permissive." It is still 4-term
  conjunction with Bonferroni correction; the only change is the
  conjunction count (4 instead of 5).
- ❌ "This note authorises a canonical sweep." It does NOT — Gate G
  already authorised the canonical sweep scoped to ricci_flow; this
  note clarifies the cell-verdict interpretation for the eventual
  sweep capsule.
- ❌ "This note edits the D-002G or D-002H locked artifact." It does
  NOT — both files remain byte-exact under their pinned sha256.

---

## 9. Claim boundary (verbatim)

> This document SCOPES R2-B inapplicability for D-002H canonical-run
> acceptance. It does NOT change D-002G acceptance rules. It does NOT
> authorise canonical sweep execution (Gate G already did, scoped to
> ricci_flow). It does NOT update D002C_CLAIM_LEDGER.yaml. Canonical
> sweep remains a separate downstream PR.

---

## 10. Cryptographic anchors (read-only)

Verified byte-exact at this PR's branch tip:

| Artifact | sha256 pin |
|---|---|
| `docs/governance/D002G_ACCEPTANCE_RULES.md` | `875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31` |
| `docs/governance/D002H_PREREGISTRATION.yaml` | `44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec` |
| `docs/governance/D002C_CLAIM_LEDGER.yaml` | `f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd` |

All three anchors are independently re-pinned in the contract test
`tests/systemic_risk/test_d002h_r2b_inapplicability.py` to guarantee
that the eventual canonical-sweep PR cannot retro-edit the rule
sources whose scope this note clarifies.
