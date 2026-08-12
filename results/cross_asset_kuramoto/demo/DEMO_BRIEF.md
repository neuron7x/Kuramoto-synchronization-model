# Cross-Asset Kuramoto Regime Strategy — Demo Brief

Integrated module at commit-to-be. Spike composite SHA-256: `9e76e3b511d31245239961e386901214ea3a4ccc549c87009e29b814f6576fe3`.
Data snapshot: /home/neuro7/spikes/cross_asset_sync_regime/data.

## 1. What the signal does

A rolling Kuramoto order parameter R(t) is computed from the instantaneous phases of detrended log returns across 8 cross-asset price series (BTC, ETH, SPY, QQQ, GLD, TLT, DXY, VIX). R(t) is classified into three regimes by fixed quantile thresholds fit on the first 70 % of the series; the trading strategy assigns a vol-targeted inverse-volatility risk-parity weighting inside a regime-specific bucket of the 5-asset strategy universe (BTC, ETH, SPY, TLT, GLD).

## 2. Key results (70/30 OOS single-split)

- OOS Sharpe: **1.262**  (spike on-disk: 1.262)
- OOS max drawdown: **-0.168**  (spike on-disk: −16.76 %)
- OOS ann return: **0.236**, vol: 0.187
- Calmar: 1.407, win rate: 0.538
- Annualised turnover: 23.127, cost drag: 231.3 bps / year (8.3 % of gross)

Walk-forward validation (5 disjoint OOS windows): median Sharpe 0.942, 4/5 folds beat BTC Sharpe, 4/5 folds reduce max DD vs BTC; one fold (2022) posted negative Sharpe (spike-known limitation, preserved).

## 3. Cost resilience

| cost multiplier | cost_bps | Sharpe |
|---:|---:|---:|
| 1.0× | 10.0 | 1.2619 |
| 2.0× | 20.0 | 1.1469 |
| 3.0× | 30.0 | 1.0318 |

The strategy remains Sharpe > 1.0 at 3× the baseline execution cost.

## 4. What it does NOT claim

- No statistical significance vs BTC under a frequentist test (paired-bootstrap p-value ≈ 0.428 in the spike on-disk report).
- No live slippage / depth-aware execution cost model.
- No adaptive / online parameter adjustment.
- No outperformance of the equities-only basket when run on SPY/QQQ/DIA/IWM only (Track-A equities-only was MARGINAL in the spike).

## 5. Known limitations

- Hilbert phase extraction is FFT-based and therefore non-causal (`INTEGRATION_NOTES.md#OBS-1`). Practical impact is boundary-localised; strictly-causal variants would require a separate PR.
- Fold 3 (2022) posted −1.15 Sharpe; the strategy underperformed BTC during the 2022 bear market's fast-move leg.
- Forward-fill policy (`ffill(limit=3)`) is material: ΔSharpe between ffill and no-ffill is 0.22 (`PIPELINE_AUDIT.md#DP5`).
- Data snapshot is 10–12 days old vs the current clock (`PIPELINE_AUDIT.md#DP3`); a live deploy would refresh the feed.

## 6. Next steps for production decision

- Replace the Hilbert step with a strictly-causal analytic-signal extractor; re-verify reproduction.
- Add a depth-aware execution cost model; redo cost sensitivity.
- Promote the module from the workspace layout into the GeoSync tree under `core/strategies/` with the full GeoSync CI pipeline.
- Continue live paper-trading from the existing spike feed to day-90 (~2026-07-10) before any capital deployment decision.
