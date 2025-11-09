"""Minimal executable core trading engine (Core Engine v1)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


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

    def generate(self, data: MarketData, context: EngineContext) -> Iterable[Signal] | Signal | None:
        """Produce zero or more signals for the supplied market data."""


@runtime_checkable
class RiskManager(Protocol):
    """Evaluates whether a :class:`Signal` can proceed to execution."""

    def assess(self, signal: Signal, context: EngineContext) -> RiskDecision:
        """Return the risk decision for the provided signal."""


@runtime_checkable
class ExecutionClient(Protocol):
    """Handles interaction with trading venues, brokers, or downstream systems."""

    def execute(self, signal: Signal, decision: RiskDecision, context: EngineContext) -> ExecutionOutcome:
        """Execute the signal in accordance with the supplied risk decision."""


@runtime_checkable
class LogSink(Protocol):
    """Receives structured log entries emitted by the engine."""

    def emit(self, entry: LogEntry, context: EngineContext) -> None:
        """Persist or forward the given log entry."""


@dataclass(slots=True)
class EngineCycle:
    """Encapsulates the artefacts produced by a single engine step."""

    market_data: MarketData
    signals: tuple[Signal, ...]
    decisions: tuple[RiskDecision, ...]
    executions: tuple[ExecutionOutcome, ...]
    logs: tuple[LogEntry, ...]


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
            for market_data in self._yield_data(context):
                signals = tuple(self._yield_signals(market_data, context))
                decisions = tuple(
                    self._risk_manager.assess(signal, context) for signal in signals
                )
                received_count = len(signals)
                approved_count = sum(1 for decision in decisions if decision.approved)
                rejected_count = received_count - approved_count

                if self._config.drop_rejected_signals:
                    approved_pairs = tuple(
                        (signal, decision)
                        for signal, decision in zip(signals, decisions, strict=True)
                        if decision.approved
                    )
                    signals = tuple(signal for signal, _ in approved_pairs)
                    decisions = tuple(decision for _, decision in approved_pairs)

                executions = tuple(
                    self._execution_client.execute(signal, decision, context)
                    for signal, decision in zip(signals, decisions, strict=True)
                )

                logs = self._emit_logs(
                    signals,
                    decisions,
                    executions,
                    context,
                    market_data,
                    received_signals=received_count,
                    approved_signals=approved_count,
                    rejected_signals=rejected_count,
                )

                yield EngineCycle(
                    market_data=market_data,
                    signals=signals,
                    decisions=decisions,
                    executions=executions,
                    logs=logs,
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
        for item in raw:
            yield item

    def _yield_signals(self, data: MarketData, context: EngineContext) -> Iterator[Signal]:
        generated = self._signal_generator.generate(data, context)
        if generated is None:
            return
        if isinstance(generated, Signal):
            yield generated
            return
        for signal in generated:
            yield signal

    def _emit_logs(
        self,
        signals: Iterable[Signal],
        decisions: Iterable[RiskDecision],
        executions: Iterable[ExecutionOutcome],
        context: EngineContext,
        data: MarketData,
        *,
        received_signals: int,
        approved_signals: int,
        rejected_signals: int,
    ) -> tuple[LogEntry, ...]:
        signals_tuple = tuple(signals)
        executions_tuple = tuple(executions)
        entries = (
            LogEntry(
                level="INFO",
                message="Engine cycle completed",
                context={
                    "run_id": context.run_id,
                    "data_source": data.source,
                    "signals": len(signals_tuple),
                    "received_signals": received_signals,
                    "approved_signals": approved_signals,
                    "rejected_signals": rejected_signals,
                    "executions": len(executions_tuple),
                },
            ),
        )
        for entry in entries:
            self._log_sink.emit(entry, context)
        return entries
