# FX-native foundation · Data contract (MODE_A_PRE_DEMO)

**Locked UTC:** 2026-04-22
**Prepared by:** Claude Code (MODE_A execution, §3 of FX-native protocol)
**Audience:** any future FX-native line that wants to stay comparable to
the closed combo_v1 × 8-FX substrate.

This contract is resolved from authoritative repository artefacts only.
No paths are guessed. If any resolution failed, the protocol would have
stopped per §14.S1; it did not.

---

## 1. Canonical raw data paths

| asset | file | resolved via |
|---|---|---|
| EURUSD | `/home/neuro7/Downloads/аскар/TransferNow-202604101WrhmK3D/EURUSD_GMT+0_NO-DST.parquet` | `results/wave1_fx/universe.json#assets[0].file` + `#data_root` |
| GBPUSD | `…/GBPUSD_GMT+0_NO-DST.parquet` | universe.json#assets[1] |
| USDJPY | `…/USDJPY_GMT+0_NO-DST.parquet` | universe.json#assets[2] |
| AUDUSD | `…/AUDUSD_GMT+0_NO-DST.parquet` | universe.json#assets[3] |
| USDCAD | `…/USDCAD_GMT+0_NO-DST.parquet` | universe.json#assets[4] |
| USDCHF | `…/USDCHF_GMT+0_NO-DST.parquet` | universe.json#assets[5] |
| EURGBP | `…/EURGBP_GMT+0_NO-DST.parquet` | universe.json#assets[6] |
| EURJPY | `…/EURJPY_GMT+0_NO-DST.parquet` | universe.json#assets[7] |

`data_root` value from `universe.json`:
`/home/neuro7/Downloads/аскар/TransferNow-202604101WrhmK3D`.

Upstream audit: `/home/neuro7/Downloads/аскар/data_audit_report.md`
(116 files inventory, SHA-available).

## 2. Canonical processed data paths

No committed processed panel exists. The daily panel is recomputed
deterministically from the 8 raw parquets by `preflight_v2.py` (locked at
commit `ef0b774`) and written only as audit metadata in
`results/wave1_fx/panel_audit.json`. Any FX-native line that wants
byte-for-byte reproducibility of the Wave 1 panel should re-invoke
`preflight_v2.py::load_clean_hourly` + `resample_daily_21utc` +
`pd.concat(... dropna()).dropna()`.

## 3. Exact 8-FX universe

Frozen: `EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, EURGBP, EURJPY`.
Same order as `results/wave1_fx/universe.json#assets[*].symbol`.

## 4. Exact ticker naming convention

`<SYMBOL>_GMT+0_NO-DST.parquet` where `<SYMBOL>` is 6-char ISO FX code
uppercase, no separator. Parquet columns: `ts` (`datetime64[us]`),
`open`, `high`, `low`, `close` (all `float64`). No `volume`, no
`corrupt_ts` flag column (see §5.cleaning).

## 5. Exact date range

| boundary | raw hourly | daily panel (inner-join 21:00 UTC) |
|---|---|---|
| first bar | 2003-05-04 22:00 UTC (EURUSD/GBPUSD/USDJPY), 2003-08-03/04 (others) | **2003-08-04 21:00 UTC** |
| last bar | 2026-02-23 00:00 UTC | **2026-02-23 21:00 UTC** |
| daily bars | — | **5863** |
| log-return bars | — | **5862** (2003-08-05 21:00 → 2026-02-23 21:00) |

Source of truth: `results/wave1_fx/panel_audit.json`.

## 6. Exact sampling frequency

- Native: **hourly** closes (23 bars per UTC weekday; Sat no data; Sun
  bars start ≈ 21:00 UTC in Sydney session).
- Canonical for Wave 1 and for any comparable FX-native line:
  **daily, resampled to the 21:00-UTC close of each calendar day that
  has at least one hourly bar at `ts.hour ≤ 21`.**

## 7. Exact time convention

- All `ts` values are UTC, zero offset, **no DST** (vendor tag
  `GMT+0_NO-DST`).
- Daily bar label is stamped at **`21:00:00` UTC** of its calendar day
  (rebalance clock). Computed by
  `preflight_v2.resample_daily_21utc()`: per UTC calendar day, take
  the last hourly close with `ts.hour ≤ 21`, reindex to
  `YYYY-MM-DD 21:00:00`.

## 8. Exact bar close convention

- Hourly: parquet `close` is the close of the hourly bar whose timestamp
  is its **start**. (A bar with `ts = 2003-05-04 22:00:00` covers
  22:00→23:00 UTC; its `close` is the last price in that window.)
- Daily: the daily `close` at 21:00 UTC on day D is the **hourly `close`
  of the last hourly bar with `ts.hour ≤ 21` on day D**. If that bar is
  `21:00:00`, it contains prices from 21:00→22:00; if it is `20:00:00`,
  the daily bar is built from the 20:00→21:00 window and carries a ≤ 1-hour
  staleness. Cleaning (§2 of Wave 1 `PREREG.md`): drop hourly rows with
  `ts.dt.year < 1990` (audit flag) or duplicate `ts`. GBPUSD / USDJPY
  each have 1 drop (year-0 / year-2 AD artefacts).

## 9. Exact source-of-truth artefacts used to resolve the contract

| item | artefact | SHA |
|---|---|---|
| universe + per-asset files + data_root | `results/wave1_fx/universe.json` | locked at `ef0b774` |
| panel shape + drop counts + timestamps | `results/wave1_fx/panel_audit.json` | commit `ef0b774` |
| fold schedule (222 folds) | `results/wave1_fx/fold_manifest.csv` | `ef0b774` |
| loader code | `preflight_v2.py` | `ef0b774` |
| registry metadata | `config/research_line_registry.yaml#lines.combo_v1_fx_wave1` | commit `1099458` |
| human-readable closure | `results/wave1_fx/CANONICAL_FAIL_NOTE.md` | `1099458` |
| upstream audit report | `/home/neuro7/Downloads/аскар/data_audit_report.md` | author-provided, 2026-04-21 |

## 10. Does this contract match the closed Wave 1 substrate exactly?

**YES — bit-identical by construction.** Any FX-native foundation work
that uses this contract is comparable to the closed combo_v1 line on:
universe, per-pair file, raw cleaning rule, daily close convention,
panel-bar count, log-return count, fold manifest.

### Forbidden reinterpretations (per §14.S2 and §8 of `PREREG.md`)

Changing any of the following while claiming "the same FX substrate"
would silently re-open the closed line:

- swap parquet source (data_root, data_audit)
- widen or narrow the 8-pair universe
- redefine rebalance clock (UTC hour, DST handling, "last" semantics)
- redefine cleaning (drop threshold, duplicate handling)
- change inner-join to outer/left/right
- change daily-bar label time

If a new FX-native line needs a different substrate, that is a
legitimate change — but the line_id must be new, the registry entry
must be new, and this DATA_CONTRACT.md must not claim equivalence.
