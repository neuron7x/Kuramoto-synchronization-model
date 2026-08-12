# DRO-ARA v7 · Walk-Forward Calibration Report

## Header

- data_source: `data/askar/SPDR_S_P_500_ETF_GMT_0_NO-DST.parquet`
- date_range: 2017-02-16 → 2026-02-20
- n_daily_bars: 2263
- n_folds: 69
- grid_size: 7 × 11 = 77
- train_window=252, test_window=63, step=21, min_history=504

## Current vs Optimal

| param | current | optimal | delta |
|-------|---------|---------|-------|
| H_threshold (H_CRITICAL) | 0.45 | 0.40 | +0.05 |
| rs_threshold (RS_LONG_THRESH) | 0.33 | 0.10 | +0.23 |

## Top-5 Pairs (by mean OOS Sharpe)

| rank | H | rs | mean_sharpe | std_sharpe | worst_fold_sharpe | worst_dd | mean_trades | passes_filters |
|------|----|----|-------------|------------|--------------------|----------|-------------|----------------|
| 1 | 0.40 | 0.10 | -0.011 | 0.191 | -1.479 | 0.128 | 0.7 | False |
| 2 | 0.40 | 0.15 | -0.011 | 0.191 | -1.479 | 0.128 | 0.7 | False |
| 3 | 0.40 | 0.20 | -0.011 | 0.191 | -1.479 | 0.128 | 0.7 | False |
| 4 | 0.45 | 0.20 | -0.011 | 0.191 | -1.479 | 0.128 | 0.7 | False |
| 5 | 0.50 | 0.20 | -0.011 | 0.191 | -1.479 | 0.128 | 0.7 | False |

## Robustness

- Top pair (H=0.40, rs=0.10): mean_sharpe=-0.011, std_sharpe=0.191, worst_fold_sharpe=-1.479, worst_dd=0.128, mean_trades=0.7, gate_on_folds=3

## Crisis Window (2022)

| H | rs | crisis_mean_sharpe | crisis_worst_dd | crisis_folds |
|----|----|--------------------|-----------------|--------------|
| 0.30 | 0.10 | 0.000 | -0.000 | 12 |
| 0.30 | 0.15 | 0.000 | -0.000 | 12 |
| 0.30 | 0.20 | 0.000 | -0.000 | 12 |
| 0.30 | 0.25 | 0.000 | -0.000 | 12 |
| 0.30 | 0.30 | 0.000 | -0.000 | 12 |

## Recommendation

**STRATEGY_UNPROFITABLE / REJECT** — 20 (H, rs) pairs activated the gate, but the best mean OOS Sharpe across all active cells is -0.011 (≤ 0). The combo_v1 × DRO-ARA pipeline does not produce a profitable edge on this asset at this bar granularity. Threshold tuning cannot fix a non-existent signal. Operator action: DO NOT modify engine constants. Consider: (a) higher-frequency data, (b) richer R/κ feature proxies than constants, or (c) a different asset class for combo_v1 deployment.

Notes: Hurst computed exclusively on train windows (no leakage). Signal = combo_v1 (AMMComboStrategy) position × DRO-ARA gate. Gate logic = INV-DRO4 under grid-swept thresholds. Backtest = vectorized_backtest(fee=0.0005, signal shift=1 anti-lookahead).
