# Wave 1 · combo_v1 · VERDICT (Run B, net of per-asset costs)
- workspace SHA: `ef0b774bc4aeb093b843d9494d3b13612ab63e59`
- GeoSync SHA:   `8b68156df48f1d8ec7566a8db57fb71a66cf8622`
- run window OOS: 2008-01-02 21:00:00 → 2026-02-09 21:00:00  (4704 bars)
- folds: 222 valid / 222 total

## VERDICT: **FAIL**

> failing gates: primary Sharpe -0.0457<0.8; %positive 43.2%<60%; maxDD 0.4488>0.2

## Gate-by-gate (Run B)

| gate | value | threshold | pass |
|---|---:|---:|:---:|
| median fold-median Sharpe | -0.0457 | ≥ 0.8 | ✗ |
| % folds with positive median Sharpe | 43.2% | ≥ 60% | ✗ |
| 2022-touching folds median Sharpe | 0.1964 | ≥ 0 (n=15) | ✓ |
| max drawdown (OOS portfolio) | 0.4488 | ≤ 0.2 | ✗ |
| median turnover per bar (documented) | 0.0 | — | — |

## Baselines (Run B, informational)

| baseline | OOS Sharpe | max DD |
|---|---:|---:|
| buy_and_hold_eq_weight | -0.0427 | 0.1618 |
| combo_2bar_lag | -0.1529 | 0.423 |

_Neither baseline gates the verdict; reported for reference (§4.6)._

## Run A — gross (diagnostic, does NOT determine verdict)

- verdict-equivalent (if A were verdict): `FAIL`
- primary median Sharpe: -0.0046  (cost impact = 0.0411 Sharpe units)
- max drawdown: 0.4061  (Δ vs B = -0.0427)
