# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified dopamine step helper for policy pipelines."""

from __future__ import annotations

from typing import Mapping, Optional, TypedDict

from geosync.core.neuro.dopamine.dopamine_controller import DopamineController


class StepResult(TypedDict):
    """Telemetry snapshot returned by :func:`dopamine_step`."""

    rpe: float
    value_estimate: float
    dopamine: float
    temperature: float
    q_modulated: float
    go: bool
    no_go: bool
    hold: bool


def dopamine_step(
    ctrl: DopamineController,
    reward: float,
    value: float,
    next_value: float,
    reward_proxy: float,
    novelty: float,
    momentum: float,
    value_gap: float,
    original_q: float,
    performance_metrics: Optional[Mapping[str, float]] = None,
    *,
    discount_gamma: Optional[float] = None,
) -> StepResult:
    """Execute a full dopamine update step and return the captured metrics."""

    rpe = ctrl.compute_rpe(reward, value, next_value, discount_gamma=discount_gamma)
    ctrl.update_value_estimate(rpe)
    appetitive = ctrl.estimate_appetitive_state(reward_proxy, novelty, momentum, value_gap)
    da = ctrl.compute_dopamine_signal(appetitive, rpe)
    q_mod = ctrl.modulate_action_value(original_q, da)
    temp = ctrl.compute_temperature(da)
    go = ctrl.check_invigoration(da)
    no_go = ctrl.check_suppress(da)
    hold = not go and not no_go
    if performance_metrics:
        missing = {"drawdown", "sharpe"} - set(performance_metrics)
        if missing:
            raise ValueError(
                "performance_metrics is missing required keys: " + ", ".join(sorted(missing))
            )
        metrics = {
            "drawdown": float(performance_metrics["drawdown"]),
            "sharpe": float(performance_metrics["sharpe"]),
        }
        ctrl.meta_adapt(metrics)
    ctrl.update_metrics()
    return StepResult(
        rpe=rpe,
        value_estimate=ctrl.value_estimate,
        dopamine=da,
        temperature=temp,
        q_modulated=q_mod,
        go=go,
        no_go=no_go,
        hold=hold,
    )
