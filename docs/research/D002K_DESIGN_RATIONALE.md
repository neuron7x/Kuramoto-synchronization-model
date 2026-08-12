# D-002K Design Rationale — High-SNR Event-Conditioned Funding-Liquidity Stress Benchmark

> **Status:** fresh pre-registration ONLY. Zero data. Zero scoring. Zero
> model run. This document explains *why* D-002K is shaped the way it is
> and *why it is not* a D-002J rescue.
>
> **No-rescue boundary (binding):** D-002K does **not** reopen, mutate,
> amend, or rescue D-002J. D-002J remains terminally **REFUSED** at P7
> (`POWER_GATE_REFUSED_UNDERPOWERED`, refused axis `effect_too_small`,
> PR #705, merge sha `c5c4158bed639014ec35ab8f53ec70d98be660a2`). That
> REFUSED verdict is the truthful terminal outcome and the honest
> foundation D-002K is built on.

## §0 — Why D-002K, not a D-002J resurrection

D-002J-P7 ran an honest power-first gate over the full canonical grid
(102 cells = Bonferroni denominator) and **REFUSED** on the axis
`effect_too_small`. The binding diagnosis is explicit in the retained
P7 power summary:

- `refused_axis = effect_too_small`
- per-cell `n_min` distribution `{min: 150, median: 235, max: 417}`,
  every cell above the most-generous feasible cap of 100 seeds
- **runtime was NOT the binding constraint** (measured per-sim ≈ 4e-5 s;
  projected sweep < 0.1 h). The binding constraint was purely that the
  honest P4-sourced substrate-vs-null separation, spread across 102
  cells under a Bonferroni α = 0.05/102, was too small to reach
  power ≥ 0.8 within a feasible per-cell seed budget.

The P7 failure_retention states forward motion is **not** P8: it
requires a *fresh* D-002K pre-registration designed against the
effect-too-small axis — a higher-SNR observable, a window-conditioned
statistic, or substantively re-derived ground truth — **NOT** a relaxed
alpha or an inflated prior. D-002K is that fresh pre-registration.

D-002J stays REFUSED. D-002K does not touch it.

## §1 — The narrowing strategy

The effect_too_small refusal was a *design-spread* failure: a real but
modest per-cell signal was diluted across a 102-cell grid under a heavy
Bonferroni correction. D-002K's response is to **increase per-hypothesis
signal-to-noise by narrowing the design**, not by loosening the
statistics:

| Lever | D-002J (refused) | D-002K (this prereg) |
|-------|------------------|----------------------|
| Mechanisms | 3 P5 substrates | **1** (`funding_liquidity_rollover`) |
| Crisis windows | 6 (CW1..CW6) | **3** (CW3, CW4, CW5) |
| Primary metric | per-cell metric x2 | **1** locked endpoint |
| Cells / hypotheses | 102 | **3** (3 windows x 1 metric) |
| Bonferroni denominator | 102 | **3** |
| Comparison structure | substrate-vs-null | crisis-vs-matched-placebo |

The Bonferroni denominator shrinks from 102 to 3 **because there are
honestly fewer pre-registered hypotheses**, not because α was loosened
at a fixed hypothesis count. This distinction is the entire legitimacy
of D-002K and is made testable in §6 and in the prereg `alpha_policy`.

Additional narrowing:

- **Observable proximity:** the locked observables (SOFR, OFR
  tri-party repo volumes, FRED H.15) sit directly on the mechanism,
  not on a contagion proxy.
- **Matched placebo:** crisis windows are scored against pre-registered
  matched placebo windows, sharpening the contrast and removing the
  cherry-picking degree of freedom.

## §2 — Why `funding_liquidity_rollover`

Of the three P5 substrates, `funding_liquidity_rollover` is the highest
point-in-time SNR and lowest fake-network risk:

- **Direct public observables:** SOFR, OFR tri-party repo volumes by
  collateral class, FRED H.15 reference rates — all point-in-time,
  public, and on the mechanism itself.
- **No unobservable network:** unlike `cross_exposure_contagion_proxy`
  (which needs an interbank network that is not publicly observable
  and risks contagion-proxy theater), the rollover mechanism is fully
  expressible from public funding-rate aggregates.
- **Clean signature:** a step in `funding_stress_index` at onset plus
  accelerating `rollover_failure_count`, with broader equity/credit
  panic muted (the CW3 "narrow funding signature without market panic"
  constraint) — a high-contrast event-conditioned signature.

It is the single locked mechanism. No other P5 substrate is in scope.

## §3 — Why CW3 / CW4 / CW5

Each is a funding-liquidity stress event with strong public
point-in-time data and a direct observable path to the rollover
mechanism:

- **CW3 — 2019 US repo spike:** a near-pure funding-liquidity event
  (SOFR spike, repo dislocation) with muted broader market panic.
- **CW4 — 2020 COVID dash-for-cash:** an acute funding-liquidity
  scramble with rich public SOFR / repo / H.15 coverage.
- **CW5 — 2022 UK gilt/LDI crisis:** a funding-liquidity / forced-
  deleveraging event with public gilt-yield and funding observables.

These are exactly the three crisis windows the P5
`funding_liquidity_rollover` substrate already declares. No broader
window set is in scope.

## §4 — Matched-placebo discipline

Hand-picked control windows are a cherry-picking degree of freedom. The
matched-placebo policy removes it:

- **Deterministic pre-registered algorithm**, seeded only by the locked
  crisis-window calendar and the `match_on` covariates
  (`macro_period`, `volatility_regime`, `calendar_length`,
  `data_availability`, `pre_window_baseline_variance`).
- **5 placebo windows per crisis**, locked at this pre-registration.
- **Locked before scoring:** if the matched placebo contrast is
  undefined before scoring opens, the run is `INVALID` (a stop
  condition).

## §5 — Power-first BEFORE scoring (the D-002J lesson, applied earlier)

D-002J only discovered it was underpowered at P7, after building the
whole grid. D-002K makes power-first a **pre-registration law** at the
P-power phase: the power gate **must run and PASS before any scoring**.
If it REFUSES, D-002K halts; no scoring is performed; forward motion
requires a fresh D-002L pre-registration. The effect prior must be
honestly derived with documented provenance and may not be inflated —
inflating it is the exact failure axis being designed against.

## §6 — Forbidden interpretations + no-rescue boundary

D-002K may **never** state, imply, or rely on:

- "D-002K rescues D-002J" / "D-002K reverses D-002J-P7 REFUSED"
- "GeoSync predicts systemic crises" / "bank-level validated"
- "cross-asset coherence proves interbank contagion"
- "universal systemic-risk prediction" / "cross-substrate generalization"
- "relaxed alpha is justified by D-002J refusal"

**The narrowing/laundering distinction (testable):** narrowing the
*scope* (3 windows, 1 mechanism, 1 metric) is legitimate experimental
design — it produces a legitimately smaller Bonferroni denominator
because there are honestly fewer hypotheses. Loosening the *statistics*
at a fixed hypothesis count (relaxing α, inflating the effect prior,
shrinking a grid post-hoc) is laundering and is forbidden. The prereg
`alpha_policy.denominator_rule = "n_windows * n_primary_metrics"` encodes
this: the denominator is derived from the honest hypothesis count, never
hand-set lower.

## §7 — D-002J → D-002K lineage relationship

D-002K continues the closure-before-restart discipline already used in
this programme:

```
D-002G -> D-002H REFUSED -> D-002I -> D-002J prereg ... -> D-002J-P7 REFUSED -> D-002K-P0 (fresh)
```

The D-002J-P7 REFUSED capsule is retained verbatim as a sha-pinned
terminal negative artifact. D-002K-P0's verdict capsule descends from
`D002J-P7` in the DAG because the honest lineage statement is: **D-002K
exists *because* D-002J-P7 refused**, not because D-002J-P7 was wrong.
The DAG records this with a `lineage_transitions` entry marking
`D002J-P7` as `TERMINAL_REFUSED`, successor lineage `D-002K`, successor
root `D002K-P0`, and `is_rescue: false`. D-002J-P1A and D-002J-P7 remain
in `rejected_nodes_retained`; D-002K does not clear them.
`canonical_run_authorized_anywhere` stays `false`.

## Judgment call — lineage map renderer

`tools.governance.render_lineage` loaded only `d002j_p*_verdict_v1.json`
capsules. Because D-002K-P0's parent is `D002J-P7` and the two lineages
now form a single connected DAG (D-002K exists because D-002J refused),
the renderer glob and `tools.governance.verdict_dag.load_dag` glob were
minimally widened to `d002[jk]_p*_verdict_v1.json` so the **single
combined** lineage map renders both lineages in one honest graph rather
than splitting them. The map title was generalised to "D-002J / D-002K
Verdict DAG — Lineage Map". This is preferred over a separate
`D002K_LINEAGE_MAP.md` precisely because the lineage is connected: a
split map would visually hide the `D002J-P7 -> D002K-P0` honest
descent. The DAG-about-the-DAG artifact name is retained for backward
compatibility.
