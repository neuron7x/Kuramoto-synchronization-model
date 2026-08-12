# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the minimal core trading engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pytest

from core.engine import (
    CoreEngine,
    CoreEngineConfig,
    CoreEngineError,
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

    def fetch(
        self, context: EngineContext
    ) -> Iterable[MarketData]:  # noqa: D401 - protocol implementation
        return self._items


class DummySignalGenerator:
    """Signal generator returning pre-baked signals keyed by data source."""

    def __init__(self, mapping: Mapping[str, Iterable[Signal]]) -> None:
        self._mapping = {key: tuple(value) for key, value in mapping.items()}

    def generate(
        self, data: MarketData, context: EngineContext
    ) -> Iterable[Signal]:  # noqa: D401 - protocol implementation
        return self._mapping.get(data.source, ())


class DummyRiskManager:
    """Risk manager that approves signals based on a provided allow-list."""

    def __init__(self, approvals: Mapping[str, bool]) -> None:
        self._approvals = dict(approvals)

    def assess(
        self, signal: Signal, context: EngineContext
    ) -> RiskDecision:  # noqa: D401 - protocol implementation
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

    def emit(
        self, entry: LogEntry, context: EngineContext
    ) -> None:  # noqa: D401 - protocol implementation
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
    assert cycle.sequence_number == 1
    assert [signal.name for signal in cycle.signals] == ["alpha"]
    assert [decision.approved for decision in cycle.decisions] == [True]
    assert [outcome.reference for outcome in cycle.executions] == ["alpha"]
    assert execution_client.calls == [(cycle.signals[0], cycle.decisions[0])]

    metrics = cycle.metrics
    assert metrics.sequence_number == cycle.sequence_number
    assert metrics.received_signals == 2
    assert metrics.approved_signals == 1
    assert metrics.rejected_signals == 1
    assert metrics.dispatched_signals == 1
    assert metrics.execution_attempts == 1
    assert metrics.started_at <= metrics.completed_at
    assert metrics.duration_ms >= 0.0
    assert metrics.log_entries == 1

    stage_durations = metrics.stage_durations
    assert stage_durations.signal_ms >= 0.0
    assert stage_durations.risk_ms >= 0.0
    assert stage_durations.execution_ms >= 0.0

    assert len(log_sink.entries) == 1
    log_entry = log_sink.entries[0]
    assert log_entry.context["run_id"] == context.run_id
    assert log_entry.context["data_source"] == "feed-a"
    assert log_entry.context["sequence_number"] == cycle.sequence_number
    assert log_entry.context["signals"] == 1  # dispatched after filtering
    assert log_entry.context["decisions"] == 1
    assert log_entry.context["received_signals"] == 2
    assert log_entry.context["approved_signals"] == 1
    assert log_entry.context["rejected_signals"] == 1
    assert log_entry.context["dispatched_signals"] == 1
    assert log_entry.context["execution_attempts"] == 1
    assert log_entry.context["executions"] == 1
    assert log_entry.context["stage_signal_ms"] >= 0.0
    assert log_entry.context["stage_risk_ms"] >= 0.0
    assert log_entry.context["stage_execution_ms"] >= 0.0
    assert "cycle_started_at" in log_entry.context
    assert "cycle_completed_at" in log_entry.context
    assert "cycle_duration_ms" in log_entry.context
    assert log_entry.context["log_entries"] == len(log_sink.entries)
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
    assert cycle.sequence_number == 1
    assert [signal.name for signal in cycle.signals] == ["gamma"]
    assert [decision.approved for decision in cycle.decisions] == [False]
    assert [outcome.reference for outcome in cycle.executions] == ["gamma"]
    assert execution_client.calls == [(cycle.signals[0], cycle.decisions[0])]

    metrics = cycle.metrics
    assert metrics.sequence_number == cycle.sequence_number
    assert metrics.received_signals == 1
    assert metrics.approved_signals == 0
    assert metrics.rejected_signals == 1
    assert metrics.dispatched_signals == 1
    assert metrics.execution_attempts == 1
    assert metrics.duration_ms >= 0.0
    assert metrics.log_entries == 1
    assert metrics.stage_durations.signal_ms >= 0.0
    assert metrics.stage_durations.risk_ms >= 0.0
    assert metrics.stage_durations.execution_ms >= 0.0

    log_entry = log_sink.entries[0]
    assert log_entry.context["sequence_number"] == cycle.sequence_number
    assert log_entry.context["signals"] == 1
    assert log_entry.context["decisions"] == 1
    assert log_entry.context["received_signals"] == 1
    assert log_entry.context["approved_signals"] == 0
    assert log_entry.context["rejected_signals"] == 1
    assert log_entry.context["dispatched_signals"] == 1
    assert log_entry.context["execution_attempts"] == 1
    assert log_entry.context["executions"] == 1
    assert "cycle_duration_ms" in log_entry.context
    assert log_entry.context["log_entries"] == len(log_sink.entries)


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
    assert cycle.sequence_number == 1
    assert list(cycle.signals) == []
    assert list(cycle.decisions) == []
    assert list(cycle.executions) == []

    metrics = cycle.metrics
    assert metrics.sequence_number == cycle.sequence_number
    assert metrics.received_signals == 1
    assert metrics.approved_signals == 0
    assert metrics.rejected_signals == 1
    assert metrics.dispatched_signals == 0
    assert metrics.execution_attempts == 0
    assert metrics.duration_ms >= 0.0
    assert metrics.log_entries == 1
    assert metrics.stage_durations.signal_ms >= 0.0
    assert metrics.stage_durations.risk_ms >= 0.0
    assert metrics.stage_durations.execution_ms >= 0.0

    log_entry = log_sink.entries[0]
    assert log_entry.context["sequence_number"] == cycle.sequence_number
    assert log_entry.context["signals"] == 0
    assert log_entry.context["decisions"] == 0
    assert log_entry.context["received_signals"] == 1
    assert log_entry.context["approved_signals"] == 0
    assert log_entry.context["rejected_signals"] == 1
    assert log_entry.context["dispatched_signals"] == 0
    assert log_entry.context["execution_attempts"] == 0
    assert log_entry.context["executions"] == 0
    assert "cycle_duration_ms" in log_entry.context
    assert log_entry.context["log_entries"] == len(log_sink.entries)


def test_engine_cycle_sequence_numbers_increment_per_datum() -> None:
    data_feed = DummyDataFeed([_make_market_data("feed-seq-1"), _make_market_data("feed-seq-2")])
    signal_generator = DummySignalGenerator(
        {
            "feed-seq-1": (_make_signal("sig-1"),),
            "feed-seq-2": (_make_signal("sig-2"),),
        }
    )
    risk_manager = DummyRiskManager({"sig-1": True, "sig-2": True})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
    )

    cycles = list(engine.run_cycle(EngineContext(run_id="sequence-test")))

    assert [cycle.sequence_number for cycle in cycles] == [1, 2]
    assert [cycle.metrics.sequence_number for cycle in cycles] == [1, 2]
    assert all(cycle.metrics.log_entries == 1 for cycle in cycles)
    assert [entry.context["sequence_number"] for entry in log_sink.entries] == [1, 2]
    assert [entry.context["log_entries"] for entry in log_sink.entries] == [1, 1]


def test_engine_rejects_invalid_market_data_when_configured_to_stop() -> None:
    class BadDataFeed:
        def fetch(self, context: EngineContext) -> Iterable[MarketData]:
            return [object()]  # type: ignore[list-item]

    signal_generator = DummySignalGenerator({})
    risk_manager = DummyRiskManager({})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=BadDataFeed(),
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
        config=CoreEngineConfig(stop_on_error=True),
    )

    context = EngineContext(run_id="invalid-data")
    with pytest.raises(CoreEngineError) as excinfo:
        list(engine.run_cycle(context))

    assert isinstance(excinfo.value.__cause__, TypeError)
    assert "DataFeed.fetch" in str(excinfo.value.__cause__)


def test_engine_rejects_invalid_signal_output_when_configured_to_stop() -> None:
    class BadSignalGenerator:
        def generate(
            self, data: MarketData, context: EngineContext
        ) -> Iterable[Signal]:  # noqa: D401 - protocol implementation
            return [object()]  # type: ignore[list-item]

    data_feed = DummyDataFeed([_make_market_data("feed-x")])
    risk_manager = DummyRiskManager({})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=BadSignalGenerator(),
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
        config=CoreEngineConfig(stop_on_error=True),
    )

    context = EngineContext(run_id="invalid-signal")
    with pytest.raises(CoreEngineError) as excinfo:
        list(engine.run_cycle(context))

    assert isinstance(excinfo.value.__cause__, TypeError)
    assert "SignalGenerator.generate" in str(excinfo.value.__cause__)


def test_engine_rejects_invalid_risk_decision_when_configured_to_stop() -> None:
    class BadRiskManager:
        def assess(self, signal: Signal, context: EngineContext) -> RiskDecision:
            return "not-a-decision"  # type: ignore[return-value]

    data_feed = DummyDataFeed([_make_market_data("feed-y")])
    signal_generator = DummySignalGenerator({"feed-y": (_make_signal("alpha", 0.5),)})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=signal_generator,
        risk_manager=BadRiskManager(),
        execution_client=execution_client,
        log_sink=log_sink,
        config=CoreEngineConfig(stop_on_error=True),
    )

    context = EngineContext(run_id="invalid-risk")
    with pytest.raises(CoreEngineError) as excinfo:
        list(engine.run_cycle(context))

    assert isinstance(excinfo.value.__cause__, TypeError)
    assert "RiskManager.assess" in str(excinfo.value.__cause__)


def test_engine_rejects_invalid_execution_outcome_when_configured_to_stop() -> None:
    class BadExecutionClient:
        def __init__(self) -> None:
            self.calls: list[tuple[Signal, RiskDecision]] = []

        def execute(
            self, signal: Signal, decision: RiskDecision, context: EngineContext
        ) -> ExecutionOutcome:
            self.calls.append((signal, decision))
            return "not-an-outcome"  # type: ignore[return-value]

    data_feed = DummyDataFeed([_make_market_data("feed-z")])
    signal_generator = DummySignalGenerator({"feed-z": (_make_signal("theta", 0.7),)})
    risk_manager = DummyRiskManager({"theta": True})
    execution_client = BadExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=signal_generator,
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
        config=CoreEngineConfig(stop_on_error=True),
    )

    context = EngineContext(run_id="invalid-execution")
    with pytest.raises(CoreEngineError) as excinfo:
        list(engine.run_cycle(context))

    assert isinstance(excinfo.value.__cause__, TypeError)
    assert "ExecutionClient.execute" in str(excinfo.value.__cause__)


def test_engine_logs_error_when_continue_on_failure() -> None:
    class BadSignalGenerator:
        def generate(
            self, data: MarketData, context: EngineContext
        ) -> Iterable[Signal]:  # noqa: D401 - protocol implementation
            return [object()]  # type: ignore[list-item]

    data_feed = DummyDataFeed([_make_market_data("feed-error")])
    risk_manager = DummyRiskManager({})
    execution_client = DummyExecutionClient()
    log_sink = DummyLogSink()

    engine = CoreEngine(
        data_feed=data_feed,
        signal_generator=BadSignalGenerator(),
        risk_manager=risk_manager,
        execution_client=execution_client,
        log_sink=log_sink,
        config=CoreEngineConfig(stop_on_error=False),
    )

    context = EngineContext(run_id="continue-on-error")
    cycles = list(engine.run_cycle(context))

    assert cycles == []
    assert log_sink.entries[-1].level == "ERROR"
    assert log_sink.entries[-1].message == "Core engine cycle failed"
    assert log_sink.entries[-1].context["run_id"] == context.run_id
    assert "SignalGenerator.generate" in log_sink.entries[-1].context["error"]
