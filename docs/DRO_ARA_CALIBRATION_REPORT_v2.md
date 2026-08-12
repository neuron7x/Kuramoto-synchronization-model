# DRO-ARA v7 · Walk-Forward Calibration Report v2 (post-patch)

**Date:** 2026-04-21
**Scope:** Threshold calibration of `(H_CRITICAL, RS_LONG_THRESH)` after
engine stationarity fix (PR #349).
**Status:** REJECT — do not modify engine constants.

---

## 1. Context

PR #345 shipped an RFC diagnosing a convention asymmetry in `core/dro_ara/engine.py`:
DFA computed Hurst on log-returns (line 138), but ADF tested stationarity on
raw prices. Empirically, 93–99 % of real-market train windows failed ADF,
collapsing INV-DRO3 to a near-tautology and making INV-DRO4's LONG-gate
permanently INVALID on live assets.

PR #349 fixed the convention (`core/dro_ara/engine.py:State.from_window`):
ADF now runs on `np.diff(np.log(|arr| + 1e-12))`, aligning both statistical
tests to the same transform.

This v2 report re-runs the walk-forward H × rs grid search on five askar
assets with the patched engine. The v1 report (under PR #345) documented the
pre-patch degeneracy; v2 documents the post-patch state and the resulting
calibration decision.

## 2. Grid parameters

- H grid: `np.arange(0.30, 0.65, 0.05)` → 7 values
- rs grid: `np.arange(0.10, 0.65, 0.05)` → 11 values
- 7 × 11 = 77 (H, rs) cells
- Walk-forward: train=252, test=63, step=21, min_history=504 (trading days)
- Signal: combo_v1 `AMMComboStrategy` (read-only), gated by DRO-ARA regime
- Backtest: `vectorized_backtest`, fee=5 bp, shift=1 anti-lookahead
- Rejection filters: mean Sharpe ≥ 0.80, worst DD ≤ 0.25, mean trades ≥ 20

## 3. Multi-asset evidence

| asset       | n_folds | active_cells | active_folds | best (H, rs) | best mean Sharpe | best_n_folds | passing pairs |
|-------------|--------:|-------------:|-------------:|:-------------|-----------------:|-------------:|--------------:|
| SPDR S&P500 |      69 |          159 |           17 | (0.40, 0.10) |          −0.0114 |            3 |             0 |
| XAUUSD      |     286 |          619 |           62 | (0.30, 0.10) |          +0.0051 |            1 |             0 |
| USA 500 Idx |     150 |          562 |           49 | (0.50, 0.35) |          −0.0081 |            3 |             0 |
| EURGBP      |     297 |        1 251 |          115 | (0.35, 0.10) |          −0.0199 |            7 |             0 |
| EURUSD      |     301 |          599 |           68 | (0.50, 0.35) |          −0.0096 |            1 |             0 |

Source artefacts: `experiments/dro_ara_calibration/results/multi_asset/`
(`{asset}_grid.csv`, `{asset}_summary.json`, `{asset}_heatmap.png`,
`aggregate.json`). All assets processed with the identical grid and protocol.

## 4. INV-DRO3 tightening validated

Engine patch impact on stationarity rate (one per fold):

| asset       | pre-patch | post-patch |
|-------------|----------:|-----------:|
| SPDR S&P500 |       1.4 % |     100.0 % |
| USA 500 Idx |       0.0 % |     100.0 % |
| XAUUSD      |       1.4 % |     100.0 % |
| EURGBP      |       7.1 % |     100.0 % |
| EURUSD      |       5.0 % |     100.0 % |

INV-DRO3 now encodes a real unit-root test on returns, as intended.
The tightening is guarded by
`tests/core/dro_ara/test_invariants.py::test_inv_dro3_tightening_post_rfc_ou_stationary_rate`.

## 5. Decision tree resolution

Per T4 calibration contract:

```
active cells > 0              → YES (across all 5 assets)
best mean Sharpe > 0          → only XAUUSD (+0.005 on n=1 fold) — statistically zero
passes_filters exists         → ZERO on all 5 assets (none meets Sharpe ≥ 0.80)
ΔH ≤ 0.10 ∧ Δrs ≤ 0.10        → no, Δrs = 0.23 on SPDR, similar on others
ΔH > 0.20 ∨ Δrs > 0.30        → partially, Δrs > 0.20 on SPDR
```

Verdict per `experiments/dro_ara_calibration/run_grid_search.py::write_report`:

> **STRATEGY_UNPROFITABLE / REJECT** — 20 (H, rs) pairs activated the gate on
> SPDR, but the best mean OOS Sharpe across all active cells is −0.011 (≤ 0).
> The combo_v1 × DRO-ARA pipeline does not produce a profitable edge on this
> asset at this bar granularity. Threshold tuning cannot fix a non-existent
> signal.

Same verdict on all 4 other assets.

## 6. Why combo_v1 × DRO-ARA is unprofitable on daily OHLC

Three hypotheses, ranked by plausibility:

1. **Granularity mismatch.** `AMMComboStrategy` was designed for high-frequency
   adaptive inference (`ema_span=32`, `vol_lambda=0.94`). At daily bars a
   32-bar EMA spans 32 trading days — the AMM never reaches steady state on
   a 63-bar test window.
2. **Impoverished upstream features.** Calibration harness feeds constant
   `R=0.6` and `κ=0.1` (matching canonical unit-test wiring), but production
   combo_v1 expects live Kuramoto R(t) and Ricci κ(t) from upstream physics.
   Without those, half the logic inside `AdaptiveMarketMind.update` collapses.
3. **Fee drag.** 5 bp per turnover on 20 trades over 63 bars = 100 bp/fold
   edge requirement — combo_v1's baseline alpha on daily bars is thinner.

None of these are threshold-tunable. They are upstream-integration and
data-frequency issues.

## 7. Recommendation

1. **DO NOT modify** `H_CRITICAL` or `RS_LONG_THRESH` in
   `core/dro_ara/engine.py`.
2. The RFC §9 sign-off (APPROVED) materialised in PR #349 as intended.
   INV-DRO3 fix is complete; engine is sound.
3. Future work that *could* change the verdict (not a threshold tune —
   upstream integration):
   - Re-run calibration on hourly/minute parquet bars (data/askar/* is
     already hourly; daily resampling was chosen for unit consistency with
     the task spec).
   - Replace the constant `(R, κ, H)` stub with a live upstream physics
     stream (Kuramoto + Ricci pipelines already exist in `core/physics/`).
   - Re-evaluate on mean-reversion-rich asset pairs (statistical
     arbitrage baskets, FX crosses with persistent spreads).
4. Artefacts from this run are preserved under
   `experiments/dro_ara_calibration/results/multi_asset/` for reproducibility.

## 8. Fail-closed audit (T2)

PR #349 carried the full audit: 8/8 property tests, 14 Hypothesis fuzz
strategies, SPDR 69-fold smoke (≥ 20 % gate-on), **11 274 passed / 0 failed**
repo-wide regression, ruff + black + mypy --strict clean. No invariants
relaxed. Merge `0864a8d` on main.

---

_Artefacts: `experiments/dro_ara_calibration/`_
_Primary canonical run (overwritten with SPDR each call): `docs/DRO_ARA_CALIBRATION_REPORT.md`_
_Supporting RFC: `docs/RFC_DRO_ARA_STATIONARITY_CONVENTION.md`_
