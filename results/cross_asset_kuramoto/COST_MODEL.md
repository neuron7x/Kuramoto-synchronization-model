# Cross-Asset Kuramoto · Cost & Latency Model (Phase 6)

**Verdict: `PASS`.** Cost is non-zero (INV-CAK5 ✓); Sharpe_2x = 1.15 > 0
(§10.CM1 ✓); baseline cost 10 bps is within the stated 5–30 bps band
(§10 default).

## Cost definition (from `PARAMETER_LOCK.json`)

| field | value | notes |
|---|---|---|
| cost_unit | bps | on notional traded |
| baseline_cost_bps | **10** | FROZEN_AT_SPIKE_VALUE (backtest_v2.py `COST_BPS`) |
| turnover_definition | `Σ |w_t − w_{t−1}|` per bar | backtest_v2.py L157 |
| application | `cost = turnover · cost_bps / 10_000` | backtest_v2.py L163–164 |
| execution_lag_bars | **1** | MANDATORY per §10.latency (regime lagged by 1 bar) |

10 bps on retail-crypto daily trading is a mid-range estimate — tight
enough to matter, loose enough to reflect realistic spread + slippage
on BTC/ETH/SPY/TLT/GLD at the 30-day rebalance horizon this strategy
exhibits. No alternative cost unit (fixed $, volume-linked, etc.) is
considered at demo stage.

## Latency

Baseline **1-bar lag** is enforced inside `simulate_rp_strategy` via
`regimes_lag = regimes.shift(execution_lag_bars)` with
`execution_lag_bars = 1` frozen in the parameter lock (INV-CAK1). Setting
the lag to 0 is syntactically possible but INV-CAK5's cost-required
invariant would still fire on any non-cost-free metric call. The test
`test_no_future_leak.py::test_signal_uses_only_past_bars_for_kuramoto`
further enforces causality of the rolling Kuramoto R(t).

## Cost sensitivity (test window = 70/30 split OOS, 2023-10-13 → 2026-04-10)

| multiplier | cost_bps | Sharpe | max DD | ann return | cost drag (log) | drag / gross |
|---:|---:|---:|---:|---:|---:|---:|
| 1× | 10 | **1.2619** | −16.76 % | +23.58 % | 0.0549 | **8.27 %** |
| 2× | 20 | **1.1469** | −16.98 % | +21.46 % | 0.1098 | **16.54 %** |
| 3× | 30 | **1.0318** | −17.20 % | +19.33 % | 0.1647 | **24.80 %** |

Interpretation:

- Doubling costs (10 → 20 bps) subtracts ~0.115 Sharpe — the strategy
  **does not collapse** under 2× baseline cost. §10.CM1 (`Sharpe_2x < 0.0 → STOP`)
  is not triggered; §10.CM2 (`Sharpe_2x < 0.5 → COST_SENSITIVE`) is
  also not triggered.
- Tripling costs (10 → 30 bps) leaves Sharpe at 1.03 — still above 1.0.
  The signal survives under 3× baseline cost (corresponding to
  ~30 bps, the upper end of retail-crypto cost bands).
- Cost drag is 8.3 % of gross at baseline and 24.8 % at 3×. Linear in
  cost_bps, as expected from the formula `cost = turnover · cost_bps / 10_000`.

## Annualised cost footprint

Mean per-bar OOS turnover ≈ 0.8436 (sum of absolute weight changes per
day). With 252 bars per year and 10 bps per turnover unit, annualised
cost footprint ≈ **213 bps per year** (~2.1 % of notional). Cost drag
in Sharpe units (Sharpe_1x − Sharpe_2x) = 0.115, consistent with a
linear scaling (Sharpe_3x − Sharpe_1x ≈ 2× the 1×→2× delta).

## §10 disposition

| gate | condition | outcome |
|---|---|---|
| CM1 | `Sharpe_2x < 0.0 → STOP` | Sharpe_2x = 1.15 → PASS |
| CM2 | `Sharpe_2x < 0.5 → FLAG COST_SENSITIVE` | Sharpe_2x = 1.15 → no flag |
| CM3 | baseline cost > 0 | 10 bps → PASS (INV-CAK5 ✓) |
| CM4 | report drag in bps and % of gross | done above |

## Caveats documented (not fail gates)

- The 10 bps figure is a vendor-free estimate. Real execution through
  BTC/ETH order books at retail spreads can exceed 10 bps at small
  fill sizes; this is acknowledged in the spike's `PUBLIC_REPORT.md`
  and is not fixed here.
- Slippage scaling with position size is **not** modeled — the cost
  function is strictly proportional to turnover, not to size² or
  depth-adjusted. Any production deployment would replace this with a
  depth-aware cost model; the integrated module exposes `cost_bps`
  explicitly so that swap-in is a one-line change.
- `0-LAG DIAGNOSTIC ONLY` mode is not used in the demo artifacts.
  If ever reported, it must be labelled exactly that phrase (§10.latency).
