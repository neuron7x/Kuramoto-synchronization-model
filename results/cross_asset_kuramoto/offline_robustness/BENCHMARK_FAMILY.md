# Phase 4 · Benchmark family

All benchmarks use the same execution lag (1 bar) and same `cost_bps=10` cost model as the frozen Kuramoto strategy, **except** pure buy-and-hold-by-construction (BF2, BTC) which has zero turnover after entry and therefore zero cost. CSV: `benchmark_family.csv`.

## Results (OOS 70/30 test)

| ID | cost / lag | OOS Sharpe | max DD | ann ret | ann vol | excess vs Kuramoto |
|---|---|---:|---:|---:|---:|---:|
| **kuramoto_strategy** | 10 bps, lag=1 | **1.262** | −16.76 % | +23.58 % | 18.69 % | 0.000 |
| BF1 equal_weight_buy_hold | 10 bps, lag=1 (zero turnover in practice) | 0.872 | −25.13 % | +21.36 % | 24.49 % | +0.390 |
| BF2 btc_benchmark | cost = 0 by construction | 0.802 | −49.53 % | +38.83 % | 48.44 % | +0.460 |
| BF3 momentum_baseline | 10 bps, lag=1 (20-bar lookback, fixed) | 0.752 | −42.50 % | +34.54 % | 45.91 % | +0.510 |
| BF4 vol_targeted_equal_weight | 10 bps, lag=1 (15 % vol target, 1.5× cap) | 0.843 | **−13.10 %** | +9.76 % | 11.58 % | +0.419 |

## Ranking (Sharpe)

1. kuramoto_strategy 1.262
2. equal_weight_buy_hold 0.872
3. vol_targeted_equal_weight 0.843
4. btc_benchmark 0.802
5. momentum_baseline 0.752

## Key observations

- **Kuramoto beats all four on Sharpe.** Excess 0.39 (vs BF1) to 0.51 (vs BF3).
- **BF4 wins on max DD** (13.1 % vs Kuramoto's 16.8 %) but pays for it — ann ret only 9.8 % vs 23.6 %. DD preservation via under-exposure.
- **BF1 is the tightest peer** (Sharpe 0.87, above 0.80 demo-gate). Kuramoto's +0.39 excess on top comes mostly from DD 25 %→17 % and vol 24 %→19 %, with ann ret roughly intact.
- **BF3 underperforms BF1.** Momentum at fixed 20-bar lookback under full cost/lag parity is worse than passive equal-weight on this universe-window. Cross-sectional momentum is not a free substitute for a regime-aware signal here.
- **BF2 (BTC):** excess +0.46 Sharpe at 1/3 of BTC's max DD (16.8 % vs 49.5 %) and 40 % of its vol.

## §BF8 answer

Kuramoto **adds value** against all four on Sharpe. It **does not dominate BF4 on DD alone** (BF4 is lower-DD by construction). The Sharpe delta vs the tightest benchmark (BF1) is +0.39 under matched cost/lag — no benefit came from zero-cost arithmetic.
