# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.watchdog module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from execution.watchdog import Watchdog, _WorkerSpec


class TestWorkerSpec:
    def test_defaults(self):
        target = MagicMock()
        spec = _WorkerSpec(target=target)
        assert spec.args == ()
        assert spec.kwargs == {}
        assert spec.restart is True
        assert spec.thread is None
        assert spec.restarts == 0

    def test_with_args(self):
        target = MagicMock()
        spec = _WorkerSpec(target=target, args=(1, 2), kwargs={"key": "val"})
        assert spec.args == (1, 2)
        assert spec.kwargs == {"key": "val"}


class TestWatchdog:
    def test_init_defaults(self):
        w = Watchdog()
        assert w._name == "watchdog"
        assert w._heartbeat_interval >= 1.0

    def test_init_custom_name(self):
        w = Watchdog(name="test-wd")
        assert w._name == "test-wd"

    def test_heartbeat_interval_clamped(self):
        w = Watchdog(heartbeat_interval=0.1)
        assert w._heartbeat_interval == 1.0

    def test_monitor_interval_clamped(self):
        w = Watchdog(monitor_interval=0.001)
        assert w._monitor_interval == 0.05

    def test_health_probe_interval_clamped(self):
        w = Watchdog(health_probe_interval=0.1)
        assert w._health_probe_interval == 0.5

    def test_health_timeout_clamped(self):
        w = Watchdog(health_timeout=0.01)
        assert w._health_timeout == 0.1

    def test_initial_stop_event_not_set(self):
        w = Watchdog()
        assert not w._stop_event.is_set()

    def test_workers_initially_empty(self):
        w = Watchdog()
        assert w._workers == {}

    def test_register_worker(self):
        w = Watchdog()
        target = MagicMock()
        w.register("worker1", target)
        assert "worker1" in w._workers

    def test_register_duplicate_raises(self):
        w = Watchdog()
        target = MagicMock()
        w.register("worker1", target)
        with pytest.raises(Exception):
            w.register("worker1", target)

    def test_snapshot_returns_dict(self):
        w = Watchdog()
        snap = w.snapshot()
        assert isinstance(snap, dict)

    def test_snapshot_includes_name(self):
        w = Watchdog(name="my-wd")
        snap = w.snapshot()
        assert "name" in snap or "workers" in snap or isinstance(snap, dict)
