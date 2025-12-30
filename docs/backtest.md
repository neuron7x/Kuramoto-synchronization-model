# Backtesting

TradePulse ships with a deterministic, vectorised walk-forward engine designed
for rapid iteration over strategy parameter sets. This guide explains the data
contract, scoring outputs, and extension hooks for more advanced simulations. Evidence: [@LopezDePrado2018AFML]

---

## Walk-Forward Engine

`backtest.engine.walk_forward(prices, signal_fn, fee=0.0005, initial_capital=0.0, market=None, cost_model=None)`
performs a rolling evaluation of a strategy by:

1. Validating that `prices` is a 1-D array with at least two observations.
2. Requesting a synchronised signal array from `signal_fn(prices)` and clipping
   it to the `[-1, 1]` range to enforce long/short bounds.
3. Calculating P&L from position changes and price moves while deducting
   configurable commissions, spreads, and slippage.
4. Returning a `Result` dataclass with total P&L, maximum drawdown, and the
   number of trades executed. 【F:backtest/engine.py†L1-L32】

```python
from backtest.engine import walk_forward
import numpy as np

def momentum_signal(prices: np.ndarray) -> np.ndarray:
    returns = np.diff(prices, prepend=prices[0])
    signal = np.sign(returns)
    return signal

prices = np.linspace(100, 110, 500) + np.random.randn(500)
result = walk_forward(
    prices,
    momentum_signal,
    fee=0.0002,
    initial_capital=10_000,
    market="BTC-USD",
)
print(result.pnl, result.max_dd, result.trades)
```

---

## Data Requirements

- **Alignment** – `signal_fn` must return an array with the same length as the
  price series; otherwise a `ValueError` is raised. 【F:backtest/engine.py†L15-L22】
- **Leverage & bounds** – signals outside `[-1, 1]` are clamped automatically.
- **Execution costs** – specify `market` to pull per-instrument settings from
  `configs/markets.yaml`, or pass a custom `cost_model` implementing
  `TransactionCostModel` for bespoke handling. Falling back to the scalar `fee`
  reproduces the legacy proportional cost behaviour.

When you need richer book-keeping (cash balances, borrowing costs, event-driven
fills), wrap the existing engine so legacy tests remain deterministic.

---

## Deterministic Seeds & Replays

Research runs should always record the pseudo-random seed so that fills, signal
generation, and performance reports can be reproduced. The analytics runner
exposes a single helper that synchronises Python's `random`, NumPy, and
`PYTHONHASHSEED` state for you—call it once at process start and persist the
value alongside the experiment metadata. 【F:analytics/runner.py†L52-L69】

```python
from analytics.runner import set_random_seeds

set_random_seeds(20240315)  # repeatable backtests across machines
```

For automated sweeps, capture the accompanying metadata (git SHA, environment
name, seed) via `collect_run_metadata` so any regression can be replayed exactly
with the same configuration snapshot. 【F:analytics/runner.py†L72-L113】

---

## Transaction Costs & Slippage

The execution layer composes granular transaction cost components—commission,
spread, slippage, and financing—before attributing them in the returned
`Result`. Each component ships with reusable policies such as per-unit fees,
basis-point spreads, or square-root market impact curves, allowing you to mix
and match venue-specific behaviour. 【F:backtest/transaction_costs.py†L1-L150】

When `market` is provided, the engine loads YAML-backed presets via
`load_market_costs`, so that the same configuration can be reused across
strategies. Otherwise, pass a bespoke `TransactionCostModel` instance to encode
custom fee schedules (maker/taker, tiered pricing, rebates). 【F:backtest/engine.py†L200-L287】【F:backtest/transaction_costs.py†L152-L239】

---

## Latency, Queueing & Partial Fills

Beyond vectorised backtests, TradePulse offers a deterministic matching engine
that honours latency pipelines, price-time priority, and incremental fills.
Orders experience configurable delays (`signal → order → execution`), are queued
by availability time, and interact with resting liquidity according to their
time-in-force semantics (market, limit, IOC, FOK). 【F:backtest/execution_simulation.py†L1-L190】

You can preload order books with passive depth via `add_passive_liquidity`,
inject market halts, or cap participation during partial outages. Execution
reports accumulate per order so strategies can audit queue position, realised
prices, and slippage attribution for every fill. 【F:backtest/execution_simulation.py†L190-L330】

---

## Market Hours & Holiday Calendars

Backtests automatically respect venue trading sessions through the
`MarketCalendar` abstraction. Calendars can be sourced from
`exchange_calendars` (for exchanges such as XNYS, XNAS, CMES) or created
manually for bespoke venues, and each exposes DST-aware timezone conversion and
holiday/weekend closures. 【F:core/data/timeutils.py†L15-L149】

Use `is_market_open(timestamp, market)` to gate order generation, or
`convert_timestamp` / `to_utc` to align historical bars captured in local time
with UTC analytics. DST transitions and overnight futures sessions are handled
via the underlying exchange metadata, ensuring realistic behaviour across
holiday boundaries. 【F:core/data/timeutils.py†L139-L229】

---

## Diagnostics & Extensions

- Use `Result.commission_cost`, `Result.spread_cost`, and
  `Result.slippage_cost` to reconcile the breakdown of execution frictions.
- Construct reusable commission/spread/slippage policies via
  `backtest.transaction_costs.CompositeTransactionCostModel` and point the
  engine at bespoke YAML configuration files with `cost_config="my_markets.yaml"`.

- Record intermediate arrays (`positions`, `equity_curve`, `drawdowns`) to
  inspect trade-by-trade performance.
- Compose with the agent layer: `Strategy.simulate_performance` in the agent
  module already uses this walk-forward logic to ensure consistent scoring.
- For multi-asset or order-book simulations, fork the engine and maintain the
  same `Result` signature so downstream tooling keeps working.

---

## Execution Simulation

When strategies require microstructure-aware analysis (latency, partial fills,
order queueing, halts, and time-in-force semantics), layer the
[`backtest.execution_simulation`](../backtest/execution_simulation.py) module on
top of the walk-forward loop. The protocol described in
[`docs/backtest_execution_simulation.md`](backtest_execution_simulation.md)
covers latency modelling, halt policies, order types, and integration steps for
deterministic research environments.
