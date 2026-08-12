# Backtest Execution Simulation Protocol

This protocol standardises how GeoSync models exchange microstructure within
its backtesting environment. It complements the deterministic walk-forward
engine by introducing order-driven mechanics—latency, queueing, partial fills,
market halts, and multiple time-in-force policies—so strategies can be assessed
under more realistic execution assumptions.

---

## Functional Requirements

| Capability | Expectations | Notes |
| ---------- | ------------ | ----- |
| **Latency / Delay** | Every order experiences deterministic or stochastic latency before it reaches the book. | Implement via a pluggable `latency_model(order) -> ms` callable. |
| **Partial Fills** | Orders may match against fragmented liquidity and report incremental executions. | Maintain execution logs and running fill state per order. |
| **Order Queue** | Competing orders respect venue matching rules (FIFO or extensions). | Orders are queued by `ready_at` timestamp and processed deterministically. |
| **Market Halts** | Exchanges can reject, defer, partially service, or fully freeze order flow. | Encode via a `halt_model(symbol, timestamp)` callback returning `MarketHalt`. |
| **Order Types** | Support `limit`, `market`, `IOC`, and `FOK` semantics. | Time-in-force policies determine whether residual quantity rests, cancels, or invalidates fills. |

---

## Architecture Overview

The implementation lives in [`backtest/execution_simulation.py`](../backtest/execution_simulation.py)
and exposes primitives that mirror exchange behaviour while
remaining deterministic for unit tests.

### Order Representation

```python
from backtest.execution_simulation import Order, OrderSide, OrderType

order = Order(
    id="order-123",
    symbol="ETH-USD",
    side=OrderSide.BUY,
    qty=2.5,
    timestamp=1_698_000_000,
    order_type=OrderType.LIMIT,
    price=1_850.0,
)
```

Each order tracks status transitions (`NEW`, `QUEUED`, `PARTIALLY_FILLED`,
`FILLED`, `CANCELLED`, `REJECTED`), accumulated fills, and execution reports.

### Matching Engine

```python
from backtest.execution_simulation import MatchingEngine, MarketHalt, HaltMode

engine = MatchingEngine(
    latency_model=lambda order: 75,  # milliseconds
    halt_model=lambda symbol, ts: MarketHalt(mode=HaltMode.OPEN),
)
```

1. **Latency modelling** – `submit_order` computes `ready_at = timestamp +
   latency` so the engine can respect exchange/network delays.
2. **Order queue** – pending orders live in a min-heap keyed by `ready_at`.
   Calling `process_until(sim_time)` flushes every order whose latency has
   elapsed, ensuring FIFO ordering for simultaneous arrivals.
3. **Matching** – `_match` consumes contra-side book entries while enforcing
   price-time priority, partial fill caps, and halt behaviour. Residual quantities
   rest on the book for standard limit orders.

### Market Halts

`MarketHalt` encapsulates venue state:

- `HaltMode.REJECT_NEW` – incoming orders are immediately rejected.
- `HaltMode.DELAY` / `HaltMode.FULL` – orders are queued until `resume_time` (or
  cancelled when the halt has no scheduled resume).
- `HaltMode.PARTIAL` – fills proceed but are capped via
  `liquidity_factor` (e.g., `0.25` allows only 25% of the desired quantity).

### Order Types & Time-in-Force

- **Market** – matches immediately; unfilled residual cancels.
- **Limit** – matches up to the limit price; remainder rests on the book.
- **IOC** – matches available liquidity instantly; residual cancels.
- **FOK** – validates available liquidity upfront; any shortfall cancels the
  order and clears tentative executions.

---

## Integration Steps

1. **Inject market structure data** – pre-seed the book with historical depth via
   `add_passive_liquidity` or dedicated loaders before replaying strategy
   signals.
2. **Schedule processing** – drive `process_until(current_time)` from the
   backtest clock so latency windows, halts, and queue semantics align with
   market timestamps.
3. **Log execution reports** – persist `order.executions` and status changes to
   analyse slippage, hit ratios, and queue position.
4. **Configuration hooks** – bundle latency distributions, halt calendars, and
   liquidity models into strategy configs so experiments remain reproducible.

---

## Testing & Quality Gates

Unit tests in [`tests/unit/backtest/test_execution_simulation.py`](../tests/unit/backtest/test_execution_simulation.py)
exercise latency handling, queue ordering, halt resumption, and FOK semantics.
Add regression scenarios for venue-specific quirks (pro-rata allocation, maker
rebates) as extensions are implemented.

For end-to-end validations:

- Replay historical order books and verify aggregate execution metrics match
  production logs within tolerance.
- Stress-test stochastic latency models to ensure deterministic seeding produces
  reproducible results.
- Integrate with observability tooling to surface queue depth, halt durations,
  and partial-fill rates during research runs.

---

## Extensibility Roadmap

- Support additional time-in-force instructions (GTD/GTC) by extending the
  `OrderType` enum.
- Introduce configurable queue policies (FIFO vs. pro-rata) by swapping the
  matching routine.
- Allow venue-specific halt behaviours (e.g., auction uncrossing) through richer
  `MarketHalt` metadata.
- Add slippage and transaction cost adapters that consume execution reports and
  feed existing P&L attribution pipelines.
