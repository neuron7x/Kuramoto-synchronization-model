# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from application.runtime.control_gates import Decision, evaluate_control_gates
from domain import Order, OrderSide, OrderType
from execution.connectors import BinanceConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import LimitViolation, OrderRateExceeded, RiskLimits

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

    def validate_order(
        self, symbol: str, side: Any, quantity: float, reference_price: float
    ) -> None:
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
    def _run_scenario(
        default_decision: str,
        correlation_id: str,
        assertion_fn,
    ) -> None:
        connector = CountingConnector()
        risk = GateAwareRisk(default_decision=default_decision)
        loop = LiveExecutionLoop({"binance": connector}, risk, config=live_loop_config)
        loop.start(cold_start=True)
        try:
            assertion_fn(loop, connector, risk, correlation_id)
        finally:
            loop.shutdown()

    def _assert_throttle(
        loop: LiveExecutionLoop, connector: CountingConnector, risk: GateAwareRisk, cid: str
    ) -> None:
        with pytest.raises(OrderRateExceeded):
            _submit_sample(loop, cid)
        assert connector.placements == 0
        assert risk.last_gate is Decision.THROTTLE

    def _assert_deny(
        loop: LiveExecutionLoop, connector: CountingConnector, risk: GateAwareRisk, cid: str
    ) -> None:
        with pytest.raises(LimitViolation):
            _submit_sample(loop, cid)
        assert risk.kill_switch.is_triggered()
        assert connector.placements == 0

    def _assert_allow(
        loop: LiveExecutionLoop, connector: CountingConnector, risk: GateAwareRisk, cid: str
    ) -> None:
        _submit_sample(loop, cid)
        for _ in range(3):
            try:
                loop._contexts["binance"].oms.process_next()
                break
            except LookupError:
                continue
        assert connector.placements >= 1

    _run_scenario("THROTTLE", "throttle-1", _assert_throttle)
    _run_scenario("DENY", "deny-1", _assert_deny)
    _run_scenario("ALLOW", "allow-1", _assert_allow)
