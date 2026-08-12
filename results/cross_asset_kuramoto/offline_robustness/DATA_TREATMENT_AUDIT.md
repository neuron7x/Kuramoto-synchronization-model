# Phase 2 · Data-treatment dependency audit

Signal/params/cost/lag/folds frozen. Only missing-data treatment varied. CSV: `data_treatment_audit.csv`.

## Results (OOS 70/30 test, 2023-10-13 → 2026-04-10)

| treatment | aligned | dropped | usable | OOS Sharpe | ΔSh vs frozen | max DD | admissible? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| `strict_drop_missing` (native only) | 2173 | 84 | 2083 | **1.043** | **−0.219** | −15.88 % | no |
| `forward_fill_limit_1` | 2257 | 0 | 2167 | **1.262** | 0.000 | −16.76 % | yes |
| `forward_fill_limit_3` (frozen) | 2257 | 0 | 2167 | **1.262** | 0.000 | −16.76 % | yes |
| `no_forward_fill_aligned_subset_only` | 2173 | 84 | 2083 | **1.043** | **−0.219** | −15.88 % | no |

## Key findings

**Fill materiality confirmed, not revised.** The 0.219 ΔSharpe between filled and unfilled treatments matches `PIPELINE_AUDIT.md#DP5` (ΔSharpe = 0.22) to two decimals. So the PIPELINE_AUDIT number was not a point estimate — it is the real substrate dependency.

**`limit=1` ≡ `limit=3` on this data.** Identical Sharpe, MDD, and bar counts. Implication: **every gap this panel actually contains is ≤ 1 day long.** The spike's `limit=3` choice therefore provides no additional gap-bridging on the observed history — it is *conservative tolerance* for future data, not current exploitation. That is relevant for live operations: wider gaps (e.g. long weekend + holiday + exchange outage) would only start to diverge between `limit=1` and `limit=3` when a ≥ 2-day contiguous hole appears.

**Sample geometry is the confounder, not fill per se.** `strict_drop_missing` and `no_forward_fill_aligned_subset_only` differ only in whether they touch the bday grid, but both drop the same 84 tradable-panel bars and land on the same 2083 usable days. Their Sharpe is identical. So the Sharpe delta against filled versions is driven by **which 84 days are in or out of the sample** (TradFi US holidays where crypto still trades), not by the fill operation's numerical artefact.

**Operational admissibility.** Only `ffill(limit=1)` and `ffill(limit=3)` are admissible for live deployment, because strict treatments discard days the paper trader and the spike backtest both include — mixing treatments across the offline/live boundary would break reproducibility.

## Answer to §9 brief

Substrate dependence is **material** (0.22 Sharpe), **confirmed** (not revised), and **fully attributable to sample geometry** (84 TradFi-holiday bars), not to the fill algorithm's numerical behaviour. The frozen `limit=3` choice and the tighter `limit=1` are indistinguishable on historical data; the frozen choice survives for future-robustness reasons documented in the spike.
