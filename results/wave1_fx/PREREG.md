# WAVE 1 · FAIL-CLOSED PRE-REGISTRATION v2 (LOCKED)

**Locked UTC**: 2026-04-21
**Locked by**: neuron7x@ukr.net
**GeoSync SHA at lock**: `8b68156df48f1d8ec7566a8db57fb71a66cf8622`
**Workspace SHA**: captured at first commit that includes this file
(see `lockfile_v2.txt` in repo root). Supersedes `../PREREG.md` (v1).

Verdict is the mechanical outcome of §4. No post-hoc modifications.

---

## §1. SIGNAL (frozen, read-only)

```
target:     var ∈ {EURUSD, GBPUSD, USDJPY, AUDUSD,
                   USDCAD, USDCHF, EURGBP, EURJPY}
module:     research.askar.full_validation.build_signal
parameters: window=120, threshold=0.30, col="combo"
graph:      full 8-asset Forman-Ricci on the daily-log-returns panel
invocation: build_signal(returns_8x1, target=T, window=120, threshold=0.30)
output col: "combo" = z_score(delta_Ricci, 120) − 0.5 · z_score(Ricci_mean, 120)
```

Loaded at GeoSync SHA `8b68156df48f1d8ec7566a8db57fb71a66cf8622` via
`sys.path.insert`. Zero patches. Any signal exception → HALT.

## §2. UNIVERSE & DATA

- 8 FX majors (see `universe.json`).
- Hourly → daily close. Daily close = last hourly close at or before
  21:00 UTC of each calendar day; daily bar is stamped at 21:00 UTC.
  This defines the rebalance clock.
- Cleaning: drop rows with `ts.year < 1990` (replicates audit
  `corrupt_ts` flag; GBPUSD, USDJPY → 1 each) and duplicate `ts`.
  Assets not excluded for having ≥1 drop.
- Inner-join on daily date → one aligned 8-asset panel.

## §3. WALK-FORWARD (frozen, pre-computed in `fold_manifest.csv`)

- Train: 252 trading-day bars
- Test:  63 trading-day bars (out-of-sample)
- Step:  21 trading-day bars
- Min history before test: 504 bars
- First test start ≥ 2008-01-01 (first available trading bar on/after)
- Last test end ≤ 2026-02-20
- Total folds: computed from data, locked in `fold_manifest.csv` BEFORE
  any run.

## §4. VERDICT CRITERIA (binary, applied to Run B only)

**PASS iff ALL of:**

1. `median(fold_median_sharpe) ≥ 0.80` across all folds (primary)
2. `fraction_folds_with_fold_median_sharpe > 0 ≥ 0.60`
3. `median(fold_median_sharpe | fold touches 2022) ≥ 0`
4. `max_drawdown_oos_portfolio ≤ 0.20` (on chained OOS equity curve)

**Also reported (not gated):**

5. `median_turnover_per_bar` — documented.
6. Null baselines:
   - buy-and-hold equal-weight 8 FX (long only, 1/8 each, no rebalance)
   - combo with 2-bar signal-to-trade lag (vs §5 locked 1-bar)
   Both measured over the same chained OOS period.

Verdict run = **Run B (net of per-asset costs)**. Run A (gross) is
diagnostic only and does NOT determine verdict.

Anything else → FAIL. No third option. INCONCLUSIVE iff < 10 valid
folds.

## §5. POSITION CONSTRUCTION (frozen)

- At each daily close (21:00 UTC, rebalance clock):
  1. Compute `combo_T(t)` for every target T in the 8-FX universe.
  2. Rank the 8 `combo_T(t)` values at bar t.
  3. `w_T(t) = +0.5` for the top-2 ranks (long leg).
  4. `w_T(t) = −0.5` for the bottom-2 ranks (short leg).
  5. `w_T(t) =  0`  for the middle 4.
  6. Ties: stable tie-break by symbol alphabetical order.
- Portfolio is **dollar-neutral**: Σ w = 0; **equal weight** within
  each leg (2 long × 0.5 = +1, 2 short × 0.5 = −1).
- **Signal-to-trade lag = 1 bar**: positions decided at close of bar t
  are applied to the log-return of bar t+1.
- Per-asset realised return on bar t+1:
  `contrib_T(t+1) = w_T(t) · r_T(t+1) − |w_T(t) − w_T(t−1)| · bps_T / 10_000`
  (where `bps_T` follows §6 per-asset table for Run B, or 0 for Run A).
- Portfolio return = Σ_T contrib_T(t+1).

## §6. COSTS (frozen — two mandatory runs)

**Run A — cost_bps = 0 for every asset.** Diagnostic only; used to
isolate alpha from execution drag. Does NOT determine verdict.

**Run B — per-asset costs (verdict run):**

| asset  | cost_bps |
|--------|----------|
| EURUSD | 1.0 |
| GBPUSD | 1.0 |
| AUDUSD | 1.0 |
| USDJPY | 1.5 |
| USDCAD | 1.5 |
| USDCHF | 1.5 |
| EURGBP | 1.5 |
| EURJPY | 1.5 |

Applied on `|Δw_T|` per bar (absolute weight change → round-trip
bps equivalent).

## §7. AGGREGATION

- For each (fold, target) pair: Sharpe of `contrib_T` over the fold's
  63-bar test period, annualised with `bars_per_year = 252`.
- `fold_median_sharpe = median_{T∈8}(sharpe_{fold,T})`.
- **Primary metric = median over folds of `fold_median_sharpe`.**
- Fold exclusion: a fold where any asset has missing-frac > 0.05
  (shouldn't happen post inner-join, but checked per §2) marks
  `is_valid = False` and is excluded from the primary metric.

## §8. FORBIDDEN AFTER LOCK

- Change universe
- Change signal parameters (window, threshold, col name)
- Change position rule (top-k, weights, lag)
- Exclude valid folds from mean/median
- Re-run with different window after seeing results
- Report best-asset subset instead of the locked full panel
- Switch verdict run (B is the verdict, A is diagnostic)

## §9. ARTEFACTS (append-only)

```
results/wave1_fx/universe.json            (locked)
results/wave1_fx/PREREG.md                (this file, locked)
results/wave1_fx/fold_manifest.csv        (locked)
results/wave1_fx/run_a_gross/per_target_fold.csv
results/wave1_fx/run_a_gross/folds.csv
results/wave1_fx/run_a_gross/portfolio_equity.csv
results/wave1_fx/run_a_gross/summary.json
results/wave1_fx/run_b_net/per_target_fold.csv
results/wave1_fx/run_b_net/folds.csv
results/wave1_fx/run_b_net/portfolio_equity.csv
results/wave1_fx/run_b_net/summary.json
results/wave1_fx/VERDICT.md               (human-readable, Run B only)
```

Every run appends to `run.log` with timestamp, workspace SHA, GeoSync SHA.
