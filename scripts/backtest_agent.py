"""Backtest the FHMC agent in a regime-shift environment."""

from __future__ import annotations

import numpy as np

from envs.market_env import RegimeShiftEnv
from rl.core.actor_critic import ActorCriticFHMC
from runtime.thermo_controller import FHMC


def main() -> None:
    fhmc = FHMC.from_yaml("configs/fhmc.yaml")
    env = RegimeShiftEnv(dim_state=128, dim_action=8, T=20_000)
    agent = ActorCriticFHMC(state_dim=128, action_dim=8, fhmc=fhmc)

    state = env.reset()
    action_history: list[float] = []
    latent_history: list[float] = []
    pnl = 0.0
    max_drawdown = 0.0

    for step in range(env.T):
        action = agent.act(state)
        reward, next_state, info = env.step(action)
        pnl += reward
        max_drawdown = min(max_drawdown, pnl - max(pnl, 0))
        agent.learn(state, action, reward, next_state, done=False)
        state = next_state

        action_history.append(float(np.tanh(action).mean()))
        latent_history.append(float(info["latent"]))

        if step % 50 == 0 and step > 0:
            fhmc.update_biomarkers(action_history, latent_history, fs_latents=50)
            fhmc.compute_threat(info["maxdd"], info["volshock"], info["cp"])
            fhmc.compute_orexin(info["exp_ret"], info["novelty"], info["load"])
            fhmc.flipflop_step()

    print({"PnL": pnl, "MaxDD": max_drawdown})


if __name__ == "__main__":
    main()
