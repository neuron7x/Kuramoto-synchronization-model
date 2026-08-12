# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from core.data.resampling import align_timeframes, resample_ticks_to_l1
from src.data.backlog_watermark import WatermarkBacklog


def _dt(seconds: float) -> datetime:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(seconds=seconds)


class _FakeClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def __call__(self) -> datetime:
        return self._now


def test_watermark_backlog_orders_streams_and_filters_expired() -> None:
    backlog = WatermarkBacklog(
        allowed_lateness=timedelta(seconds=2),
        expiration=timedelta(seconds=6),
    )
    assert backlog.observe("alpha", _dt(2), payload={"price": 101}, arrival_time=_dt(3))
    assert backlog.observe("beta", _dt(1), payload={"price": 100}, arrival_time=_dt(3))
    assert backlog.observe("alpha", _dt(5), payload={"price": 102}, arrival_time=_dt(6))
    assert (
        backlog.observe("beta", _dt(-10), payload={"price": 90}, arrival_time=_dt(1))
        is None
    )
    assert backlog.observe("beta", _dt(4), payload={"price": 103}, arrival_time=_dt(6))

    ready = backlog.drain_ready()
    assert [event.event_time for event in ready] == [_dt(1), _dt(2)]
    assert backlog.dropped_events == 1
    assert backlog.watermark and backlog.watermark >= _dt(2)


def test_progress_markers_and_monotonic_indices() -> None:
    backlog = WatermarkBacklog(
        allowed_lateness=timedelta(seconds=1),
        expiration=timedelta(seconds=5),
    )
    backlog.observe("alpha", _dt(0), payload={}, arrival_time=_dt(0.2))
    backlog.observe("beta", _dt(0.5), payload={}, arrival_time=_dt(0.7))
    backlog.observe("alpha", _dt(3), payload={}, arrival_time=_dt(3.2))
    backlog.observe("beta", _dt(4), payload={}, arrival_time=_dt(4.1))
    backlog.observe("alpha", _dt(6), payload={}, arrival_time=_dt(6.1))
    backlog.observe("beta", _dt(6), payload={}, arrival_time=_dt(6.2))

    ready = backlog.drain_ready()
    assert len(ready) >= 4
    indices = [event.index for event in ready]
    assert indices == sorted(indices)
    progress = backlog.progress_snapshot()
    assert set(progress) == {"alpha", "beta"}
    assert all(marker.watermark == backlog.watermark for marker in progress.values())
    history = backlog.progress_history()
    assert history
    assert history[-1].processed_index == max(indices)


def test_lag_calibration_and_delay_visualisation() -> None:
    backlog = WatermarkBacklog(
        allowed_lateness=timedelta(seconds=1),
        expiration=timedelta(seconds=10),
    )
    for i in range(3):
        backlog.observe(
            "alpha",
            _dt(i),
            payload={},
            arrival_time=_dt(i + 1),
        )
    for i in range(3):
        backlog.observe(
            "beta",
            _dt(i + 0.5),
            payload={},
            arrival_time=_dt(i + 1.8),
        )
    backlog.observe("alpha", _dt(6), payload={}, arrival_time=_dt(6.2))
    backlog.observe("beta", _dt(6), payload={}, arrival_time=_dt(6.5))
    backlog.drain_ready()

    summary = backlog.lag_summary()
    assert summary["alpha"].count >= 3
    assert summary["beta"].count >= 3
    assert 0.75 <= summary["alpha"].average_seconds <= 1.05
    assert 1.0 <= summary["beta"].average_seconds <= 1.35
    series = backlog.delay_series()
    assert {"alpha", "beta"} == set(series)
    assert all(sample.delay_seconds >= 0 for sample in series["alpha"])


def test_resampling_and_synchronisation_edge_cases() -> None:
    backlog = WatermarkBacklog(
        allowed_lateness=timedelta(seconds=1),
        expiration=timedelta(seconds=8),
    )
    for offset, price in enumerate((100, 101, 102), start=0):
        backlog.observe(
            "alpha",
            _dt(offset),
            payload={"price": price, "size": 1},
            arrival_time=_dt(offset + 0.3),
        )
    for offset, price in enumerate((200, 201, 202), start=1):
        backlog.observe(
            "beta",
            _dt(offset + 0.5),
            payload={"price": price, "size": 2},
            arrival_time=_dt(offset + 1.0),
        )
    backlog.observe(
        "alpha", _dt(10), payload={"price": 110, "size": 1}, arrival_time=_dt(11)
    )
    backlog.observe(
        "beta", _dt(10), payload={"price": 210, "size": 2}, arrival_time=_dt(11)
    )
    ready = backlog.drain_ready()

    alpha_rows = [
        {"price": event.payload["price"], "size": event.payload.get("size", 0)}
        for event in ready
        if event.source == "alpha"
    ]
    alpha_index = [event.event_time for event in ready if event.source == "alpha"]
    beta_rows = [
        {"price": event.payload["price"], "size": event.payload.get("size", 0)}
        for event in ready
        if event.source == "beta"
    ]
    beta_index = [event.event_time for event in ready if event.source == "beta"]

    alpha_frame = pd.DataFrame(alpha_rows, index=pd.DatetimeIndex(alpha_index))
    beta_frame = pd.DataFrame(beta_rows, index=pd.DatetimeIndex(beta_index))
    assert alpha_frame.index.is_monotonic_increasing
    assert beta_frame.index.is_monotonic_increasing

    l1 = resample_ticks_to_l1(
        alpha_frame, freq="1s", price_col="price", size_col="size"
    )
    assert not l1.empty
    aligned = align_timeframes(
        {"alpha": alpha_frame, "beta": beta_frame}, reference="alpha"
    )
    assert aligned["alpha"].index.equals(aligned["beta"].index)
    assert aligned["alpha"].index.is_monotonic_increasing


def test_inactive_sources_stop_blocking_watermark_progress() -> None:
    clock = _FakeClock(_dt(0))
    backlog = WatermarkBacklog(
        allowed_lateness=timedelta(seconds=1),
        expiration=timedelta(seconds=5),
        clock=clock,
    )
    backlog.observe("alpha", _dt(0), payload={})
    backlog.observe("beta", _dt(0), payload={})

    clock.advance(timedelta(seconds=10))
    backlog.observe("alpha", _dt(10), payload={})
    clock.advance(timedelta(seconds=2))
    backlog.observe("alpha", _dt(12), payload={})

    ready = backlog.drain_ready()
    ready_times = [event.event_time for event in ready]
    assert _dt(10) in ready_times
    assert backlog.watermark == _dt(11)


def test_pruned_sources_are_removed_from_lag_and_delay_views() -> None:
    clock = _FakeClock(_dt(0))
    backlog = WatermarkBacklog(
        allowed_lateness=timedelta(seconds=1),
        expiration=timedelta(seconds=5),
        clock=clock,
    )

    backlog.observe("alpha", _dt(0), payload={}, arrival_time=_dt(0.1))
    backlog.observe("beta", _dt(0), payload={}, arrival_time=_dt(0.2))
    backlog.observe("alpha", _dt(3), payload={}, arrival_time=_dt(3.1))

    clock.advance(timedelta(seconds=10))
    backlog.observe("alpha", _dt(10), payload={}, arrival_time=_dt(10.1))
    backlog.drain_ready()

    assert "beta" not in backlog.lag_summary()
    assert "beta" not in backlog.delay_series()
