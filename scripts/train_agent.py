"""Train the FHMC actor-critic agent in the toy market environment."""

from __future__ import annotations

import argparse

import numpy as np

from envs.market_env import ToyMarketEnv
from rl.core.actor_critic import ActorCriticFHMC
from runtime.thermo_controller import FHMC


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    fhmc = FHMC.from_yaml("configs/fhmc.yaml")
    env = ToyMarketEnv(dim_state=128, dim_action=8)
    agent = ActorCriticFHMC(state_dim=128, action_dim=8, fhmc=fhmc)

    state = env.reset()
    action_history: list[float] = []
    latent_history: list[float] = []

    for step in range(args.steps):
        action = agent.act(state)
        reward, next_state, info = env.step(action)
        agent.learn(state, action, reward, next_state, done=False)
        state = next_state

        action_history.append(float(np.tanh(action).mean()))
        latent_history.append(float(info["latent"]))

        if step % 50 == 0 and step > 0:
            fhmc.update_biomarkers(action_history, latent_history, fs_latents=50)
            fhmc.compute_threat(info["maxdd"], info["volshock"], info["cp"])
            fhmc.compute_orexin(info["exp_ret"], info["novelty"], info["load"])
            fhmc.flipflop_step()


if __name__ == "__main__":
    main()
