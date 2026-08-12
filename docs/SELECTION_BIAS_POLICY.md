<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Selection-Bias & Multiple-Testing Policy (RES-007)

## Purpose

GeoSync promotes exactly one **flagship** research question
(`research/flagship/rq.yaml` — `FLAGSHIP-RQ-001`). Its answer rests on a small
programme of tried configuration variants (the RES-008 baseline hierarchy). This
policy controls the **researcher-degrees-of-freedom** in that programme: it
forbids cherry-picking the best of several runs, and it requires the number of
comparisons to be recorded and the final inference to use the **pre-specified
primary** comparison — not a post-hoc best pick.

It is enforced by the fail-closed gate `scripts/ci/check_selection_bias.py`
(tests in `tests/ci/test_selection_bias.py`) over the report
`artifacts/research/selection_bias_report.json`.

## Boundary (inherited, unchanged)

This is an **infrastructure / synthetic-only** question under
`RESEARCH_ALPHA_SYNTHETIC_ONLY_NO_DEPLOY`. The decision variable is a
**deterministic census count** `D_marginal` read from a frozen repository/build
artifact — **not** a sampled market return.

> **This is NOT a market backtest.** Deflated-Sharpe and CSCV/PBO are market
> constructs and do **not** apply here. We adapt the *idea* honestly: the
> **family** is the set of tried variants/baselines/ablations, and the risk is
> cherry-picking the best run or running many comparisons without correction. No
> return, PnL, Sharpe, or edge metric is admissible (see `FORBIDDEN_CLAIMS.md`).

## The family

The family of hypotheses is the set of tried wheel-contract **configuration
variants**, each tested for marginal detection over the **preregistered null
baseline** `EXISTING_SUITE` (the in-place gate suite; prereg
`nulls.primary_null` / `nulls.null_reference`):

| Member | Role | marginal `D` | one-sided permutation `p` |
| --- | --- | --- | --- |
| `FLAGSHIP` | **pre-specified primary** | 70 | `1/(B+1)` ≈ 9.999e-05 |
| `NAIVE` | control (definitional 0) | 0 | 1.0 |
| `ABLATED` | ablation (clean-archive step removed) | 0 | 1.0 |
| `SHUFFLED` | label-shuffle null control | 0 | 1.0 |

`EXISTING_SUITE` is the **null reference** the family is tested against, so it is
not itself a family member. **Family size = 4. `selection_count = 4`.**

### Decision statistics and the randomization null

The outcome is a deterministic census count, so classical sampling p-values are a
category error. Significance is assessed against the preregistered **label-shuffle
permutation null** (`SHUFFLED` tier): each first-party namespace label is replaced
by a random stdlib token and the flagship rule re-applied. Because the stdlib pool
contains **zero** first-party namespaces, every one of `B` relabelings yields 0
first-party hits, so the one-sided permutation p-value is **exact**:

```
p = (#{perm_stat >= observed_stat} + 1) / (B + 1)
  = 1 / (B + 1)     when observed_stat > 0   (e.g. FLAGSHIP: 70 > 0)
  = 1.0             when observed_stat == 0   (NAIVE / ABLATED / SHUFFLED)
```

with `B = 10000`.

## Multiple-testing correction

The frozen preregistration declares `multiple_testing_corrections: none_required`
(a single pre-specified primary). This policy **adds** the correction machinery as
**defence-in-depth** — it does not amend the frozen plan (no new `prereg_id`).
Even when the four variants are conservatively treated as a family, the primary
conclusion is unchanged.

At family-wise `alpha = 0.05`, `m = 4`:

- **Bonferroni** threshold `= alpha/m = 0.0125`.
- **Holm** threshold at ascending rank `i` `= alpha/(m − i + 1)`.
- **Benjamini-Hochberg (FDR)** threshold at rank `i` `= (i/m)·alpha`.

Sorted raw p-values `[9.999e-05, 1.0, 1.0, 1.0]`. Under all three procedures,
**exactly one** hypothesis is rejected — `FLAGSHIP_vs_EXISTING_SUITE`, the
pre-specified primary. The ablation and both null controls correctly fail to
reject. This is the **opposite** of a best-of-N artifact: the surviving result is
the one registered in advance, and the failing variants are recorded, not hidden.

## No cherry-pick

The FINAL inference uses the **pre-specified** primary comparison
(`FLAGSHIP` vs the preregistered `EXISTING_SUITE` null), fixed **before** any run
in `FLAGSHIP-PREREG-001`. It is not a post-hoc best-of-N pick. Every tried variant
and its raw decision statistic / p-value is recorded in the report; the three
non-primary variants are not reinterpreted as the headline result.

## Honesty: no manufactured significance

The correction controls selection bias in the **marginal-detection** leg
(H1: `D_marginal ≥ 1`), which survives family-wise and FDR correction. Surviving
correction does **not** upgrade the study verdict. `FLAGSHIP-RQ-001` stays
**`INSUFFICIENT_EVIDENCE`** (per RES-008) because the **separate** preregistered
reproducibility-at-S leg is unverified — a criterion **orthogonal** to
multiplicity that the correction neither addresses nor can rescue. No `SUPPORTED`
result is fabricated, and the frozen snapshot S / final holdout is untouched.

## What the gate enforces (fail-closed)

`scripts/ci/check_selection_bias.py` exits **RED** when:

1. the report's declared primary ≠ the preregistered primary
   (`FLAGSHIP` vs the primary-null tier, both derived from `hierarchy.yaml`);
2. `selection_count` is unrecorded, non-integer, negative, or inconsistent with
   the number of listed comparisons;
3. a best-of-N / post-hoc primary is presented **without** a valid
   multiple-testing correction, or the primary is not flagged `pre_specified`;
4. `final_verdict` does not match the RES-008 comparison verdict (a corrected
   conclusion inflated past `INSUFFICIENT_EVIDENCE`).

Exit codes: `0` clean, `1` a selection-bias violation, `2` a required file
absent/malformed (fail-closed).

## Amending the analysis

Scope, comparator, primary, and criteria are frozen at the pinned commit. Any
post-hoc change to the family, the primary, or the correction plan requires a
**new study** with a **new `prereg_id`** (see `PREREGISTRATION_POLICY.md`).
