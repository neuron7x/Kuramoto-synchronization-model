# Phase 1 · Leave-one-asset-out robustness

Frozen. Two LOO sweeps. CSV: `leave_one_asset_out.csv`.

Baseline: OOS Sharpe **1.262**, MDD −16.76 %, ann ret +23.58 %, fold-3 Sharpe −1.146.

## Regime LOO (R(t) on 7 of 8)

| omit | OOS Sharpe | ΔSh | max DD | ΔMDD |
|---|---:|---:|---:|---:|
| BTC | 1.503 | +0.24 | −17.05 % | −0.29 |
| ETH | **1.620** | **+0.36** | −18.52 % | −1.75 |
| SPY | 1.590 | +0.33 | −18.72 % | −1.96 |
| QQQ | 1.303 | +0.04 | −17.34 % | −0.58 |
| GLD | 1.315 | +0.05 | −16.55 % | +0.21 |
| TLT | 1.231 | −0.03 | −14.55 % | +2.21 |
| DXY | 1.572 | +0.31 | −16.94 % | −0.17 |
| VIX | 1.257 | −0.005 | −11.50 % | **+5.27** |

**No single regime asset is load-bearing.** Sharpe stays in [1.23, 1.62]. Four omissions (BTC/ETH/SPY/DXY) *increase* Sharpe by +0.24..+0.36 → those add phase-sync noise. VIX-omission cuts max DD by 5.27 pp.

## Tradable LOO (omit one of 5 traded)

| omit | OOS Sharpe | ΔSh | max DD | ΔMDD | note |
|---|---:|---:|---:|---:|---|
| BTC | 1.141 | −0.12 | −15.06 % | +1.70 | low-sync bucket halved |
| ETH | 1.251 | −0.01 | −10.24 % | **+6.52** | low-sync → BTC-only |
| **SPY** | **1.262** | **0.00** | −16.76 % | 0.00 | SPY is in **no** bucket; exact no-op ✓ |
| TLT | **1.731** | **+0.47** | −15.69 % | +1.07 | high-sync → GLD-only; GLD outperforms TLT-GLD blend OOS |
| GLD | **0.532** | **−0.73** | **−23.02 %** | **−6.25** | high-sync → TLT-only; biggest concentration exposure |

**GLD is load-bearing.** Drop → Sharpe collapses 1.26→0.53 (−58 %), MDD −6 pp. Flight-to-safety is majority-GLD, not 50/50 TLT-GLD.

**SPY is inert.** It is in no bucket (`low={BTC,ETH}`, `mid={BTC,ETH,TLT,GLD}`, `high={TLT,GLD}`); weight identically 0 every bar. Δ-0 row is a mechanical consistency check.

**Benchmark parity (§ tradable LOO):** BTC buy-and-hold benchmark does not depend on tradable membership → `benchmark_recomputed=no` for every row.

## §L9 answers

- Broad vs concentrated: regime broad (any-of-8 removable); tradable concentrated in GLD, with TLT displaceable.
- R(t) one-member dependent: **no** — 8/8 omissions keep Sharpe ≥ 1.23.
- PnL one-asset dependent: **yes, GLD** — losing it takes Sharpe below the 0.80 demo gate.

Fold 3 (2022) stays negative in every configuration → 2022 limitation is signal-robust, not concentration artefact.
