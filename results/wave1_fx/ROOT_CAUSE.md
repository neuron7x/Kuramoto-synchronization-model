# Wave 1 · combo_v1 FAIL · Root-Cause — Evidence-Tiered

**Verdict:** FAIL.  **No Wave 2.**
**Workspace SHA (complete run):** `3214612f59b56059c7b9a668baec047e1f0c793a`
**GeoSync SHA at lock:** `8b68156df48f1d8ec7566a8db57fb71a66cf8622`
**OOS window:** 2008-01-02 → 2026-02-09 · 4704 bars · 222 folds

> Note: this file supersedes the narrative root-cause written at commit
> `3214612`. The earlier version mixed proven outcomes with plausible
> mechanisms. This rewrite separates the two and is machine-grepable by
> tier (`### PROVEN`, `### PLAUSIBLE`, `### RULED_OUT`). Audits in
> `results/wave1_fx/audits/` promote PLAUSIBLE → PROVEN only when their
> own labels say `SUPPORTED`.

---

## PROVEN

Every claim in this section is computable directly from
`results/wave1_fx/run_*/summary.json`, `folds.csv`, `per_target_fold.csv`,
`portfolio_equity.csv`. Anyone can reproduce the numbers from those
CSVs with 10 lines of pandas.

### P1. combo_v1 Sharpe on the 8-FX panel is statistically indistinguishable from zero, gross

- Run A (gross, cost_bps=0): **median fold-median Sharpe = −0.0046**
  across 222 folds.
- Fold-median Sharpe distribution (Run A): mean −0.08, std 0.74,
  min −2.53, max +2.03.
- Positive-fold fraction (gross): 45.9 %.
- Cost drag A → B is ΔSharpe = −0.041.

Interpretation: the magnitude of the Sharpe change from removing all
costs is of the same order as the median itself. Even the
"best-case-zero-cost" regime has no economic signal. Formal null
comparison is deferred to `audits/null_portfolio_audit.md`.

### P2. Three of four preregistered gates fail decisively in Run B

| gate | value | threshold | outcome |
|---|---:|---:|---|
| median fold-median Sharpe | −0.0457 | ≥ 0.80 | FAIL |
| % folds with positive median Sharpe | 43.2 % | ≥ 60 % | FAIL |
| max DD (OOS portfolio) | 0.4488 | ≤ 0.20 | FAIL |
| 2022-touching folds median Sharpe (n=15) | +0.1964 | ≥ 0 | pass |

Three failures; one pass. Per `PREREG.md §4`, this is FAIL.

### P3. combo_v1 does not beat naive baselines

Run B OOS (2008-01-02 → 2026-02-09):

| strategy | Sharpe | max DD |
|---|---:|---:|
| combo_v1 (1-bar lag, net) | −0.0457 | 0.4488 |
| buy-and-hold equal-weight 8-FX | **−0.0427** | **0.1618** |
| combo with 2-bar lag (net) | −0.1529 | 0.4230 |

Buy-and-hold delivers essentially the same Sharpe at **36 % of the
drawdown**. On Run B's own metric there is no regime in which
combo_v1 dominates buy-and-hold.

### P4. Per-asset contribution is sign-heterogeneous with wide spread

Run B per-asset aggregate Sharpe across 222 folds:

| asset  | mean | median |
|--------|---:|---:|
| USDJPY | +0.251 | +0.321 |
| GBPUSD | +0.089 | −0.060 |
| AUDUSD | −0.008 |  0.000 |
| EURJPY | −0.018 | +0.078 |
| EURGBP | −0.149 | −0.051 |
| USDCAD | −0.196 | −0.295 |
| EURUSD | −0.282 | −0.121 |
| USDCHF | −0.636 | −0.510 |

Spread of means: −0.636 to +0.251 (range 0.89), larger than the
magnitude of any individual mean. Cross-asset structure of the
strategy is not uniformly monetizable: gains on one target are
absorbed by losses on another.

### P5. Costs are not the dominant failure mode

Run A (gross) also fails: median Sharpe −0.005, positive-fold frac
45.9 %, max DD 0.4061. Removing costs would not convert FAIL → PASS
on any of the three failing gates.

### P6. 2022 pass is a within-sample median-of-15 — not a robust crisis edge (in its own terms)

The 15 folds touching 2022 have portfolio-level Sharpes spanning
**[−1.95, +2.69]** (`run_b_net/folds.csv`, column
`fold_portfolio_sharpe`). The positive median is driven by fall-2022
folds 182–184 (+2.48, +2.69, +2.42) offsetting spring-2022 folds
176–178 (−1.69, −1.95, −1.83). Even conditional on the 2022 subset,
the run is whipsaw-dominated; the gate passes only because the
**median** smooths those whipsaws.

**Important:** §4 of the preregistration makes 2022 one of four gates
it does not rank-order them. Since the other three gates fail, no
mechanical or admissible interpretation of "2022 passes" promotes the
result to PASS. The 2022 finding is reported and not up-weighted.

---

## PLAUSIBLE BUT NOT YET PROVEN

Every claim here is a mechanism hypothesis. Each is labelled
`⇒ AUDIT_X` with the audit that, when run, will promote it to PROVEN
or demote it to RULED_OUT.

### H1. The FX panel saturates the 0.30 edge gate — ⇒ `audits/topology_audit.md`

combo_v1 was engineered on a 3-node equity/gold graph
(`research/askar/intermarket_ricci_divergence.py`) where the |corr|
> 0.30 edge gate toggles meaningfully across regimes. On an 8-FX
panel dominated by the USD factor, the correlation structure may be
near-saturated — most edges active most of the time — which would
collapse the variability of `ricci_mean` and make `delta_Ricci`
dominated by degree noise instead of regime transitions.

Status: HYPOTHESIS. To be promoted only if Audit 1 labels the
saturation claim `SUPPORTED`.

### H2. The 40–45 % drawdown is structural to the portfolio mechanics, not a signal-specific tail event — ⇒ `audits/null_portfolio_audit.md`

Zero-mean log-returns with 2× gross exposure and autocorrelated
weights will generically compound into large drawdowns over 18 years.
The hypothesis is that combo_v1's 0.45 max DD sits inside the
**null-portfolio-mechanics** distribution (random-ranking and
sign-shuffled nulls with identical top-2 / bottom-2 / 1-bar-lag rules).
If so, the DD is not a signal failure — it is the mechanical cost of
running this position construction on zero-alpha inputs.

Status: HYPOTHESIS. Promoted only if Audit 2 labels the "DD structural"
claim `SUPPORTED`.

### H3. PnL losses are dispersed across bars, not concentrated in a few pathological assets/folds — ⇒ `audits/turnover_exposure_audit.md`

An alternative is that 1–2 assets (e.g. USDCHF with aggregate Sharpe
−0.64) or 2–3 specific folds carry the loss while the rest is
neutral-to-positive. If concentration is high, then the "no-edge"
framing is too coarse and the line could in principle be rescued by
some other universe — which would *still not* constitute a rescue of
combo_v1 × 8-FX under this preregistration, but it would change the
mechanistic story.

Status: HYPOTHESIS. Audit 3 returns a precise decomposition.

### H4. Combo's behaviour on 2022 reflects topology flip luck, not repeatable crisis-alpha

There is no 2022 replication (no second "2022") in the sample. The
claim is qualitative and cannot be elevated by any single-run audit.

Status: HYPOTHESIS — **unpromotable within this preregistration**.
The only path to proof or disproof is a preregistered out-of-sample
test on a separate crisis regime (e.g. 2020 Q1, 2015 CHF-float, 2008
Q4) with pre-committed thresholds. That is a new line, not a Wave 2.

---

## RULED_OUT

### R1. "Signal direction is inverted" (sign-flip bug)

Run A gross median Sharpe = −0.0046 is **within noise of zero**, not a
large negative. A sign-flip bug would produce roughly
−|true_positive_Sharpe|. With |median| ≈ 0.005, no such symmetric
structure exists. Ruled out.

### R2. "Fold subset bias drives the FAIL"

All 222 locked folds are `is_valid = True` in `run_b_net/folds.csv`
(column sum 222 / 222). No fold is excluded. §8 of `PREREG.md`
forbids subsetting. Ruled out.

### R3. "The spec was not actually run with cost_bps = 0 in Run A"

`run_a_gross/summary.json.costs_bps` shows 0.0 for every asset.
Confirmed. Ruled out.

### R4. "Wave 2 might salvage combo_v1 × 8-FX with tuning"

`PREREG.md §GATE`: *"Wave 2 starts only on PASS verdict."*
`CANONICAL_FAIL_NOTE.md §6`: parameter rescue explicitly prohibited.
`config/research_line_registry.yaml#combo_v1_fx_wave1`: machine-readable
`wave2_authorized: false`, `parameter_rescue_allowed: false`,
`same_family_same_substrate_retest_allowed: false`. Ruled out by
contract.

### R5. "2022 pass is sufficient because it is the gate that matters most"

§4 of the preregistration enumerates four gates with AND semantics.
No single gate is privileged. Ruled out by pre-reg.

---

## Audit results (appended after audits completed)

| hypothesis | audit | pre-committed label |
|---|---|---|
| H1: FX 0.30 edge gate saturates | `audits/topology_audit.md` | **WEAKLY_SUPPORTED** — P5(edge_density) = 0.50, median = 0.64 (below the pre-committed 0.75 / 0.85 thresholds for SUPPORTED; above the 0.50 ceiling for NOT_SUPPORTED). Graph is connected on 98 % of bars but not edge-saturated. |
| H2: DD is structural to portfolio mechanics, not signal-specific | `audits/null_portfolio_audit.md` | **NOT_SUPPORTED** — combo DD percentile in N1 (random-rank null) = 0.00; combo is *better* than every null, i.e. the signal reduces DD vs pure mechanics. The refined finding that is `SUPPORTED`: combo's DD and Sharpe are indistinguishable from combo's own block-shuffled self (N3, block = 60) at percentiles 0.50 / 0.56 — the signal has no time-aligned predictive content on FX forward returns. |
| H3: PnL losses are dispersed, not concentrated in a few assets | `audits/turnover_exposure_audit.md` | **HYBRID — partially supported** — top-2 assets = 53.7 % of |PnL| (moderate concentration); **USDCHF alone = 46.8 % of the max-DD window loss** with trough on 2015-01-16 (= SNB CHF-floor-break). DD is a hybrid of a 6-year slow grind and a single known tail event. |

### Promotions and demotions induced by audits

- **PROMOTED to PROVEN (P7, new):** combo_v1's one-bar-forward predictive
  content on the 8-FX panel is statistically indistinguishable from
  combo's own block-shuffled self at block = 60 bars (N3:
  Sharpe percentile 0.56, DD percentile 0.50). This is stronger than
  "combo has no edge" — it localises the missing edge to the
  time-alignment axis, not to the cross-sectional structure.
- **PROMOTED to PROVEN (P8, new):** combo_v1 *does* carry non-trivial
  contemporaneous cross-sectional structure on FX — it beats random
  ranking (N1) and sign-shuffled (N2) nulls on both Sharpe and DD at
  percentile ≥ 0.99. This rules out "combo is pure noise" as a
  diagnosis.
- **DEMOTED (H2):** "DD is structural to the mechanics" in its original
  form is RULED_OUT. The correct framing is "combo's DD is structural
  *within the family of signals with combo's own autocorrelation
  profile*", not "structural to any top-2 / bottom-2 mechanics".
- **PARTIALLY SUPPORTED (H1):** edge saturation is weakly present only.
  The stronger mechanism on FX is **graph connectedness** (one
  component 98 % of the time), not edge-count saturation.
- **PARTIALLY SUPPORTED (H3):** hybrid — 6-year grind + 2015-01-15
  USDCHF tail event (= 47 % of DD window loss).

### Meta-conclusion after audits

The verdict **does not change**. Every audit confirms combo_v1 × 8-FX
has no usable edge. What the audits add is **precision** about *why*:
the signal has cross-sectional structure but no forward-time edge, the
observed DD is a hybrid of a grind and a single known tail, and the
topology mechanism is graph-connectedness rather than edge-saturation.
None of these findings admits a parameter-rescue path on this
substrate.

---

## Forbidden next (enforced by registry + tests)

- Re-running combo_v1 on the 8-FX substrate with any different
  window, threshold, lag, top-k, or cost table.
- Subsetting the universe (e.g. "combo_v1 on USD-crosses only").
- Changing position construction while keeping `combo_v1` as the
  signal source on this substrate.

## Admissible next

- A **new** preregistration with a **new** FX-native signal family
  (carry, rate-differential, central-bank policy-path residual, USD-DXY
  residualised momentum, …), a **new** fold manifest, and a **new**
  line_id in `config/research_line_registry.yaml`.
- Applying combo_v1 on a **non-FX** substrate is a separate line;
  it is not blocked by this closure but must carry its own
  preregistration and fail-closed contract.

## Artefacts

```
results/wave1_fx/
├── CANONICAL_FAIL_NOTE.md    (canonical closure, cite in downstream)
├── ROOT_CAUSE.md             (this file — evidence-tiered)
├── POSTMORTEM_SUMMARY.md     (≤500-word decision grade)
├── VERDICT.md                (machine-generated from Run B)
├── PREREG.md                 (locked preregistration v2)
├── universe.json             (locked)
├── fold_manifest.csv         (locked; 222 folds)
├── panel_audit.json          (locked; panel build stats)
├── run_a_gross/              (diagnostic)
├── run_b_net/                (verdict)
└── audits/
    ├── topology_audit.md
    ├── null_portfolio_audit.md
    └── turnover_exposure_audit.md
```
