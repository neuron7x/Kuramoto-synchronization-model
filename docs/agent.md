# Agent System

GeoSync agents coordinate strategy discovery, evaluation, and deployment.
The system couples deterministic backtests with bandit-driven exploration so
only robust parameter sets survive. This document outlines the lifecycle
contracts, key classes, and extension points.

---

## Components at a Glance

| Component | Responsibility | Implementation |
| --------- | -------------- | --------------- |
| `Strategy` | Holds hyperparameters, enforces bounds, and scores itself against historical data. | [`core/agent/strategy.py`](../core/agent/strategy.py) |
| `PiAgent` | Wraps a strategy with instability detection, mutation/repair hooks, and action decisions. | [`core/agent/strategy.py`](../core/agent/strategy.py) |
| `StrategyMemory` | Stores top-performing strategies keyed by market signature with exponential decay. | [`core/agent/memory.py`](../core/agent/memory.py) |
| Bandits (`EpsilonGreedy`, `UCB1`) | Choose which strategy to evaluate next based on reward signals. | [`core/agent/bandits.py`](../core/agent/bandits.py) |

---

## Strategy Lifecycle

1. **Parameter validation** – `Strategy.validate_params()` clamps lookback,
   threshold, and risk budget into safe ranges before any scoring occurs.
2. **Performance simulation** – `Strategy.simulate_performance()` ingests raw
   prices (array, `Series`, or `DataFrame`), sanitises them, then runs a
   deterministic mean-reversion backtest that produces Sharpe- and P&L-weighted
   scores plus diagnostics (`max_drawdown`, `trades`, equity curve). 【F:core/agent/strategy.py†L12-L92】
3. **Mutation** – `Strategy.generate_mutation()` perturbs numeric parameters,
   reuses validation, and returns a ready-to-evaluate clone so exploration stays
   bounded. 【F:core/agent/strategy.py†L18-L39】
4. **Persistence** – After evaluation, store outcomes in `StrategyMemory.add()`
   keyed by a rounded `StrategySignature`; newer, higher-scoring entries replace
   stale ones while the decay factor continuously discounts old results. 【F:core/agent/memory.py†L6-L67】

### Example

```python
from core.agent.strategy import Strategy
from core.agent.memory import StrategyMemory, StrategySignature

prices = ...  # 1D numpy array or pandas Series
strategy = Strategy(name="mean_revert", params={"lookback": 60, "threshold": 0.8})
score = strategy.simulate_performance(prices)

memory = StrategyMemory(decay_lambda=5e-6, max_records=128)
signature = StrategySignature(R=0.72, delta_H=-0.03, kappa_mean=-0.15, entropy=2.1, instability=0.18)
memory.add(strategy.name, signature, score)
```

---

## Instability Detection & Actions

`PiAgent` tracks short-term volatility regimes to decide when a strategy should
enter, hold, or exit. It maintains an exponentially smoothed instability score
and a cooldown timer so spurious blips do not trigger constant churn. 【F:core/agent/strategy.py†L94-L145】

Key signals expected in `market_state`:

- `R` – Kuramoto order (synchrony) 【F:core/agent/strategy.py†L101-L113】
- `delta_H` – change in entropy
- `kappa_mean` – Ricci curvature of price graph
- `transition_score` – probability of phase transition
- Optional boolean `phase_reversal` to trigger exits when hysteresis allows

Actions returned by `PiAgent.evaluate_and_adapt(market_state)`:

- `"enter"` – open or add exposure when instability crosses the threshold
- `"exit"` – flatten positions when reversal detected and smoothed risk is low
- `"hold"` – maintain current stance

`PiAgent.repair()` cleans NaNs injected by upstream processes and re-validates
parameters before the next evaluation cycle. 【F:core/agent/strategy.py†L127-L145】

---

## Exploration Policies

GeoSync provides two lightweight bandits for selecting which strategy to test:

- **`EpsilonGreedy`** – random exploration with probability `ε`, otherwise
  exploit the best average reward so far. 【F:core/agent/bandits.py†L1-L19】
- **`UCB1`** – upper-confidence bound algorithm balancing average reward and
  uncertainty via logarithmic bonuses. 【F:core/agent/bandits.py†L21-L35】

Usage sketch:

```python
from core.agent.bandits import EpsilonGreedy

bandit = EpsilonGreedy(["mean_revert", "breakout"], epsilon=0.15)
arm = bandit.select()
# evaluate strategy `arm` here and compute reward
bandit.update(arm, reward=0.42)
```

---

## Strategy Scheduler

For automated experimentation GeoSync ships a deterministic scheduler that
periodically evaluates strategy bundles. The scheduler deduplicates runtime
state, applies jitter to avoid thundering herds, and backs off exponentially
when data sources fail. 【F:core/agent/scheduler.py†L40-L216】【F:core/agent/scheduler.py†L327-L343】

```python
from core.agent.scheduler import StrategyJob, StrategyScheduler
from core.agent.strategy import Strategy

scheduler = StrategyScheduler()

job = StrategyJob(
    name="nightly",
    strategies=[Strategy(name="mean_revert", params={"lookback": 60})],
    data_provider=lambda: load_market_snapshot(),
    interval=3600.0,  # seconds
    jitter=120.0,
)

scheduler.add_job(job)
scheduler.start()
```

Use `StrategyScheduler.run_pending()` in batch workflows to trigger due jobs
explicitly, or `StrategyScheduler.start()` to keep evaluations running in a
background thread. Introspection helpers expose per-job status, last error, and
evaluation results so operators can build monitoring dashboards or trigger
alerts. 【F:core/agent/scheduler.py†L200-L370】

---

## Strategy Orchestrator

When strategies must be evaluated in parallel without blocking the main control
thread, use :class:`StrategyOrchestrator`. The orchestrator coordinates multiple
`StrategyFlow` definitions via a bounded worker pool, ensuring each flow runs in
its own worker and preventing duplicate submissions from clobbering shared
state. Results for each flow are aggregated, and any failures raise
`StrategyOrchestrationError` containing both the exceptions and the successful
partial results for post-mortem inspection. 【F:core/agent/orchestrator.py†L1-L165】

---

## Best Practices

- Keep market feature engineering consistent with `StrategySignature` to ensure
  memory lookups deduplicate comparable environments.
- Log diagnostics stored on `Strategy.params` (`last_equity_curve`,
  `max_drawdown`, `trades`) for post-mortem analysis.
- When introducing new agent behaviours (e.g., reinforcement learning), extend
  this document and link to the relevant modules so the portal stays aligned
  with code.
