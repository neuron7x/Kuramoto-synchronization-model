# Core Engine v1

The **Core Engine v1** package delivers the minimum executable pipeline required
for GeoSync deployments. It is intentionally small, dependency-light, and
focused on five sequential responsibilities:

1. **Data** – pull normalized `MarketData` instances from an upstream `DataFeed`.
2. **Signal** – transform market inputs into actionable `Signal` objects via a
   `SignalGenerator` implementation.
3. **Risk** – assess each signal using a `RiskManager`, producing
   `RiskDecision` artefacts that capture approval state and adjustments.
4. **Execute** – route approved signals to an `ExecutionClient`, returning an
   `ExecutionOutcome` for downstream reconciliation.
5. **Log** – emit structured `LogEntry` objects to a pluggable `LogSink` for
   observability and traceability.

## Public API

All interfaces are exposed from `core.engine`:

```python
from core.engine import (
    CoreEngine,
    CoreEngineConfig,
    CoreEngineError,
    CycleMetrics,
    DataFeed,
    EngineContext,
    EngineCycle,
    ExecutionClient,
    ExecutionOutcome,
    LogEntry,
    LogSink,
    MarketData,
    RiskDecision,
    RiskManager,
    StageDurations,
    Signal,
    SignalGenerator,
)
```

### Engine lifecycle

A `CoreEngine` instance orchestrates a single pipeline pass through the
`run_cycle` iterator. Each iteration yields an `EngineCycle` object containing
inputs, intermediate artefacts, and outputs for a given unit of market data. The
engine enforces the following contract:

- Data feeds **must** produce `MarketData` items that are already normalized; the
  engine does not apply schema transformations.
- Signal generators **may** emit zero, one, or many `Signal` objects per market
  datum.
- Risk managers **must** return a `RiskDecision` for every provided signal.
- Execution clients **should** treat signals and risk decisions as immutable
  inputs and return an `ExecutionOutcome` describing the interaction with
  downstream systems.
- Log sinks **must** persist or forward the structured `LogEntry` instances they
  receive.

### Cycle metrics and observability

`EngineCycle.metrics` exposes a `CycleMetrics` instance with timing and
throughput counters for the processed datum. Each metrics object captures the
sequential position of the cycle, per-stage latency breakdowns via
`StageDurations`, and the number of emitted log entries in addition to the
aggregate counts for received, approved, rejected, and dispatched signals as
well as execution attempts. These values are mirrored in the structured log
emitted at the end of each cycle, enabling downstream monitoring pipelines to
reason about performance trends without reprocessing the artefacts themselves.

### Configuration

`CoreEngineConfig` exposes two primary toggles:

| Option | Default | Description |
| --- | --- | --- |
| `drop_rejected_signals` | `True` | Filter out signals where `RiskDecision.approved` is `False` before execution. |
| `stop_on_error` | `False` | Raise `CoreEngineError` when any cycle fails; otherwise emit an error log and continue. |

### Example usage

```python
from core.engine import CoreEngine, CoreEngineConfig, EngineContext

engine = CoreEngine(
    data_feed=my_data_feed,
    signal_generator=my_signal_generator,
    risk_manager=my_risk_manager,
    execution_client=my_execution_client,
    log_sink=my_log_sink,
    config=CoreEngineConfig(drop_rejected_signals=True),
)

context = EngineContext(run_id="2024-04-18-eu-session")
for cycle in engine.run_cycle(context):
    for execution in cycle.executions:
        reconcile(execution)
```

The package does not prescribe concrete implementations for the interfaces,
allowing teams to plug in existing data pipelines, analytics stacks, risk
systems, and execution adapters without reworking their current code.
