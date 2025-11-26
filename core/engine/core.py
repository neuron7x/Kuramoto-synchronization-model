"""Minimal executable core trading engine (Core Engine v1)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol, TypeVar, runtime_checkable

_T = TypeVar("_T")


@dataclass(slots=True)
class EngineContext:
    """Represents the execution context for a single engine cycle."""

    run_id: str
    as_of: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MarketData:
    """Normalized representation of upstream market or reference data."""

    source: str
    payload: Mapping[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class Signal:
    """Actionable analytics derived from :class:`MarketData`."""

    name: str
    strength: float
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RiskDecision:
    """Outcome of the risk management step for a specific :class:`Signal`."""

    approved: bool
    reason: str | None = None
    adjustments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionOutcome:
    """Result of order placement, allocation, or other execution activity."""

    status: str
    reference: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LogEntry:
    """Structured log payload emitted by the engine."""

    level: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class CoreEngineConfig:
    """Configuration toggles for :class:`CoreEngine`."""

    drop_rejected_signals: bool = True
    stop_on_error: bool = False


class CoreEngineError(RuntimeError):
    """Raised when the engine cannot complete a processing cycle."""


@runtime_checkable
class DataFeed(Protocol):
    """Supplies normalized market data to the engine."""

    def fetch(self, context: EngineContext) -> Iterable[MarketData] | MarketData:
        """Return the next batch (or single instance) of :class:`MarketData`."""


@runtime_checkable
class SignalGenerator(Protocol):
    """Transforms :class:`MarketData` into actionable :class:`Signal` objects."""

    def generate(
        self, data: MarketData, context: EngineContext
    ) -> Iterable[Signal] | Signal | None:
        """Produce zero or more signals for the supplied market data."""


@runtime_checkable
class RiskManager(Protocol):
    """Evaluates whether a :class:`Signal` can proceed to execution."""

    def assess(self, signal: Signal, context: EngineContext) -> RiskDecision:
        """Return the risk decision for the provided signal."""


@runtime_checkable
class ExecutionClient(Protocol):
    """Handles interaction with trading venues, brokers, or downstream systems."""

    def execute(
        self, signal: Signal, decision: RiskDecision, context: EngineContext
    ) -> ExecutionOutcome:
        """Execute the signal in accordance with the supplied risk decision."""


@runtime_checkable
class LogSink(Protocol):
    """Receives structured log entries emitted by the engine."""

    def emit(self, entry: LogEntry, context: EngineContext) -> None:
        """Persist or forward the given log entry."""


@dataclass(slots=True, frozen=True)
class StageDurations:
    """Latency measurements for each pipeline stage within a cycle."""

    signal_ms: float
    risk_ms: float
    execution_ms: float


@dataclass(slots=True, frozen=True)
class CycleMetrics:
    """Operational statistics captured for a single engine cycle."""

    sequence_number: int
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    stage_durations: StageDurations
    received_signals: int
    approved_signals: int
    rejected_signals: int
    dispatched_signals: int
    execution_attempts: int
    log_entries: int


@dataclass(slots=True)
class EngineCycle:
    """Encapsulates the artefacts produced by a single engine step."""

    sequence_number: int
    market_data: MarketData
    signals: tuple[Signal, ...]
    decisions: tuple[RiskDecision, ...]
    executions: tuple[ExecutionOutcome, ...]
    logs: tuple[LogEntry, ...]
    metrics: CycleMetrics


class CoreEngine:
    """Minimal executable pipeline that powers Core Engine v1."""

    def __init__(
        self,
        *,
        data_feed: DataFeed,
        signal_generator: SignalGenerator,
        risk_manager: RiskManager,
        execution_client: ExecutionClient,
        log_sink: LogSink,
        config: CoreEngineConfig | None = None,
    ) -> None:
        self._data_feed = data_feed
        self._signal_generator = signal_generator
        self._risk_manager = risk_manager
        self._execution_client = execution_client
        self._log_sink = log_sink
        self._config = config or CoreEngineConfig()

    @property
    def config(self) -> CoreEngineConfig:
        """Return the current engine configuration."""

        return self._config

    def run_cycle(self, context: EngineContext) -> Iterator[EngineCycle]:
        """Execute the data→signal→risk→execute→log pipeline.

        The engine iterates over the data feed and yields :class:`EngineCycle`
        artefacts for each processed datum. Each cycle is isolated, ensuring
        that downstream systems can consume partial results without waiting for
        the entire batch to complete.
        """

        try:
            cycle_index = 0
            for market_data in self._yield_data(context):
                cycle_index += 1
                cycle_started_at = datetime.now(timezone.utc)
                stopwatch = perf_counter()

                signal_timer = perf_counter()
                generated_signals = self._collect_and_validate(
                    "SignalGenerator.generate",
                    self._yield_signals(market_data, context),
                    Signal,
                )
                signal_latency_ms = (perf_counter() - signal_timer) * 1000.0
                received_count = len(generated_signals)

                risk_timer = perf_counter()
                decisions = self._collect_and_validate(
                    "RiskManager.assess",
                    (
                        self._risk_manager.assess(signal, context)
                        for signal in generated_signals
                    ),
                    RiskDecision,
                )
                risk_latency_ms = (perf_counter() - risk_timer) * 1000.0
                approved_count = sum(1 for decision in decisions if decision.approved)
                rejected_count = received_count - approved_count

                signal_decision_pairs = tuple(
                    zip(generated_signals, decisions, strict=True)
                )
                if self._config.drop_rejected_signals:
                    filtered_pairs = tuple(
                        (signal, decision)
                        for signal, decision in signal_decision_pairs
                        if decision.approved
                    )
                else:
                    filtered_pairs = signal_decision_pairs

                dispatched_signals = tuple(signal for signal, _ in filtered_pairs)
                dispatched_decisions = tuple(decision for _, decision in filtered_pairs)

                execution_timer = perf_counter()
                executions = self._collect_and_validate(
                    "ExecutionClient.execute",
                    (
                        self._execution_client.execute(signal, decision, context)
                        for signal, decision in filtered_pairs
                    ),
                    ExecutionOutcome,
                )
                execution_latency_ms = (perf_counter() - execution_timer) * 1000.0

                completed_at = datetime.now(timezone.utc)
                metrics = CycleMetrics(
                    sequence_number=cycle_index,
                    started_at=cycle_started_at,
                    completed_at=completed_at,
                    duration_ms=(perf_counter() - stopwatch) * 1000.0,
                    stage_durations=StageDurations(
                        signal_ms=signal_latency_ms,
                        risk_ms=risk_latency_ms,
                        execution_ms=execution_latency_ms,
                    ),
                    received_signals=received_count,
                    approved_signals=approved_count,
                    rejected_signals=rejected_count,
                    dispatched_signals=len(dispatched_signals),
                    execution_attempts=len(executions),
                    log_entries=0,
                )

                logs = self._emit_logs(
                    dispatched_signals,
                    dispatched_decisions,
                    executions,
                    context,
                    market_data,
                    metrics=metrics,
                )

                metrics = replace(metrics, log_entries=len(logs))
                if metrics.log_entries:
                    for entry in logs:
                        if isinstance(entry.context, dict):
                            entry.context.setdefault("log_entries", metrics.log_entries)
                        else:  # pragma: no cover - defensive path for Mapping implementations
                            mutable_context = dict(entry.context)
                            mutable_context.setdefault(
                                "log_entries", metrics.log_entries
                            )
                            entry.context = mutable_context

                yield EngineCycle(
                    sequence_number=metrics.sequence_number,
                    market_data=market_data,
                    signals=dispatched_signals,
                    decisions=dispatched_decisions,
                    executions=executions,
                    logs=logs,
                    metrics=metrics,
                )
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._config.stop_on_error:
                raise CoreEngineError("Core engine cycle failed") from exc
            self._log_sink.emit(
                LogEntry(
                    level="ERROR",
                    message="Core engine cycle failed",
                    context={"run_id": context.run_id, "error": str(exc)},
                ),
                context,
            )

    def _yield_data(self, context: EngineContext) -> Iterator[MarketData]:
        raw = self._data_feed.fetch(context)
        if isinstance(raw, MarketData):
            yield raw
            return
        if not isinstance(raw, Iterable):
            raise TypeError(
                "DataFeed.fetch must return MarketData or an iterable of MarketData",
            )
        for index, item in enumerate(raw):
            if not isinstance(item, MarketData):
                raise TypeError(
                    "DataFeed.fetch yielded unsupported payload at index "
                    f"{index}: {type(item).__name__}",
                )
            yield item

    def _yield_signals(
        self, data: MarketData, context: EngineContext
    ) -> Iterator[Signal]:
        generated = self._signal_generator.generate(data, context)
        if generated is None:
            return
        if isinstance(generated, Signal):
            yield generated
            return
        if not isinstance(generated, Iterable):
            raise TypeError(
                "SignalGenerator.generate must return None, a Signal, or an iterable of Signal",
            )
        for index, signal in enumerate(generated):
            if not isinstance(signal, Signal):
                raise TypeError(
                    "SignalGenerator.generate produced unsupported payload at index "
                    f"{index}: {type(signal).__name__}",
                )
            yield signal

    def _emit_logs(
        self,
        signals: Iterable[Signal],
        decisions: Iterable[RiskDecision],
        executions: Iterable[ExecutionOutcome],
        context: EngineContext,
        data: MarketData,
        *,
        metrics: CycleMetrics,
    ) -> tuple[LogEntry, ...]:
        signals_tuple = tuple(signals)
        decisions_tuple = tuple(decisions)
        executions_tuple = tuple(executions)
        entries = (
            LogEntry(
                level="INFO",
                message="Engine cycle completed",
                context={
                    "run_id": context.run_id,
                    "data_source": data.source,
                    "sequence_number": metrics.sequence_number,
                    "signals": len(signals_tuple),
                    "decisions": len(decisions_tuple),
                    "received_signals": metrics.received_signals,
                    "approved_signals": metrics.approved_signals,
                    "rejected_signals": metrics.rejected_signals,
                    "dispatched_signals": metrics.dispatched_signals,
                    "execution_attempts": metrics.execution_attempts,
                    "executions": len(executions_tuple),
                    "stage_signal_ms": metrics.stage_durations.signal_ms,
                    "stage_risk_ms": metrics.stage_durations.risk_ms,
                    "stage_execution_ms": metrics.stage_durations.execution_ms,
                    "cycle_started_at": metrics.started_at.isoformat(),
                    "cycle_completed_at": metrics.completed_at.isoformat(),
                    "cycle_duration_ms": metrics.duration_ms,
                    "log_entries": 0,
                },
            ),
        )
        log_entries = len(entries)
        for entry in entries:
            entry.context["log_entries"] = log_entries
            self._log_sink.emit(entry, context)
        return entries

    def _collect_and_validate(
        self,
        producer: str,
        values: Iterable[Any],
        expected_type: type[_T],
    ) -> tuple[_T, ...]:
        """Materialize *values* into a tuple while validating item types."""

        collected = tuple(values)
        for index, value in enumerate(collected):
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"{producer} produced unsupported payload at index {index}: "
                    f"{type(value).__name__} (expected {expected_type.__name__})",
                )
        return collected
