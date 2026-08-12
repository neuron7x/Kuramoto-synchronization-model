# Cross-Asset Kuramoto · Pipeline Audit (Phase 7)

**Status: PASS with documented caveat.** Data alignment and survivorship are clean; forward-fill is material and documented; latest bars are a fixed snapshot (not a live feed), so staleness vs the "now" clock is informational, not a live-pipeline breach.

## DP1. Time alignment

Master calendar: pandas `freq="B"` (Monday–Friday), UTC-localised.
Range: 2017-08-17 → 2026-04-10 ⇒ **2257 business days**.

| asset | native bars | bday-grid NaN rows | ffill(limit=3) filled | still NaN |
|---|---:|---:|---:|---:|
| BTC | 3160 (7-day market) | 0 | 0 | 0 |
| ETH | 3160 (7-day market) | 0 | 0 | 0 |
| SPY | 2173 | 84 | 84 | 0 |
| QQQ | 2173 | 84 | 84 | 0 |
| GLD | 2173 | 84 | 84 | 0 |
| TLT | 2173 | 84 | 84 | 0 |
| VIX | 2173 | 84 | 84 | 0 |
| DXY | 2175 | 82 | 82 | 0 |

Misalignment: **84 / 2257 = 3.72 %** of bday rows have at least one
missing TradFi asset (typical cause: US market holidays that are
business days in the pandas calendar). This is **below the 5 %
threshold (§11.DP1)**; no STOP. All 84 rows are successfully repaired
by `ffill(limit=3)` — the spike's frozen policy.

Timezone consistency: every asset's native CSV has a tz-aware index
(`2017-08-17 00:00:00+00:00`) parsed via `tz_convert("UTC")`; anything
naïve is `tz_localize("UTC")`. No mixed-tz rows.

## DP2. Survivorship / selection bias

The 8-asset regime universe (`BTC, ETH, SPY, QQQ, GLD, TLT, DXY, VIX`)
is **fixed** for the entire 2017-08-17 → 2026-04-10 window. No entry /
exit, no rebalanced constituent set.

Survivorship caveat is descriptive, not a bias: the universe was
chosen in the spike as the most-liquid cross-asset basket covering
risk-on (crypto, equity), risk-off (TLT, GLD), dollar (DXY), and
volatility (VIX). Any universe change would be a new research line,
not a pipeline fix.

## DP3. Data staleness

Each asset's last bar and age vs the current clock:

| asset | last_bar | age (days) |
|---|---|---:|
| BTC, ETH | 2026-04-11 | 11 |
| SPY, QQQ, GLD, TLT, DXY, VIX | 2026-04-10 | 12 |

Ages computed against "today" 2026-04-22. Both exceed the 5-business-day flag threshold (§11.DP3). **FLAG: demo-snapshot staleness.**

This is *expected* for a frozen spike snapshot (`METADATA.json.fetched_at = 2026-04-11T11:40:21Z`); it is not a live-feed defect. Any future live demo would refresh the data bundle and re-verify. The integrated module exposes `data_dir` as a parameter so a fresh bundle replaces the stale one without code change.

## DP4. Missing data

NaN counts in the raw concat (before bday reindex):

- BTC, ETH, SPY, QQQ, GLD, TLT, VIX, DXY: **0** NaN values in the
  native CSVs (all rows carry finite `close`).

Per the §3 NaN-treatment policy:

- No interpolation (forbidden); only forward-fill with strict `limit=3`.
- 84 rows filled once per affected asset (see DP1).
- Nothing is dropped at the close level; rows that still contain any
  NaN after ffill(limit=3) are dropped as aligned panel rows (count = 0).

## DP5. Forward-fill impact

Integrated-module OOS Sharpe (70/30 single-split test) with and
without `ffill(limit=3)`:

| variant | strategy days | OOS Sharpe | OOS max DD |
|---|---:|---:|---:|
| with `ffill(limit=3)` (baseline, frozen in lock) | 2167 | **1.2619** | −16.76 % |
| without `ffill` (inner-join drops bday holidays) | 2083 | **1.0426** | −15.88 % |
| absolute ΔSharpe | — | **0.2193** | — |

|ΔSharpe| = 0.22 > 0.1 ⇒ **forward-fill is material (§11.DP5)**. This is **documented**, not fixed; the spike deliberately forward-fills to keep crypto 7-day bars aligned with TradFi 5-day bars. Holding to the spike convention preserves reproducibility; swapping to no-ffill would be a behaviour change that requires a separate PR.

## Conclusion

| gate | outcome |
|---|---|
| §11.DP1 (>5 % misalignment → STOP) | 3.72 % ⇒ PASS |
| §11.DP1 (>1 % misalignment → document fix) | documented: `ffill(limit=3)` |
| §11.DP2 (survivorship) | fixed universe, no entry/exit |
| §11.DP3 (>5 bdays stale) | **FLAG**: demo snapshot 10–12 days old; not a live-pipeline defect |
| §11.DP4 (NaN treatment) | 0 NaN in raw; ffill covers bday-holiday mismatches |
| §11.DP5 (ffill materiality) | ΔSharpe 0.22 > 0.1 ⇒ **MATERIAL, documented** |

No §S7 stop triggered. One caveat (DP3) recorded.
