# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Example policy loop integration for the dopamine controller."""

from __future__ import annotations

from geosync.core.neuro.dopamine import (
    ActionGate,
    DopamineController,
    adapt_ddm_parameters,
)

da_ctrl = DopamineController("config/dopamine.yaml")


def policy_step(
    reward: float,
    V: float,
    V_next: float,
    reward_proxy: float,
    novelty: float,
    momentum: float,
    value_gap: float,
    Q_value: float,
    serotonin_ctrl=None,
    performance_metrics=None,
):
    """Illustrative policy update that fuses dopamine and serotonin controls."""

    # 1. RPE + оновлення value
    rpe = da_ctrl.compute_rpe(reward, V, V_next)
    da_ctrl.update_value_estimate(rpe)

    # 2. DA сигнал
    appetitive = da_ctrl.estimate_appetitive_state(reward_proxy, novelty, momentum, value_gap)
    DA = da_ctrl.compute_dopamine_signal(appetitive, rpe)

    # 3. Модуляція Q, температура, адаптація DDM
    Q_mod = da_ctrl.modulate_action_value(Q_value, DA)
    gate = ActionGate(da_ctrl, serotonin_ctrl)
    gate_eval = gate.evaluate(DA)
    ddm = adapt_ddm_parameters(
        dopamine_level=gate_eval.dopamine_level,
        base_drift=1.0,
        base_boundary=da_ctrl.config["base_temperature"],
    )

    # 5. Мета-адаптація (опц.)
    if performance_metrics:
        da_ctrl.meta_adapt(performance_metrics)

    # 6. Телеметрія
    da_ctrl.update_metrics()

    return {
        "rpe": rpe,
        "dopamine": DA,
        "Q_mod": Q_mod,
        "temperature": gate_eval.temperature,
        "go": gate_eval.go,
        "no_go": gate_eval.no_go,
        "hold": gate_eval.hold,
        "ddm": {"drift": ddm.drift, "boundary": ddm.boundary},
    }
