# Intermarket Ricci Divergence — Diagnostics Report
**Verdict:** `MARGINAL`  
**Reason:** 5/5 positive folds but mean Sharpe 0.672 in [0.5, 1.0)
## Data audit
- aligned panel: **15849** bars (2017-02-16 16:00:00 → 2026-02-20 21:00:00), anchor = `SPY`, ffill limit = 24 h
- per-asset:
  - `XAUUSD` (XAUUSD_GMT_0_NO-DST.parquet): n_bars=54009, nan=0, 2017-01-03 00:00:00 → 2026-02-23 00:00:00
  - `USA500` (USA_500_Index_GMT_0_NO-DST.parquet): n_bars=51105, nan=0, 2017-01-03 08:00:00 → 2026-02-23 00:00:00
  - `SPY` (SPDR_S_P_500_ETF_GMT_0_NO-DST.parquet): n_bars=15849, nan=0, 2017-02-16 16:00:00 → 2026-02-20 21:00:00

## Orthogonality gate
- `corr(ricci_div_z, spy_momentum_20)` = **+0.0093**  (threshold ±0.3)
- gate_passed = **True**

## Walk-forward 5-fold
| fold | train_start | split_ts | IC_train | IC_test | Sharpe_test | MaxDD_test |
|---|---|---|---|---|---|---|
| 1 | 2017-02-28 | 2018-05-16 | -0.0471 | +0.0332 | +1.277 | -0.0616 |
| 2 | 2018-11-29 | 2020-03-06 | +0.0067 | +0.0201 | -0.698 | -0.3524 |
| 3 | 2020-09-17 | 2021-12-20 | +0.0102 | +0.0206 | +1.591 | -0.1465 |
| 4 | 2022-07-07 | 2023-10-10 | -0.0376 | +0.0165 | +1.113 | -0.0860 |
| 5 | 2024-04-25 | 2025-08-06 | +0.0293 | +0.0083 | +0.077 | -0.1306 |

- positive_count = **5 / 5**
- mean IC_train = -0.0077
- mean IC_test  = +0.0197
- mean Sharpe_test = +0.672
- overfit_ratio = -0.39

### Caveats
- **Train / test sign inversion.** mean IC_train = -0.0077 has the opposite sign of mean IC_test = +0.0197. The positive test ICs do not extrapolate a positive train relationship — they flip. The signal is not stationary in sign, so the MARGINAL verdict should not be over-interpreted as a stable forward edge.
- Train IC is negative in fold(s) **[1, 4]** — the signal relationship inside those training windows flipped vs the subsequent test window.
- Sharpe is negative on test in fold(s) **[2]** despite the positive test IC — train-derived quintile cutoffs do not survive the intra-fold regime shift (costs + turnover eat the edge).
- Verdict = MARGINAL is the mechanical outcome of the spec rubric (5/5 positive folds, mean Sharpe ∈ [0.5, 1.0)) but the sign-inversion caveat above means this is not `SIGNAL_FOUND` even in spirit. Honest next step: live paper-trade a small size and watch whether fold-6 extends the 5/5 streak or breaks it.

## Invariants asserted
- train-frozen z-score (global AND per-fold)
- orthogonality gate vs momentum before any stacking
- walk-forward per-fold train/test split, no look-ahead, `fwd_return_1h` computed via `shift(-1)`
- hard rule: any non-positive test fold IC → verdict = `NO_SIGNAL`
