# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from core.utils.slo import (
    AutoRollbackGuard,
    RequestSample,
    SLOBurnRateRule,
    SLOConfig,
    _percentile,
)


@pytest.fixture()
def base_time() -> datetime:
    return datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_auto_rollback_guard_triggers_on_error_rate(base_time: datetime) -> None:
    triggered: List[str] = []

    def rollback(reason: str, summary: dict[str, float]) -> None:
        triggered.append(reason)
        assert reason == "error_rate"
        assert summary["error_rate"] >= 0.5

    config = SLOConfig(
        error_rate_threshold=0.4,
        latency_threshold_ms=500.0,
        min_requests=3,
        evaluation_period=timedelta(minutes=5),
        cooldown=timedelta(seconds=0),
    )

    guard = AutoRollbackGuard(config=config, rollback_callback=rollback)
    for idx, success in enumerate([True, False, False]):
        timestamp = base_time + timedelta(seconds=idx)
        should_trigger = guard.record_outcome(120.0, success, timestamp=timestamp)
        if idx < 2:
            assert should_trigger is False
        else:
            assert should_trigger is True

    assert triggered == ["error_rate"]
    summary = guard.last_summary
    assert summary is not None
    assert summary["reason"] == "error_rate"
    assert summary["total_requests"] == 3.0


def test_auto_rollback_guard_respects_cooldown(base_time: datetime) -> None:
    triggered: List[str] = []

    config = SLOConfig(
        error_rate_threshold=0.3,
        latency_threshold_ms=300.0,
        min_requests=2,
        evaluation_period=timedelta(minutes=5),
        cooldown=timedelta(seconds=30),
    )
    guard = AutoRollbackGuard(config=config, rollback_callback=lambda r, s: triggered.append(r))

    first_trigger_time = base_time + timedelta(seconds=1)
    guard.record_outcome(200.0, True, timestamp=base_time)
    assert guard.record_outcome(600.0, True, timestamp=first_trigger_time) is True
    assert triggered == ["latency"]

    within_cooldown = first_trigger_time + timedelta(seconds=10)
    assert (
        guard.evaluate_snapshot(
            error_rate=0.5,
            latency_p95_ms=1000.0,
            timestamp=within_cooldown,
            total_requests=100,
        )
        is False
    )

    outside_cooldown = first_trigger_time + timedelta(seconds=45)
    assert (
        guard.evaluate_snapshot(
            error_rate=0.6,
            latency_p95_ms=900.0,
            timestamp=outside_cooldown,
            total_requests=120,
        )
        is True
    )
    assert triggered == ["latency", "error_rate"]


def test_record_outcome_rejects_negative_latency(base_time: datetime) -> None:
    guard = AutoRollbackGuard(config=SLOConfig(min_requests=1))
    with pytest.raises(ValueError):
        guard.record_outcome(-1.0, True, timestamp=base_time)


def test_percentile_helper_covers_edge_cases() -> None:
    assert _percentile([], 50) == 0.0
    assert _percentile([1.0, 2.0, 3.0], -10) == 1.0
    assert _percentile([1.0, 2.0, 3.0], 150) == 3.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


def test_prune_discards_old_samples(base_time: datetime) -> None:
    config = SLOConfig(min_requests=1, evaluation_period=timedelta(seconds=30))
    guard = AutoRollbackGuard(config=config)
    old_event = RequestSample(base_time - timedelta(seconds=60), 100.0, True)
    guard._events.append(old_event)
    guard.record_outcome(120.0, True, timestamp=base_time)
    assert all(sample.timestamp >= base_time - timedelta(seconds=30) for sample in guard._events)


def test_burn_rate_rules_trigger_before_slo_breach(base_time: datetime) -> None:
    triggered: list[tuple[str, dict[str, float]]] = []

    config = SLOConfig(
        error_rate_threshold=0.02,
        latency_threshold_ms=500.0,
        evaluation_period=timedelta(minutes=10),
        min_requests=50,
        cooldown=timedelta(seconds=0),
        burn_rate_rules=(
            SLOBurnRateRule(
                window=timedelta(minutes=1),
                max_burn_rate=4.0,
                min_requests=10,
                name="1m",
            ),
        ),
    )
    guard = AutoRollbackGuard(
        config=config,
        rollback_callback=lambda reason, summary: triggered.append((reason, summary)),
    )

    # Baseline healthy traffic within the evaluation period.
    for idx in range(200):
        guard.record_outcome(
            120.0,
            True,
            timestamp=base_time + timedelta(seconds=idx * 2),
        )

    # Recent spike of errors contained in the short burn-rate window.
    burn_window_start = base_time + timedelta(seconds=540)
    recent_outcomes = [False, False, False, False] + [True] * 6
    for offset, success in enumerate(recent_outcomes):
        guard.record_outcome(
            130.0,
            success,
            timestamp=burn_window_start + timedelta(seconds=offset * 5),
        )

    assert triggered, "Expected burn-rate policy to trigger a rollback"
    reason, summary = triggered[-1]
    assert reason == "burn_rate[1m]"
    assert summary["reason"] == "burn_rate[1m]"
    assert summary["error_rate"] < config.error_rate_threshold
    assert summary["burn_rate[1m]"] == pytest.approx(20.0)
    assert summary["requests[1m]"] == pytest.approx(10.0)
    assert summary["burn_rate_window_seconds"] == pytest.approx(60.0)
    assert summary["burn_rate_threshold"] == pytest.approx(4.0)
    assert summary["total_requests"] == pytest.approx(210.0)
    assert summary["error_budget"] == pytest.approx(config.error_rate_threshold)


def test_retention_expands_for_burn_rate_windows(base_time: datetime) -> None:
    config = SLOConfig(
        min_requests=1,
        evaluation_period=timedelta(seconds=30),
        burn_rate_rules=(SLOBurnRateRule(window=timedelta(minutes=2), max_burn_rate=2.0),),
    )
    guard = AutoRollbackGuard(config=config)

    retained_event = RequestSample(base_time - timedelta(seconds=110), 100.0, True)
    guard._events.append(retained_event)
    guard.record_outcome(90.0, True, timestamp=base_time)
    assert any(sample.timestamp == retained_event.timestamp for sample in guard._events)

    guard.record_outcome(95.0, True, timestamp=base_time + timedelta(seconds=121))
    assert all(sample.timestamp >= base_time + timedelta(seconds=1) for sample in guard._events)
