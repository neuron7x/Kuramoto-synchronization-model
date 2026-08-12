from __future__ import annotations

import numpy as np
import pandas as pd

from src.kuramoto_trader.bridge.gate_runner import GateRunner


def test_sensor_absent_during_warmup() -> None:
    g = GateRunner(window=8)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    d = g.tick(100.0, ts)
    assert d.state == "SENSOR_ABSENT"


def test_gate_ready_on_synchronized_signal() -> None:
    g = GateRunner(window=16, threshold=0.2)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    d = None
    for i in range(40):
        d = g.tick(100 + np.sin(i / 4), ts + pd.Timedelta(hours=i))
    assert d is not None and d.state in {"READY", "BLOCKED"}


def test_gate_blocked_on_random_signal() -> None:
    rng = np.random.default_rng(42)
    g = GateRunner(window=16, threshold=0.95)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    d = None
    for i in range(40):
        d = g.tick(float(rng.normal()), ts + pd.Timedelta(hours=i))
    assert d is not None and d.state == "BLOCKED"


def test_history_schema() -> None:
    g = GateRunner(window=4)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    for i in range(6):
        g.tick(100 + i, ts + pd.Timedelta(hours=i))
    h = g.history()
    assert list(h.columns) == ["ts", "R", "state", "execution_allowed"]


def test_execution_allowed_only_when_ready() -> None:
    g = GateRunner(window=8, threshold=0.9)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    for i in range(20):
        d = g.tick(100 + np.sin(i), ts + pd.Timedelta(hours=i))
    assert d.execution_allowed == (d.state == "READY")
