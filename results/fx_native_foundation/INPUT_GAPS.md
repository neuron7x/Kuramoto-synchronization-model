# FX-native foundation · input inventory & gaps (MODE_A)

Descriptive-only inventory of inputs that a credible FX-native line
would plausibly need, matched against what is **provably** available
in the repository at commit `1099458`. Sourced from the Askar data
audit report (`/home/neuro7/Downloads/аскар/data_audit_report.md`,
read-only) and the committed lock artefacts. No tradability claim is
made from this inventory alone.

| input class | required for | availability in repo | evidence |
|---|---|---|---|
| 8-FX majors OHLC, hourly, 2003–2026 | any FX line | **AVAILABLE** | `universe.json`, `panel_audit.json`, 5863 daily bars |
| DXY (US Dollar Index) OHLC | DXY-factor neutralisation, DXY-residual cross-section | **AVAILABLE** | Askar audit row 78: `US_Dollar_Index_GMT+0_NO-DST.parquet`, 44 121 hourly bars, 2017-12-01 → 2026-02-20 |
| Non-USD cross legs (EURGBP, EURJPY, …) | factor-neutralisation boundary cases | **AVAILABLE** (both in locked universe) | `universe.json#assets[6..7]` |
| G10 short-rate curve (1M / 3M / 6M / 1Y / 2Y) | carry, rate-differential, policy-path | **MISSING** | no rates parquet; audit shows only FX / equity indices / commodities / bond ETFs |
| Long-end sovereign yields (US 10Y, Bund, Gilt, JGB) | term-structure carry, policy residual | **PARTIALLY_AVAILABLE** via ETF prices only | `iShares_7-10_Year_Treasury_Bond_ETF` (row 46-ish), `iShares_20+_Year_Treasury_Bond_ETF`, `Euro_Bund_GMT+0_NO-DST.parquet`, `UK_Long_Gilt_GMT+0_NO-DST.parquet`, `US_T-Bond_GMT+0_NO-DST.parquet`. These are **price** series, not yields; yield proxies require log-return differencing which loses curvature information |
| Central-bank policy-path / MP surprises | policy-path residual signal | **MISSING** | no calendar / rate-decision / STIR futures data in repo |
| FX options IV surface / risk-reversal | vol-skew signals, carry-VIX interplay | **MISSING** | no options parquet |
| VIX / implied-vol proxies | risk-on / risk-off gating | **AVAILABLE** (cross-asset use only) | Askar row 42: `iPath_S_P_500_VIX_ST_Futures_ETN_GMT+0_NO-DST.parquet`, 2017–2026 |
| FX bid/ask / L2 depth | microstructure / OFI signals | **MISSING** | `data_audit_report.md` shows only OHLC columns in every FX parquet |
| Macro calendar (NFP, CPI, FOMC) | event-study / pre/post-event bias | **MISSING** | no calendar parquet |
| FX carry proxy via forward points | proxy for interest-rate differentials | **MISSING** | no forward-rate parquet; spot-only |

Summary by mechanism class:

| mechanism class | inputs status | implication |
|---|---|---|
| **DXY-residual cross-section** (price-only) | AVAILABLE | candidate corridor; post-demo |
| **Cross-asset Kuramoto applied to 8-FX** | AVAILABLE | cheap empirical floor-test; Track-B analogue to existing equities-only Track A |
| **Carry / rate-differential** | MISSING core inputs | blocked by §14.S4 until a real rates feed is ingested |
| **Policy-path residual** | MISSING | blocked |
| **FX options / vol-surface** | MISSING | blocked |
| **FX microstructure / OFI** | MISSING | blocked; `GeoSync-main/research/kernels/` microstructure kernels exist but require L2 which this panel does not carry |

Rates-proxy footnote: using bond-ETF price returns as a stand-in for
yield moves is a **known** approximation (changes in bond-ETF price ≈ −
duration × Δyield). It introduces a duration-scaling and roll-cost bias
that is not acceptable for a carry signal in isolation. Any FX-native
mechanism that needs real rates should not use this proxy without
explicit documentation and would still trigger the "PARTIALLY_AVAILABLE"
label in the mechanism brief.

Per §14.S4: any candidate FX-native mechanism that lands on a MISSING
row **must abort its own line** or explicitly request data ingestion.
Only the two AVAILABLE rows are valid corridors at MODE_A.
