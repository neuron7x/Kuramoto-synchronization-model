# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping

import pytest

from core.events.models import SignalDirection
from core.strategies.engine import (
    InvalidModeTransition,
    IOContract,
    RiskAdviceLevel,
    RiskAssessment,
    StrategyContext,
    StrategyEngine,
    StrategyEngineEvent,
    StrategyEngineMode,
    StrategyEventType,
    StrategySignal,
)


@dataclass
class _StubModule:
    name: str
    input_contract: IOContract
    output_contract: IOContract
    events: Iterable[StrategyEngineEvent]
    processed: int = 0

    def process(self, context: StrategyContext) -> Iterable[StrategyEngineEvent]:
        self.processed += 1
        return self.events


class _BlockingRiskPolicy:
    def __init__(
        self,
        approved: bool,
        *,
        adjustments: Mapping[str, object] | None = None,
        reason: str | None = None,
    ) -> None:
        self._assessment = RiskAssessment(
            approved=approved,
            reason=reason,
            adjustments=adjustments or {},
        )
        self.calls: list[tuple[StrategySignal, StrategyEngineMode]] = []

    def assess(self, signal: StrategySignal, *, mode: StrategyEngineMode) -> RiskAssessment:
        self.calls.append((signal, mode))
        return self._assessment


def _context(data: Mapping[str, object]) -> StrategyContext:
    return StrategyContext(
        timestamp=datetime.now(timezone.utc),
        data=data,
        mode=StrategyEngineMode.PAPER,
    )


def _make_signal_event(signal_id: str = "sig-1", strength: float = 1.0) -> StrategyEngineEvent:
    signal = StrategySignal(
        signal_id=signal_id,
        symbol="BTCUSDT",
        direction=SignalDirection.BUY,
        strength=strength,
        confidence=0.8,
    )
    return StrategyEngineEvent(
        type=StrategyEventType.SIGNAL,
        module="stub",
        payload=signal,
    )


def test_engine_enforces_input_contract() -> None:
    module = _StubModule(
        name="stub",
        input_contract=IOContract(required={"prices": list}),
        output_contract=IOContract(),
        events=(),
    )
    engine = StrategyEngine(modules=[module])
    with pytest.raises(ValueError):
        engine.process(_context({"volumes": [1, 2, 3]}))


def test_io_contract_validates_optional_fields() -> None:
    contract = IOContract(optional={"volumes": list})
    contract.validate({"volumes": [1, 2, 3]}, contract_name="optional")
    with pytest.raises(TypeError):
        contract.validate({"volumes": (1, 2, 3)}, contract_name="optional")


def test_engine_routes_signal_when_risk_approves() -> None:
    captured: list[StrategyEngineEvent] = []
    routed: list[tuple[StrategySignal, RiskAssessment]] = []

    def listener(event: StrategyEngineEvent) -> None:
        captured.append(event)

    policy = _BlockingRiskPolicy(True, adjustments={"strength": 0.5}, reason="scaled")
    engine = StrategyEngine(
        risk_policy=policy,
        signal_router=lambda signal, assessment: routed.append((signal, assessment)),
    )
    engine.subscribe(StrategyEventType.SIGNAL, listener)
    engine.subscribe(StrategyEventType.RISK_ADVICE, listener)
    module = _StubModule(
        name="stub",
        input_contract=IOContract(required={"prices": list}),
        output_contract=IOContract(),
        events=[_make_signal_event()],
    )
    engine.register_module(module)

    events = engine.process(_context({"prices": [1.0, 2.0, 3.0]}))

    assert policy.calls and policy.calls[0][1] is StrategyEngineMode.PAPER
    assert len(events) == 2  # adjusted signal + risk advice
    signal_event = next(event for event in events if event.type is StrategyEventType.SIGNAL)
    assert signal_event.payload.strength == pytest.approx(0.5)
    assert routed[0][0].strength == pytest.approx(0.5)
    advice_event = next(event for event in events if event.type is StrategyEventType.RISK_ADVICE)
    assert advice_event.payload.level is RiskAdviceLevel.WARN
    assert captured == list(events)


def test_engine_blocks_signal_when_risk_denies() -> None:
    advice_messages: list[str] = []

    def sink(advice) -> None:
        advice_messages.append(advice.message)

    policy = _BlockingRiskPolicy(False, reason="limit breached")
    engine = StrategyEngine(
        risk_policy=policy,
        risk_advice_sink=sink,
        signal_router=lambda *_: (_ for _ in ()).throw(RuntimeError),
    )
    module = _StubModule(
        name="stub",
        input_contract=IOContract(required={"prices": list}),
        output_contract=IOContract(),
        events=[_make_signal_event()],
    )
    engine.register_module(module)

    events = engine.process(_context({"prices": [1.0, 2.0, 3.0]}))

    assert len(events) == 1
    event = events[0]
    assert event.type is StrategyEventType.RISK_ADVICE
    assert event.payload.level is RiskAdviceLevel.BLOCK
    assert "limit" in event.payload.message
    assert advice_messages == [event.payload.message]


def test_engine_enforces_output_contract() -> None:
    module = _StubModule(
        name="stub",
        input_contract=IOContract(required={"prices": list}),
        output_contract=IOContract(required={"strength": int}),
        events=[_make_signal_event()],
    )
    engine = StrategyEngine(modules=[module])

    with pytest.raises(TypeError):
        engine.process(_context({"prices": [1.0, 2.0, 3.0]}))


def test_engine_state_machine_transitions() -> None:
    engine = StrategyEngine()
    assert engine.mode is StrategyEngineMode.PAPER
    engine.set_mode(StrategyEngineMode.LIVE)
    assert engine.mode is StrategyEngineMode.LIVE
    engine.pause()
    assert engine.mode is StrategyEngineMode.PAUSED
    engine.resume()
    assert engine.mode is StrategyEngineMode.LIVE
    with pytest.raises(InvalidModeTransition):
        engine.resume()


def test_processing_skipped_when_paused() -> None:
    module = _StubModule(
        name="stub",
        input_contract=IOContract(required={"prices": list}),
        output_contract=IOContract(),
        events=[_make_signal_event()],
    )
    engine = StrategyEngine(modules=[module])
    engine.pause()
    events = engine.process(_context({"prices": [1.0, 2.0, 3.0]}))
    assert events == ()
    assert module.processed == 0
