# Cross-Asset Kuramoto · Numeric Reproduction (Phase 4)

**Verdict: `PASS`** — `max_abs_dev` across every compared series is at
machine-epsilon order, well below the 1e-10 success target and the
1e-7 hard-stop.

## Compared artefacts

Integrated module (`core/cross_asset_kuramoto/`) vs spike outputs on
disk in `~/spikes/cross_asset_sync_regime/results/`:

- `kuramoto_R_regimes.csv` — R(t) and regime label per bar.
- `strategy_v2_returns.csv` — gross / net / turnover / leverage per bar.
- `phase4_backtest_v2.json` — train / test Sharpe, MDD and annualised stats.

Data source for both: `~/spikes/cross_asset_sync_regime/data/` (the
same 8 per-asset CSVs pinned in `data/METADATA.json`).

## Per-series deltas

| series | common bars | max_abs_dev | sign_match | rank_corr |
|---|---:|---:|---:|---:|
| R(t)             | 2168 | **8.33e-17** | 1.0000 | 1.000000 |
| regime label     | 2168 | 100 % string match | — | — |
| gross_ret        | 2167 | **9.99e-17** | — | — |
| net_ret          | 2167 | **9.99e-17** | — | — |
| turnover         | 2167 | **2.22e-16** | — | — |
| leverage         | 2167 | **2.22e-16** | — | — |

All deviations are at the IEEE-754 double-precision round-off
boundary. By the §8 ladder:

- `max_abs_dev < 1e-10` → **PASS** on every series.
- No series enters `WARN_NUMERIC_DRIFT` (< 1e-7) or `STOP` (≥ 1e-7).

## Top-line Sharpe / MDD reproduction

| metric | spike on-disk | integrated | Δ |
|---|---:|---:|---:|
| TEST Sharpe (70/30, OOS start 2023-10-13) | 1.26185000 | 1.26185000 | < 1e-9 |
| TRAIN Sharpe                               | 0.15275692 | 0.15275692 | < 1e-9 |
| TEST max drawdown                          | −0.1676   | −0.1676    | < 1e-9 |
| TEST ann return                            |  0.2358   |  0.2358    | < 1e-9 |

Cross-check against memory-claimed OOS Sharpe = **+1.262** (per
`project_cross_asset_sync.md`): matches to four decimals.

## Sources of residual noise

The only ~2e-16 residual arises from pandas column-order variation
under `pd.concat(..., sort=False)` when the underlying arrays are
dispatched through `np.clip` / `np.sqrt` etc. It is bit-for-bit
reproducible within one process but can shift by one ULP between two
processes with differing BLAS / MKL threading. The integrated module
inherits this property from the spike without addition.

## Conclusion

INV-CAK3 (determinism) and numeric-reproduction §8 PASS are both
satisfied. No WARN_NUMERIC_DRIFT caveat required. No §S4 STOP.
