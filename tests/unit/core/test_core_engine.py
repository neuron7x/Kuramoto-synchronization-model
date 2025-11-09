"""Unit tests for the minimal core trading engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from tradepulse.core.engine import (
    CoreEngine,
    CoreEngineConfig,
    EngineContext,
    ExecutionOutcome,
    LogEntry,
    MarketData,
    RiskDecision,
    Signal,
)


class DummyDataFeed:
    """Deterministic data feed used for unit tests."""

    def __init__(self, items: Iterable[MarketData]) -> None:
        self._items = tuple(items)

    def fetch(self, context: EngineContext) -> Iterable[MarketData]:  # noqa: D401 - protocol implementation
        return self._items


class DummySignalGenerator:
    """Signal generator returning pre-baked signals keyed by data source."""

    def __init__(self, mapping: Mapping[str, Iterable[Signal]]) -> None:
        self._mapping = {key: tuple(value) for key, value in mapping.items()}

    def generate(self, data: MarketData, context: EngineContext) -> Iterable[Signal]:  # noqa: D401 - protocol implementation
        return self._mapping.get(data.source, ())


class DummyRiskManager:
    """Risk manager that approves signals based on a provided allow-list."""

    def __init__(self, approvals: Mapping[str, bool]) -> None:
        self._approvals = dict(approvals)

    def assess(self, signal: Signal, context: EngineContext) -> RiskDecision:  # noqa: D401 - protocol implementation
        return RiskDecision(approved=self._approvals.get(signal.name, True))


class DummyExecutionClient:
    """Execution client capturing all routed signals for assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[Signal, RiskDecision]] = []

    def execute(
        self, signal: Signal, decision: RiskDecision, context: EngineContext
    ) -> ExecutionOutcome:  # noqa: D401 - protocol implementation
        self.calls.append((signal, decision))
        return ExecutionOutcome(
            status="sent",
            reference=signal.name,
            details={"approved": decision.approved},
        )


class DummyLogSink:
    """Log sink collecting emitted entries for verification."""

    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def emit(self, entry: LogEntry, context: EngineContext) -> None:  # noqa: D401 - protocol implementation
        self.entries.append(entry)


def _make_market_data(source: str) -> MarketData:
    return MarketData(source=source, payload={"price": 101.0})


def _make_signal(name: str, strength: float = 1.0) -> Signal:
    return Signal(name=name, strength=strength)


def test_engine_cycle_drops_rejected_signals_and_logs_counts() -> None:
    data_feed = DummyDataFeed([_make_market_data("feed-a")])
    signal_generator = DummySignalGenerator(
        {
            "feed-a": (
                _make_signal("alpha", 0.9),
                _make_signal("beta", -0.5),
            )
        }
    )
    risk_manager = DummyRiskManager({"alpha": True, "beta": False})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
    )

    context = EngineContext(run_id="unit-drop")
    cycles = list(engine.run_cycle(context))

    assert len(cycles) == 1
    cycle = cycles[0]
    assert [signal.name for signal in cycle.signals] == ["alpha"]
    assert [decision.approved for decision in cycle.decisions] == [True]
    assert [outcome.reference for outcome in cycle.executions] == ["alpha"]
    assert execution_client.calls == [(cycle.signals[0], cycle.decisions[0])]

    assert len(log_sink.entries) == 1
    log_entry = log_sink.entries[0]
    assert log_entry.context["run_id"] == context.run_id
    assert log_entry.context["data_source"] == "feed-a"
    assert log_entry.context["signals"] == 1  # dispatched after filtering
    assert log_entry.context["received_signals"] == 2
    assert log_entry.context["approved_signals"] == 1
    assert log_entry.context["rejected_signals"] == 1
    assert log_entry.context["executions"] == 1
    assert cycle.logs == tuple(log_sink.entries)


def test_engine_cycle_preserves_rejected_when_configured() -> None:
    data_feed = DummyDataFeed([_make_market_data("feed-b")])
    signal_generator = DummySignalGenerator({"feed-b": (_make_signal("gamma", 0.4),)})
    risk_manager = DummyRiskManager({"gamma": False})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
        config=CoreEngineConfig(drop_rejected_signals=False),
    )

    context = EngineContext(run_id="unit-keep")
    cycles = list(engine.run_cycle(context))

    assert len(cycles) == 1
    cycle = cycles[0]
    assert [signal.name for signal in cycle.signals] == ["gamma"]
    assert [decision.approved for decision in cycle.decisions] == [False]
    assert [outcome.reference for outcome in cycle.executions] == ["gamma"]
    assert execution_client.calls == [(cycle.signals[0], cycle.decisions[0])]

    log_entry = log_sink.entries[0]
    assert log_entry.context["signals"] == 1
    assert log_entry.context["received_signals"] == 1
    assert log_entry.context["approved_signals"] == 0
    assert log_entry.context["rejected_signals"] == 1
    assert log_entry.context["executions"] == 1


def test_engine_cycle_logs_when_all_signals_rejected() -> None:
    data_feed = DummyDataFeed([_make_market_data("feed-c")])
    signal_generator = DummySignalGenerator({"feed-c": (_make_signal("delta", -0.2),)})
    risk_manager = DummyRiskManager({"delta": False})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
    )

    context = EngineContext(run_id="unit-all-rejected")
    cycles = list(engine.run_cycle(context))

    assert len(cycles) == 1
    cycle = cycles[0]
    assert list(cycle.signals) == []
    assert list(cycle.decisions) == []
    assert list(cycle.executions) == []

    log_entry = log_sink.entries[0]
    assert log_entry.context["signals"] == 0
    assert log_entry.context["received_signals"] == 1
    assert log_entry.context["approved_signals"] == 0
    assert log_entry.context["rejected_signals"] == 1
    assert log_entry.context["executions"] == 0
