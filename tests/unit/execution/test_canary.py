# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import itertools

from execution.canary import CanaryConfig, CanaryController, MetricThreshold
from execution.risk import KillSwitch


def test_canary_controller_triggers_on_drawdown():
    kill_switch = KillSwitch()
    config = CanaryConfig(max_relative_drawdown=0.1, grace_period=1, cooldown_seconds=0.0)
    controller = CanaryController(
        config, kill_switch=kill_switch, time_source=itertools.count().__next__
    )

    assert controller.evaluate({"pnl": 0.0}).action == "continue"
    assert controller.evaluate({"pnl": 1.0}).action == "continue"
    decision = controller.evaluate({"pnl": 0.8})
    assert decision.action == "disable"
    assert kill_switch.is_triggered()


def test_canary_controller_respects_metric_thresholds():
    config = CanaryConfig(
        metric_thresholds={"latency_ms": MetricThreshold(upper=150)},
        grace_period=0,
        cooldown_seconds=10.0,
    )
    controller = CanaryController(config, time_source=itertools.count().__next__)
    decision = controller.evaluate({"pnl": 0.0, "latency_ms": 200})
    assert decision.action == "disable"
    controller.reset()
    assert controller.evaluate({"pnl": 0.0, "latency_ms": 100}).action == "continue"
