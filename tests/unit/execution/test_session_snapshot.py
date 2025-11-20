from __future__ import annotations

import hashlib
import json

import pytest

from execution.connectors import ExecutionConnector
from execution.risk import RiskLimits, RiskManager
from execution.session_snapshot import ExecutionMode, SessionSnapshotter


class StaticConnector(ExecutionConnector):
    def __init__(self) -> None:
        super().__init__()
        self._positions_payload = [
            {
                "symbol": "BTCUSDT",
                "net_quantity": 0.5,
                "average_price": 20_000.0,
            }
        ]

    def get_positions(self):  # type: ignore[override]
        return list(self._positions_payload)


class FailingConnector(ExecutionConnector):
    def __init__(self) -> None:
        super().__init__()

    def get_positions(self):  # type: ignore[override]
        raise RuntimeError("unable to fetch positions")


def test_session_snapshotter_persists_snapshot(tmp_path) -> None:
    directory = tmp_path / "snapshots"
    limits = RiskLimits(
        max_notional=100_000.0,
        max_position=10.0,
        kill_switch_violation_threshold=5,
        kill_switch_rate_limit_threshold=4,
        kill_switch_limit_multiplier=2.0,
    )
    risk_manager = RiskManager(limits)
    risk_manager.register_fill("BTCUSDT", "buy", 0.5, 20_000.0)

    connector = StaticConnector()
    snapshotter = SessionSnapshotter(
        directory, mode=ExecutionMode.LIVE, risk_manager=risk_manager
    )

    path = snapshotter.capture({"binance": connector})

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["mode"] == "live"
    assert payload["venues"][0]["balance"]["estimated_equity"] == pytest.approx(
        10_000.0
    )
    assert payload["venues"][0]["issues"] == []
    assert payload["risk_limits"]["max_position"] == 10.0
    assert payload["kill_switch"]["violation_threshold"] == 5
    assert "hash" in payload
    canonical = json.dumps(
        {k: v for k, v in payload.items() if k != "hash"},
        sort_keys=True,
        separators=(",", ":"),
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == payload["hash"]
    exposure = payload["risk_exposure"]
    assert exposure
    symbol, metrics = next(iter(exposure.items()))
    assert symbol.startswith("BTC")
    assert metrics["notional"] == pytest.approx(10_000.0)


def test_session_snapshotter_records_position_failure(tmp_path) -> None:
    snapshotter = SessionSnapshotter(
        tmp_path / "snapshots",
        mode=ExecutionMode.LIVE,
        risk_manager=RiskManager(RiskLimits()),
    )
    path = snapshotter.capture({"broken": FailingConnector()})
    payload = json.loads(path.read_text())
    issues = payload["venues"][0]["issues"]
    assert issues
    assert issues[0].startswith("positions_unavailable")
