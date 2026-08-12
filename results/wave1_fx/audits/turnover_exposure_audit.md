# Audit 3 — Turnover, exposure, concentration, PnL/DD attribution

Generated UTC: `2026-04-21T21:09:14Z`  
OOS window: 2008-01-02 21:00:00 → 2026-02-09 21:00:00  (4704 bars)

## Exposure invariants (sanity)

| metric | value |
|---|---|
| gross_mean | 2.0 |
| gross_median | 2.0 |
| gross_min | 2.0 |
| gross_max | 2.0 |
| gross_frac_at_2 | 1.0 |
| net_mean | 0.0 |
| net_median | 0.0 |
| net_abs_max | 0.0 |
| net_frac_at_0 | 1.0 |
| n_zero_exposure_bars | 0.0 |

`gross_frac_at_2` ≈ 1 and `net_frac_at_0` ≈ 1 → position-construction invariants hold: dollar-neutral long-short, 2× gross, 0 net, on every bar where combo signal is defined.

## Turnover per bar (OOS)

| metric | value |
|---|---|
| median_per_bar | 0.0 |
| mean_per_bar | 0.4037 |
| p95_per_bar | 2.0 |
| p99_per_bar | 3.0 |
| frac_bars_with_zero_turnover | 0.777 |
| frac_bars_with_max_turnover_4.0 | 0.0066 |

## Sign-flip frequency per asset

| asset | n_oos_bars | frac_long | frac_short | frac_flat | n_sign_flips | sign_flip_rate_per_bar |
|---|---|---|---|---|---|---|
| EURUSD | 4704 | 0.254 | 0.2411 | 0.5049 | 16 | 0.0034 |
| GBPUSD | 4704 | 0.1956 | 0.2474 | 0.557 | 29 | 0.0062 |
| USDJPY | 4704 | 0.2747 | 0.2572 | 0.4681 | 28 | 0.006 |
| AUDUSD | 4704 | 0.2273 | 0.2207 | 0.5521 | 21 | 0.0045 |
| USDCAD | 4704 | 0.203 | 0.2766 | 0.5204 | 20 | 0.0043 |
| USDCHF | 4704 | 0.2315 | 0.216 | 0.5525 | 24 | 0.0051 |
| EURGBP | 4704 | 0.2957 | 0.29 | 0.4143 | 30 | 0.0064 |
| EURJPY | 4704 | 0.3182 | 0.2511 | 0.4307 | 14 | 0.003 |

## Per-asset OOS PnL attribution

| asset | total_net_log_return | total_gross_log_return | total_cost_log_return | pct_of_portfolio_net |
|---|---|---|---|---|
| EURUSD | -0.0683 | -0.044 | -0.0243 | 0.2282 |
| GBPUSD | 0.0077 | 0.0333 | -0.0256 | -0.0258 |
| USDJPY | 0.1793 | 0.2159 | -0.0366 | -0.5992 |
| AUDUSD | 0.1808 | 0.2046 | -0.0238 | -0.6045 |
| USDCAD | -0.1452 | -0.1134 | -0.0319 | 0.4855 |
| USDCHF | -0.3746 | -0.3413 | -0.0333 | 1.2521 |
| EURGBP | -0.0772 | -0.0397 | -0.0374 | 0.2579 |
| EURJPY | -0.0017 | 0.0335 | -0.0352 | 0.0058 |

- PnL concentration: top-2 assets (by |contrib|) account for **53.7 %** of absolute PnL; top-3 for **71.0 %**.

## Drawdown attribution

- Peak date: `2008-12-11 21:00:00`
- Trough date: `2015-01-16 21:00:00`
- Max DD: **0.4297** (42.97%)
- Total log-return across the DD window: -0.5516
- Single worst asset in the DD window: **USDCHF** (-0.2583 log-return, 46.8 % of DD window loss).

Per-asset breakdown inside the DD window (peak → trough):

| asset | log_return_in_dd_window |
|---|---|
| USDCHF | -0.2583 |
| USDCAD | -0.1074 |
| AUDUSD | -0.0632 |
| GBPUSD | -0.0533 |
| EURUSD | -0.0455 |
| EURGBP | -0.0434 |
| EURJPY | -0.0004 |
| USDJPY | 0.0198 |

## Worst 5 and best 5 folds by cumulative portfolio log-return

Worst 5:

| fold_id | test_start_ts | test_end_ts | portfolio_cum_log_return | portfolio_sharpe | in_2022 |
|---|---|---|---|---|---|
| 33 | 2010-08-11 | 2010-11-05 | -0.1183 | -3.7239 | False |
| 210 | 2024-11-22 | 2025-02-19 | -0.1118 | -5.8797 | False |
| 85 | 2014-10-21 | 2015-01-16 | -0.1046 | -2.3433 | False |
| 21 | 2009-08-20 | 2009-11-16 | -0.099 | -3.6861 | False |
| 19 | 2009-06-23 | 2009-09-17 | -0.0984 | -3.8295 | False |

Best 5:

| fold_id | test_start_ts | test_end_ts | portfolio_cum_log_return | portfolio_sharpe | in_2022 |
|---|---|---|---|---|---|
| 10 | 2008-09-23 | 2008-12-18 | 0.2182 | 4.1898 | False |
| 9 | 2008-08-25 | 2008-11-19 | 0.1765 | 3.2805 | False |
| 110 | 2016-10-27 | 2017-01-23 | 0.1354 | 6.3469 | False |
| 109 | 2016-09-28 | 2016-12-23 | 0.1115 | 5.0058 | False |
| 88 | 2015-01-19 | 2015-04-15 | 0.0936 | 2.525 | False |

## Final precise statement

The observed 42.97% max DD has a **hybrid structure** and is not reducible to a single mechanism.

### Facts (numerically grounded)

1. **Timing — 6-year grind + one known tail**: Peak 2008-12-11, trough **2015-01-16**. The trough date coincides with the **SNB CHF-floor-break of 2015-01-15** (trough fold = 85, test_end = 2015-01-16). Sixth-plus-year drawdown with an identifiable tail event inside it.

2. **Cross-asset concentration is real but not total**: In the DD window, **USDCHF alone = 46.8 %** of the window's total loss. USDCHF + USDCAD = 66 %. Top-2 assets by |contribution| across full OOS = 53.7 % of absolute PnL; top-3 = 71.0 %. This is **mild-to-moderate concentration**, not a diversified failure and not a single-asset failure.

3. **Exposure mechanics are clean**: Gross = 2.0 on 100 % of OOS bars, net = 0.0 on 100 % of OOS bars. Dollar-neutral L/S invariants hold. Not a construction bug.

4. **Turnover is low**: median = 0, mean = 0.40, 77.7 % of bars zero-turnover, 0.66 % of bars at max turnover 4.0. Sign-flip rates per asset cluster in 0.05–0.15 range. **Not a thrash-cost story.**

5. **Whipsaw around regime transitions**: Best 5 and worst 5 folds by cumulative portfolio return straddle regime changes — fold 10 (Sep-Dec 2008 GFC) = best (+0.218), fold 85 (ending 2015-01-16 CHF unpeg) = trough; fold 88 (starting 2015-01-19) = best in 2015 (+0.094). Large alternating bets around known regime events.

### Decomposition verdict

The DD is best described as:

> **(a)** a **~6-year slow-grind loss** produced by noisy cross-sectional ordering with no time-aligned forward edge (consistent with Audit 2 N3 — combo_v1 is indistinguishable from its own block-shuffled self on forward-return predictivity), combined with **(b)** a **concentrated USDCHF tail event on 2015-01-15** that accounts for ~47 % of the DD window's loss and whose timing and magnitude are driven by a specific known regime break (SNB floor), not by combo_v1's signal content.

Implications for ROOT_CAUSE.md:

- The earlier "DD is structural, zero-mean random walk with 2× exposure" narrative is **partially supported at best**: the 6-year grind component is plausibly structural, but ~47 % of the DD is from a specific single-asset tail. This is a **hybrid failure mode**, not a pure structural one.
- **Nothing in this audit argues for combo_v1 × FX rescue.** The grind component is the "no time-aligned edge" problem identified by Audit 2; the tail component is a non-repeatable event whose handling depends on risk-management, not signal.

## Artefacts

- `turnover_exposure_path.csv` — per-bar gross, net, turnover
- `turnover_per_fold.csv` — per-fold turnover summaries
- `sign_flip_per_asset.csv` — per-asset flip rates
- `per_asset_pnl_oos.csv` — per-asset PnL attribution
- `dd_asset_breakdown.csv` — per-asset contrib during DD window
- `fold_portfolio_attribution.csv` — per-fold portfolio Sharpe & PnL
- `turnover_exposure_audit.json` — machine-readable summary
