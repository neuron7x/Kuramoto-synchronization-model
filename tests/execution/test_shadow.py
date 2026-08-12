# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from domain.signal import Signal, SignalAction
from execution.shadow import (
    ShadowArchiveRecord,
    ShadowDecision,
    ShadowDeploymentConfig,
    ShadowDeploymentOrchestrator,
    ShadowMetrics,
)


class InMemoryArchive:
    def __init__(self) -> None:
        self.records: list[ShadowArchiveRecord] = []

    def persist(self, record: ShadowArchiveRecord) -> None:
        self.records.append(record)


class DeterministicBaseline:
    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self, market_state: Mapping[str, Any]) -> Signal:
        self._ticks += 1
        timestamp = market_state.get(
            "timestamp", datetime.now(timezone.utc) + timedelta(seconds=self._ticks)
        )
        return Signal(
            symbol=str(market_state.get("symbol", "BTCUSDT")),
            action=SignalAction.HOLD,
            confidence=0.6,
            timestamp=timestamp,
        )


def _candidate_same(market_state: Mapping[str, Any]) -> Signal:
    return Signal(
        symbol=str(market_state.get("symbol", "BTCUSDT")),
        action=SignalAction.HOLD,
        confidence=0.6,
        timestamp=market_state["timestamp"],
    )


def _candidate_flip(market_state: Mapping[str, Any]) -> Signal:
    return Signal(
        symbol=str(market_state.get("symbol", "BTCUSDT")),
        action=SignalAction.BUY,
        confidence=0.9,
        timestamp=market_state["timestamp"],
    )


def test_shadow_orchestrator_promotes_candidate_when_stable() -> None:
    archive = InMemoryArchive()
    baseline = DeterministicBaseline()
    config = ShadowDeploymentConfig(
        window_size=5,
        min_samples=3,
        promotion_stable_observations=2,
        promotion_disagreement_rate=0.02,
        promotion_confidence_mape=0.02,
        promotion_action_drift=0.02,
    )
    orchestrator = ShadowDeploymentOrchestrator(
        baseline=baseline,
        candidates={"candidate": _candidate_same},
        config=config,
        archive=archive,
    )

    for index in range(3):
        timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index)
        decisions = orchestrator.process({"timestamp": timestamp, "symbol": "BTCUSDT"})

    decision = decisions["candidate"]
    assert decision.action == "promote"
    assert orchestrator.status()["candidate"] == "promoted"
    assert len(archive.records) == 3
    latest = archive.records[-1]
    assert latest.candidate == "candidate"
    assert latest.decision.action == "promote"
    assert isinstance(latest.decision.metrics, ShadowMetrics)
    assert latest.decision.metrics.disagreement_rate == pytest.approx(0.0)


def test_shadow_orchestrator_rejects_on_guardrail_breach() -> None:
    archive = InMemoryArchive()
    baseline = DeterministicBaseline()
    config = ShadowDeploymentConfig(
        window_size=4,
        min_samples=3,
        max_disagreement_rate=0.1,
        max_confidence_mape=0.3,
        max_action_drift=0.5,
        promotion_stable_observations=2,
    )
    orchestrator = ShadowDeploymentOrchestrator(
        baseline=baseline,
        candidates={"noisy": _candidate_flip},
        config=config,
        archive=archive,
    )

    decision: ShadowDecision | None = None
    for index in range(4):
        timestamp = datetime(2024, 2, 1, tzinfo=timezone.utc) + timedelta(seconds=index)
        decision = orchestrator.process({"timestamp": timestamp, "symbol": "ETHUSDT"})["noisy"]
        if decision.action != "continue":
            break

    assert decision is not None
    assert decision.action == "reject"
    assert decision.reason == "guardrail-breach"
    assert orchestrator.status()["noisy"] == "rejected"
    assert archive.records[-1].decision.action == "reject"
    assert archive.records[-1].deviation.action_mismatch is True


def test_shadow_orchestrator_handles_candidate_errors() -> None:
    archive = InMemoryArchive()
    baseline = DeterministicBaseline()

    def failing_candidate(_: Mapping[str, Any]) -> Signal:
        raise RuntimeError("boom")

    config = ShadowDeploymentConfig(window_size=2, min_samples=1, promotion_stable_observations=1)
    orchestrator = ShadowDeploymentOrchestrator(
        baseline=baseline,
        candidates={"failing": failing_candidate},
        config=config,
        archive=archive,
    )

    timestamp = datetime(2024, 3, 1, tzinfo=timezone.utc)
    decisions = orchestrator.process({"timestamp": timestamp, "symbol": "SOLUSDT"})
    decision = decisions["failing"]

    assert decision.action == "reject"
    assert decision.reason == "generator-error"
    assert orchestrator.status()["failing"] == "rejected"
    assert len(archive.records) == 1
    record = archive.records[0]
    assert record.candidate_signal == record.baseline_signal
    assert record.decision.action == "reject"
