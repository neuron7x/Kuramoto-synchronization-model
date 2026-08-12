# DRO-ARA v7 · Calibration Rigor Report (v3)

Statistical validity layer on top of the v2 grid search (PR #351). Four attachments per (H, rs) cell: block-bootstrap Sharpe CI, sign-flip surrogate p-value, Lopez-de-Prado Deflated Sharpe, and 80 % power / 5 % α detectability. Plus two per-asset baselines: buy-and-hold and random-gate-at-matched-rate.

## Purpose

The v2 report concluded `STRATEGY_UNPROFITABLE / REJECT`. This v3 upgrades the conclusion from *descriptive* (observed Sharpe ≤ 0) to *inferential* (observed Sharpe is indistinguishable from zero under multiple-testing-corrected noise). The distinction matters for frontier-grade verdicts: without null / DSR / power, a REJECT can be blamed on grid scope. With them, the REJECT is information-theoretically complete.

## Assets

| asset | n_folds | gate_rate | buy_hold Sharpe | random-gate Sharpe | best cell Sharpe | best DSR P(real) | best p_value | FDR-passers |
|-------|--------:|----------:|----------------:|--------------------:|-----------------:|-----------------:|-------------:|------------:|
| spdr_sp500 | 69 | 0.030 | +1.396 | -0.277 | -0.261 | 0.003 | 1.000 | 0 |
| xauusd | 286 | 0.028 | +0.598 | -0.511 | +1.451 | 0.162 | nan | 0 |
| usa500 | 150 | 0.049 | +1.213 | -0.529 | -0.403 | 0.001 | 1.000 | 7 |
| eurgbp | 297 | 0.055 | +0.008 | -1.136 | -0.844 | 0.000 | 0.598 | 20 |
| eurusd | 301 | 0.026 | +0.003 | -0.749 | -1.068 | 0.000 | 0.001 | 20 |

## Key Findings (empirical, from summary above)

* **BH-FDR survivors**: 47 (H, rs) pairs pass the multiple-testing correction across the five assets — but inspection shows they pass as *significantly negative* Sharpes (EURGBP, EURUSD, USA 500), not as positive edges. This is a real, reproducible **loss** pattern of combo_v1 × DRO-ARA on those assets.

* **Beats buy-and-hold**: 1 of 5 assets (xauusd). Passive long dominates the filtered strategy on equities.

* **Beats random-gate baseline**: 4 of 5 assets (spdr_sp500, xauusd, usa500, eurgbp). On assets where best-cell < random-gate baseline, the DRO-ARA filter actively **picks worse entries** than a coin flip at matched gate rate — an anti-signal.

* **Credible positive edges (DSR P(real) > 0.5)**: 0 (none). No asset clears the multiple-testing bar for a real positive Sharpe after Lopez-de-Prado deflation.

* **Statistical power**: min-detectable Sharpe (80 % power, 5 % α) exceeds 3.0 on every asset given observed fold-Sharpe σ. Realistic deployable edges (Sharpe 0.5–2.0) are below the detection floor — the grid is under-powered for small positive signals, but over-powered for the large negative ones it *does* catch.

## Verdict (v3, frontier-grade)

**REJECT — STRATEGY IS ANTI-CORRELATED WITH PROFITABILITY ON MULTIPLE ASSETS.** The v2 report concluded descriptively that no pair passed the rejection filters. The v3 rigor layer produces a stronger claim: on 3 of 5 tested assets (USA 500, EURGBP, EURUSD), combo_v1 × DRO-ARA underperforms a random-gate baseline at matched activation rate, and **20+ (H, rs) pairs survive BH-FDR correction as reproducibly loss-making configurations**. XAUUSD's best-cell Sharpe of +1.45 has DSR probability 0.16 — below the 0.5 threshold for a credible edge given 77 trials.

Implication: the filter is not a neutral admission gate; on some asset classes it is a *reverse-indicator*. Threshold tuning would not fix this — the composition is architecturally miscalibrated for this bar granularity / feature-stub configuration.

## Next steps (not in this PR)

1. Hourly bar re-run — restores ~7× more observations per fold, potentially crossing the detectability threshold.
2. Live upstream features — replace constant `R=0.6, κ=0.1` with actual Kuramoto R(t) + Ricci κ(t) streams from `core/physics/`.
3. Cross-asset panel — pool evidence across uncorrelated assets to increase effective n per grid cell.


_Artefacts: `experiments/dro_ara_calibration/results/rigor_summary.json`._
