"""Example policy loop integration for the dopamine controller."""

from __future__ import annotations

from tradepulse.core.neuro.dopamine import DopamineController


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

    # 3. Модуляція Q, температура
    Q_mod = da_ctrl.modulate_action_value(Q_value, DA)
    T = da_ctrl.compute_temperature(DA)

    # 4. Go / No-Go (з урахуванням серотоніну)
    go = da_ctrl.check_invigoration(DA)
    no_go = da_ctrl.check_suppress(DA)
    if serotonin_ctrl:
        no_go = no_go or serotonin_ctrl.check_cooldown()
        if hasattr(serotonin_ctrl, "temperature_floor"):
            T = max(T, getattr(serotonin_ctrl, "temperature_floor"))

    # 5. Мета-адаптація (опц.)
    if performance_metrics:
        da_ctrl.meta_adapt(performance_metrics)

    # 6. Телеметрія
    da_ctrl.update_metrics()

    return {
        "rpe": rpe,
        "dopamine": DA,
        "Q_mod": Q_mod,
        "temperature": T,
        "go": go,
        "no_go": no_go,
    }
