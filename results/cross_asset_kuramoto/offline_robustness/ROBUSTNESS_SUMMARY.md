# Cross-Asset Kuramoto · Offline Robustness Summary

Five-phase packet run in parallel to the live shadow validation; no
protected artefact mutated (NI verdict: **PASS**, 28/28 hashes intact).
Live shadow timer and spike cron untouched.

## Phase 1 · Leave-one-asset-out

- **Regime universe is broad-based.** 8/8 regime-LOO omissions leave
  OOS Sharpe in [1.23, 1.62]. Four (BTC, ETH, SPY, DXY) *increase*
  Sharpe when removed — those nodes add phase-sync noise on this
  substrate.
- **Tradable universe concentrates in GLD.** Removing GLD collapses
  Sharpe 1.26 → 0.53 and widens max DD by 6 pp. **Losing GLD takes
  the strategy below the 0.80 demo gate.**
- **SPY trades zero bars** (in none of the regime buckets) — inclusion
  is spec-residual, not structural; Phase 1 is a mechanical proof.
- Fold 3 (2022) stays negative in every LOO configuration — the
  known-failing fold is signal-robust, not concentration artefact.

## Phase 2 · Data-treatment audit

- ΔSharpe 0.22 between filled and unfilled treatments **confirmed**
  (matches `PIPELINE_AUDIT.md#DP5` to two decimals).
- `ffill(limit=1)` ≡ `ffill(limit=3)` bit-exactly — every gap in
  observed data is ≤ 1 day. The spec's `limit=3` is conservative
  future-tolerance, not current exploitation.
- Substrate dependence is sample-geometry-driven (84 TradFi-holiday
  bars), not fill-algorithm numerical artefact.

## Phase 3 · Asset attribution & drawdown anatomy

- **GLD carries 63 %** of OOS net log-return; BTC 29 %, ETH 22 %.
  **TLT contributes −13.5 %** — it is a net drag over this window
  (hit rate 47.5 %, cost drag 2.2 pp on ~22 pp of turnover). Phase-1
  tradable-LOO result (dropping TLT raises Sharpe 1.26 → 1.73) is
  exactly attributable to this negative contribution.
- Top-3 OOS drawdowns: DD-1 / DD-2 are **crypto events** (ETH
  dominant), DD-3 is a **TLT event** (52 % of window loss).

## Phase 4 · Benchmark family

Kuramoto (1.262) > BF1 equal-weight buy-hold (0.872) > BF4
vol-targeted EW (0.843) > BF2 BTC buy-hold (0.802) > BF3 fixed-20-bar
momentum (0.752). Excess Sharpe is 0.39 (vs BF1) to 0.51 (vs BF3).
BF4 wins on max DD alone (13.1 % vs 16.8 %) but loses 60 % of the
annualized return to buy its DD safety. Under matched cost/lag
parity, **no benchmark advantage came from zero-cost arithmetic.**

## Phase 5 · Envelope stress

Block-bootstrap (seed 20260501, block 20, 500 paths) at 20/40/60/90
bars:

- 90-bar median cumret +3.63 %; p05 floor −16.29 %; p05 max-DD 20.86 %
  (below the 25.14 % live drawdown gate).
- **Recovery probability after early dip stays below 14 %** at every
  horizon. Historical blocks rarely climb from `below_p25` back to
  `above_p50`. The shadow engine's pessimistic labelling of sustained
  `below_p25` is appropriate under this distribution.

## Phase 6 · Risk overlay

**SKIPPED.** Optional phase; `RISK_OVERLAY_EXPLORATORY.md` not
produced. No parameter search occurred anywhere in the packet.

## Structural verdict (offline, not deployment)

1. **Regime panel redundancy is real** — removing any single regime
   node is safe; four omissions even improve Sharpe.
2. **Tradable concentration is real** — GLD is the single load-bearing
   position; TLT is a net drag on this window. This is the single
   most important structural truth in the packet.
3. **Fill policy is material and documented** — ΔSharpe 0.22, sample
   geometry, not algorithmic magic.
4. **Benchmark-relative value is real** — Kuramoto +0.39..+0.51 Sharpe
   excess across four baselines with matched cost/lag.
5. **Early-live dips rarely recover** per envelope stress — the
   shadow gate's pessimistic labelling is calibration-consistent.

## What this does NOT authorise

No deployment. No tuning. No parameter change. No universe change. No
modification to the live shadow rail. **`combo_v1` stays closed.
FX-native line stays deferred.** The `systemd.timer` keeps ticking.
