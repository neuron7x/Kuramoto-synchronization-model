# Wave 1 · combo_v1 × 8 FX · POSTMORTEM SUMMARY

Decision grade. SHAs: lock `ef0b774`, complete `3214612`, GeoSync `8b68156`.

## Hypothesis tested

combo_v1 (= `research.askar.full_validation.build_signal`, window 120,
threshold 0.30) — a Forman-Ricci graph-topology signal engineered on a
3-node equity/gold panel — produces OOS edge on 8-FX daily
cross-sectional L/S (top-2 / bottom-2, 1-bar lag, dollar-neutral,
equal-weight).

## What was locked

8 FX majors; 2003–2026 daily close at 21:00 UTC; inner-joined
(5863 bars, 2 corrupt_ts rows dropped); 222 walk-forward folds
(252 / 63 / 21 days, min-history 504, 2008-01-01 → 2026-02-20);
cross-sectional L/S; Run B costs 1.0 bps EUR/GBP/AUD-USD, 1.5 bps
other pairs; PASS iff (median-of-fold-medians Sharpe ≥ 0.80) AND
(positive-fold fraction ≥ 60 %) AND (2022-touching fold median ≥ 0)
AND (OOS max DD ≤ 0.20).

## What failed

Three of four gates fail decisively in the verdict run (Run B, net):

| gate | value | threshold |
|---|---:|---:|
| median fold-median Sharpe | −0.0457 | ≥ 0.80 |
| positive-fold fraction | 43.2 % | ≥ 60 % |
| 2022-touching folds median Sharpe | +0.1964 | ≥ 0 (pass) |
| max drawdown (OOS portfolio) | 0.4488 | ≤ 0.20 |

Only the 2022 gate passes. Gross Sharpe (cost-free diagnostic) is
−0.0046 — cost drag is 0.04 Sharpe, not the root cause.

## What is proven

1. No PASS gate is achievable by removing costs: Run A also fails.
2. Per-asset mean Sharpe spread −0.636 (USDCHF) to +0.251 (USDJPY);
   the cross-asset structure does not monetise uniformly.
3. combo_v1 beats random-rank and sign-shuffled nulls at Sharpe
   percentile 1.00 and DD percentile 0.00 (n = 300 each) — real
   cross-sectional structure.
4. combo_v1 is statistically indistinguishable from its own
   block-shuffled self (block = 60, percentiles 0.56 / 0.50) — no
   time-aligned edge on one-bar-forward FX returns.
5. Max DD is hybrid: 2008-12-11 → 2015-01-16 (~6-year grind) with
   USDCHF alone contributing 46.8 % of window loss (trough =
   2015-01-15 SNB CHF-floor break).
6. Exposure invariants hold: gross = 2.0, net = 0.0 on 100 % of OOS
   bars.

## What is only hypothesized

- 0.30 edge-threshold saturation on the FX graph — audit label
  **WEAKLY_SUPPORTED** (median edge density 0.64, not saturated; but
  graph connected on 98 % of bars).
- 2022 = regime-flip luck rather than repeatable crisis-alpha —
  unpromotable within this single preregistration. Needs a new,
  preregistered crisis-regime test.

## What is forbidden next

- Any combo_v1 re-run on the 8-FX substrate with altered window,
  threshold, lag, top-k, or cost table.
- Universe subsetting, fold exclusion, verdict-run switching.
- "Promising / almost works / needs tuning" framings.
- Wave 2. Blocked by preregistration §GATE and by registry test.

## What is admissible next

- A fresh preregistration with a new FX-native signal family (carry,
  rate-differential, policy-path residual, DXY-residualised momentum),
  new `line_id` in `config/research_line_registry.yaml`, new fold
  manifest, new lock commit.
- combo_v1 on a non-FX substrate — separate line, not blocked by this
  closure.
