# Disha → D-002C connector

**Class.** Architectural cross-reference. Not a claim.
**Date.** 2026-05-11.
**Anchor commits:** D-002B-A ledger sha256
`e3b9d0a4daa553485e7123bdbe325ca4e9c3c4a9cf46499208087e3910321362`
(pragma: allowlist secret); Disha artifact PR #590 / #592 lineage.

This file makes one specific architectural statement:

> The Disha country-level co-movement corridors are
> *predictive substrate-design priors* for the D-002C
> block-structured substrate hypothesis. They are not
> evidence inputs to any D-002C verdict.

If the next sweep's block-structured substrate finds
detectability at N ≤ 200 along block boundaries that mirror
the Disha corridors, that is *predictive emergence* across
two independent observables — not a circular fit.

If it does not, the prior is discarded. That is the test.

---

## 1. What Disha provides (descriptive only)

From `figures/disha_ba_correlation/`:

| Corridor | Pearson r (log-changes, 2007Q1–2009Q4, n_eff=11) |
|---|---|
| DE–FR | 0.910 |
| DE–LU | 0.906 |
| GB–US | 0.872 |
| CH–GB | 0.865 |
| BE–NL | 0.836 |

Hub set (article-rank top 7 + IE; combined strength and
co-movement criterion): `{GB, DE, FR, LU, US, IE, NL, BE}`.

Disha is country-level aggregate exposure data. n_eff = 11.
Descriptive co-movement only. **No bank-level claim. No
contagion claim. No mechanism claim.** This is the only
shape of input from Disha to D-002C: corridor pairs and hub
identities, treated as topological priors.

---

## 2. What D-002C block-structured substrate looks like

Per `docs/governance/D002C_PREREGISTRATION.yaml` §3 H1:

```
substrate: block_structured
param_grid:
  n_blocks:       [2, 3, 4]
  inter_block_p:  [0.05, 0.10, 0.20]
  intra_block_p:  [0.60, 0.80]
```

The substrate is a synthetic block-graph with controlled
inter-vs-intra block density contrast. The block partition is
specified *before* the sweep runs.

---

## 3. The Disha-informed block partition (priors, not claims)

For one block-count cell (n_blocks = 3), the following
partition is a candidate topology motivated by the Disha
corridors:

```
Block 1 — Continental Europe cluster:
    DE, FR, LU, BE, NL
    (justified by DE-FR 0.91, DE-LU 0.91, BE-NL 0.84
     stress-window co-movement corridors)

Block 2 — Anglo-American cluster:
    GB, US, IE
    (justified by GB-US 0.87 corridor; IE included on
     article-rank co-movement criterion)

Block 3 — Cross-block bridge:
    CH
    (justified by CH-GB 0.87 corridor crossing the GB
     cluster boundary)
```

This partition is *one of several* tried in the n_blocks = 3
cell. Other partitions (e.g. random, modularity-optimised,
modular-spectrum) are also swept in the D-002C grid. The
Disha partition does not get preferential treatment in the
verdict rule.

---

## 4. The non-circular test

The D-002C verdict rule (per pre-reg §4) is:

```
∃ N ≤ 200, substrate, metric: |signal|/CI > 1
AND FPR(λ=0) ≤ 0.05
AND direction stability ≥ 0.80
```

If the rule passes on the Disha-informed partition **but not
on other partitions tried in the same cell**, that supports
the predictive-emergence reading. If it passes on multiple
partitions, the Disha link is non-discriminative (still
useful but weaker). If it fails on the Disha partition while
passing elsewhere, the Disha link is null. All three
outcomes are reported per the secondary metrics in
pre-reg §4.

**This is what makes the connection falsifiable instead of
correlational.**

---

## 5. What this file does NOT do

- Does **NOT** claim Disha corridors are causally related to
  any precursor signal.
- Does **NOT** lift INV-IDENTIFICATION-1.
- Does **NOT** make a real-data Gate 6 prediction (no
  real-data verdict on Disha's BIS LBS country aggregates is
  attempted at this stage).
- Does **NOT** override the pre-registration. If the Disha
  partition fails the rule, that result stands.

---

## 6. Reproducibility envelope

| Item | Source |
|---|---|
| Disha corridor numbers (§1) | `figures/disha_ba_correlation/top_correlated_pairs_changes.csv`, mode=changes, period=sensitivity_2007Q1_2009Q4 |
| Disha hub set (§1) | `figures/disha_ba_correlation/risk_concentration_article_grade.csv`, article-rank top 7 + IE |
| Disha audit (independent) | `/tmp/disha_delivery/DISHA_ARTICLE_PACK.md` audit report (2026-05-11, adversarial mode, PARTIAL_PASS → PASS after 3 edits) |
| D-002C protocol | `docs/governance/D002C_PREREGISTRATION.yaml` |
| D-002B-A boundary | `docs/governance/X10R_BOUNDARY_CARD.md` |

---

## 7. The honest reading

> Disha gives us 5 country-level co-movement corridors
> (descriptive, n_eff = 11). D-002C will test whether a
> synthetic block-graph with those corridors as block
> boundaries lets Gate 6 detect a precursor at N ≤ 200
> without breaking fail-closed. The test is pre-registered.
> If it works, that is non-trivial because the two data
> sources (Disha real BIS LBS aggregates; D-002C synthetic
> block-graph Kuramoto sims) share no methodology. If it
> doesn't work, the prior is discarded and D-002C tries
> other partitions (random, modular-spectrum). No claim
> survives without the rule passing on the live sweep.

That is the entire architectural statement.
