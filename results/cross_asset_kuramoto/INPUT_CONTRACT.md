# Cross-Asset Kuramoto · INPUT_CONTRACT (Phase 1)

**Prepared by:** Claude Code. **Resolved from spike artefacts on disk only** (§IC3.D1). No memory-based claims.
**Spike source composite SHA-256:** `9e76e3b511d31245239961e386901214ea3a4ccc549c87009e29b814f6576fe3` (of `sync_regime.py` + `backtest_v2.py` + `walk_forward.py` + `fetch_data.py`; spike not under git).
**Spike data bundle:** per `~/spikes/cross_asset_sync_regime/data/METADATA.json` (`fetched_at: 2026-04-11T11:40:21Z`), per-asset SHA-256 carried.

## IC1. Data paths

| kind | path | resolution |
|---|---|---|
| raw (Phase 1 regime) | `~/spikes/cross_asset_sync_regime/data/{btc_usdt_1d,eth_usdt_1d,spy_1d,qqq_1d,gld_1d,tlt_1d,dxy_1d,vix_1d}.csv` | `sync_regime.py::CACHE_MAP` lines 48–53 |
| raw (Phase 3 strategy) | subset: `btc_usdt_1d,eth_usdt_1d,spy_1d,tlt_1d,gld_1d` | `backtest_v2.py::load_asset_close.cache_map` lines 56–58 |
| intermediate regime state | `~/spikes/cross_asset_sync_regime/results/kuramoto_R_regimes.csv` | produced by Phase 1, loaded by Phase 3 (`backtest_v2.load_regimes`) |
| per-asset sha256 of input data | `~/spikes/cross_asset_sync_regime/data/METADATA.json` | content-addressed |

Integrated module reads from the same CSV layout via `INPUT_CONTRACT.json` pointer (below).

## IC2. Universe

**Regime universe (Phase 1 · 8 assets, ordered):**
`BTC, ETH, SPY, QQQ, GLD, TLT, DXY, VIX`
Source: `sync_regime.py::ASSETS` line 47.

**Strategy universe (Phase 3 · 5 assets, ordered):**
`BTC, ETH, SPY, TLT, GLD`
Source: `backtest_v2.py::run()` local `assets` line 255 + `walk_forward.py::walk_forward_validation()` `assets` line 92.

**Ticker format (code):** Python string constants listed above, uppercase, no separator. CSV `timestamp,open,high,low,close,volume`.

## IC3. Time specification

| field | value | source |
|---|---|---|
| timezone | **UTC** (enforced; `tz_localize("UTC")` if naïve, else `tz_convert("UTC")`) | `sync_regime.py::load_asset` L79–83, `backtest_v2.py::load_asset_close` L61–65 |
| bar close | daily bar at `00:00 UTC` of the next day *as labelled*; CSV rows are labelled at `YYYY-MM-DD 00:00:00+00:00` | CSV head: `2017-08-17 00:00:00+00:00` |
| sampling frequency | **daily**, aligned to pandas `freq="B"` (business days) master calendar | `build_panel` L90–94, `build_returns_panel` L70–75 |
| forward-return definition | `log(close[t+1] / close[t])` computed via `np.log(panel / panel.shift(1)).dropna()` | `compute_log_returns` L99–100 |

## IC4. Date range

| boundary | value | source |
|---|---|---|
| start | **2017-08-17** (earliest shared across 8 assets; BTC/ETH begin here) | METADATA.json `BTC.start` |
| end | **2026-04-10** (yfinance assets end) to **2026-04-11** (Binance assets) → canonical panel end after inner-join = **2026-04-10** | METADATA.json per-asset |
| total bars (regime panel, business days, ffill-3) | **2260** (aligned, log-return length 2259) | reproduced in Phase 4 |

## IC5. Walk-forward split

Expanding-window, 5 splits — source `walk_forward.py::WALK_FORWARD_SPLITS` L59–65:

| split | train IS | test OOS |
|---:|---|---|
| 1 | 2017-08-17 → 2020-01-01 | 2020-01-01 → 2021-01-01 |
| 2 | 2017-08-17 → 2021-01-01 | 2021-01-01 → 2022-01-01 |
| 3 | 2017-08-17 → 2022-01-01 | 2022-01-01 → 2023-01-01 |
| 4 | 2017-08-17 → 2023-01-01 | 2023-01-01 → 2024-01-01 |
| 5 | 2017-08-17 → 2024-01-01 | 2024-01-01 → 2026-05-01 |

Memory claim "4/5 pass on Sharpe": operational interpretation is `n_beats_btc_sharpe` (per `walk_forward.py::walk_forward_validation` summary). The **failing** split is the one where strategy Sharpe < BTC Sharpe. The JSON `~/spikes/cross_asset_sync_regime/results/walk_forward_summary.json` is authoritative for per-split values — the integrated module must match split-for-split.

## IC6. Missing data policy

| rule | value | source |
|---|---|---|
| forward fill | **yes, limit=3 business days** | `build_panel` L94, `build_returns_panel` L74 |
| drop | after ffill, `.dropna()` removes any remaining NaN rows | same |
| interpolation | **forbidden** — not used in spike | grep of spike: zero `interpolate` calls |
| NaN in detrended series before Hilbert | guarded (`mask = np.isfinite(x_detrend); analytic[mask] = hilbert(...)`; fail if `mask.sum() < DETREND_WINDOW + 10`) | `extract_phase` L116–121 |

## D1–D3 compliance

All paths/universe/time fields resolved from spike `.py` and `data/METADATA.json` — zero fields from memory. Protocol `STOP` not triggered.
