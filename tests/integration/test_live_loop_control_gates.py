from __future__ import annotations

import time
import types
from pathlib import Path
from typing import Any

import pytest

from application.runtime.control_gates import Decision, evaluate_control_gates
from domain import Order, OrderSide, OrderType
from execution.connectors import BinanceConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import LimitViolation, OrderRateExceeded, RiskLimits

SUBMISSION_WAIT_S = 2.0
POLL_INTERVAL_S = 0.05


class _DummyKillSwitch:
    def __init__(self) -> None:
        self._triggered = False
        self.reason = ""

    def trigger(self, reason: str) -> None:
        self._triggered = True
        self.reason = reason

    def is_triggered(self) -> bool:
        return self._triggered

    def guard(self) -> None:
        """Present to mirror RiskManager API."""


class _Config:
    def __init__(self, default_decision: str = "ALLOW") -> None:
        self.gate_defaults = {
            "default_decision": default_decision,
            "min_position_multiplier": 0.0,
            "max_position_multiplier": 1.0,
        }
        self.controllers_required = True


class _SerotoninAllow:
    def __init__(self, risk_budget: float = 1.0) -> None:
        self._risk_budget = risk_budget

    def update(self, observation: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            action_gate="ALLOW",
            risk_budget=self._risk_budget,
            reason_codes=(),
            metrics_snapshot={},
        )


class _ThermoAllow:
    controller_state = "OK"
    baseline_F = None
    epsilon_adaptive = 0.0
    circuit_breaker_active = False
    previous_F = 0.0


class GateAwareRisk:
    def __init__(self, default_decision: str = "ALLOW") -> None:
        self.config = _Config(default_decision)
        self.controllers = {"serotonin": _SerotoninAllow(), "thermo": _ThermoAllow()}
        self.kill_switch = _DummyKillSwitch()
        self.limits = RiskLimits(max_notional=1_000_000, max_position=10.0)
        self._signals = {"risk_score": 1.0, "drawdown": -0.01, "free_energy": 0.2}
        self.last_gate: Decision | None = None

    def set_default_decision(self, value: str) -> None:
        self.config.gate_defaults["default_decision"] = value

    def validate_order(self, symbol: str, side: Any, quantity: float, reference_price: float) -> None:
        result = evaluate_control_gates(self.config, self.controllers, dict(self._signals))
        self.last_gate = result.gate.decision
        if result.gate.decision is Decision.DENY:
            self.kill_switch.trigger(";".join(result.gate.reasons))
            raise LimitViolation("control gate deny")
        if result.gate.decision is Decision.THROTTLE:
            raise OrderRateExceeded("control gate throttle")

    def register_fill(self, symbol: str, side: Any, quantity: float, price: float) -> None:
        pass

    def exposure_snapshot(self):
        return {}

    def hydrate_positions(self, snapshot: Any, *, replace: bool = False) -> None:
        pass


class CountingConnector(BinanceConnector):
    def __init__(self) -> None:
        super().__init__()
        self.placements = 0

    def connect(self, credentials: object | None) -> None:  # type: ignore[override]
        self.connected = True

    def disconnect(self) -> None:  # type: ignore[override]
        self.connected = False

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:  # type: ignore[override]
        if not self.connected:
            raise RuntimeError("connector must be connected before placing orders")
        self.placements += 1
        return super().place_order(order, idempotency_key=idempotency_key)


@pytest.fixture()
def live_loop_config(tmp_path: Path):
    return LiveLoopConfig(
        state_dir=tmp_path / "state",
        submission_interval=POLL_INTERVAL_S,
        fill_poll_interval=POLL_INTERVAL_S,
        heartbeat_interval=0.1,
        max_backoff=0.2,
    )


def _submit_sample(loop: LiveExecutionLoop, correlation_id: str) -> Order:
    return loop.submit_order(
        "binance",
        Order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=0.1,
            price=20_000,
            order_type=OrderType.LIMIT,
        ),
        correlation_id=correlation_id,
    )


def test_live_loop_respects_control_gate_decisions(live_loop_config) -> None:
    throttle_connector = CountingConnector()
    throttle_risk = GateAwareRisk(default_decision="THROTTLE")
    throttle_loop = LiveExecutionLoop({"binance": throttle_connector}, throttle_risk, config=live_loop_config)

    throttle_loop.start(cold_start=True)
    try:
        with pytest.raises(OrderRateExceeded):
            _submit_sample(throttle_loop, "throttle-1")
        assert throttle_connector.placements == 0
        assert throttle_risk.last_gate is Decision.THROTTLE
    finally:
        throttle_loop.shutdown()

    deny_connector = CountingConnector()
    deny_risk = GateAwareRisk(default_decision="DENY")
    deny_loop = LiveExecutionLoop({"binance": deny_connector}, deny_risk, config=live_loop_config)

    deny_loop.start(cold_start=True)
    try:
        with pytest.raises(LimitViolation):
            _submit_sample(deny_loop, "deny-1")
        assert deny_risk.kill_switch.is_triggered()
        assert deny_connector.placements == 0
    finally:
        deny_loop.shutdown()

    allow_connector = CountingConnector()
    allow_risk = GateAwareRisk(default_decision="ALLOW")
    allow_loop = LiveExecutionLoop({"binance": allow_connector}, allow_risk, config=live_loop_config)

    allow_loop.start(cold_start=True)
    try:
        _submit_sample(allow_loop, "allow-1")

        deadline = time.monotonic() + SUBMISSION_WAIT_S
        while allow_connector.placements == 0 and time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL_S)
        assert allow_connector.placements >= 1
    finally:
        allow_loop.shutdown()
