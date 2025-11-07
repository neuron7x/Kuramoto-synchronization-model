"""Training entry-point for the MisanthropicAgent."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict

import numpy as np
import torch
from omegaconf import OmegaConf

from core.env.hawkes_env import HawkesConfig, HawkesEnv
from core.env.nhp_env import NHPConfig, NHPEnv
from runtime.bootstrap import set_determinism
from runtime.metrics import init_metrics_server
from runtime.misanthropic_agent import MisanthropicAgent, load_agent_config


def _load_env(name: str, cfg_path: Path) -> tuple[object, Dict[str, float]]:
    cfg = OmegaConf.load(cfg_path)
    data = OmegaConf.to_container(cfg, resolve=True)
    if name == "hawkes":
        env_cfg = HawkesConfig(**data)
        env = HawkesEnv(env_cfg)
    elif name == "nhp":
        env_cfg = NHPConfig(**data)
        env = NHPEnv(env_cfg)
    else:
        raise ValueError(f"Unknown environment {name}")
    return env, data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/train.yaml")
    parser.add_argument("--env-config", default="configs/env/hawkes.yaml")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-dir", default="logs")
    args = parser.parse_args()

    train_cfg = OmegaConf.load(args.config)
    train_dict = OmegaConf.to_container(train_cfg, resolve=True)
    seed = int(train_dict.get("seed", args.seed))
    set_determinism(seed)

    log_dir = Path(train_dict.get("log_dir", args.log_dir))
    agent_cfg = load_agent_config(Path(train_dict["agent_config"]))
    env_name = train_dict.get("env", "hawkes")
    env, env_params = _load_env(env_name, Path(train_dict.get("env_config", args.env_config)))

    if train_dict.get("prometheus", {}).get("enabled", True):
        init_metrics_server(int(train_dict.get("prometheus", {}).get("port", 9200)))

    agent = MisanthropicAgent(agent_cfg, seed=seed, log_dir=log_dir)
    episodes = int(train_dict.get("episodes", 10))
    latency_samples = []
    coverage_samples = []
    total_rewards = []

    for ep in range(episodes):
        obs_dict = env.reset()
        obs = obs_dict["state"]
        reward = 0.0
        done = False
        pnl = 0.0
        while not done:
            tic = time.perf_counter()
            action = agent.step(obs, reward, done)
            latency_samples.append((time.perf_counter() - tic) * 1000)
            next_obs, reward, done = env.step(action)
            pnl += reward
            obs = next_obs["state"]
        agent.step(obs, reward, True)
        coverage_samples.extend(agent.coverage_history)
        total_rewards.append(pnl)

    agent.close()
    checkpoint_path = log_dir / "checkpoint.pt"
    torch.save(agent.online.state_dict(), checkpoint_path)
    result = {
        "episodes": episodes,
        "avg_pnl": float(np.mean(total_rewards)),
        "coverage_mean": float(np.mean(coverage_samples) if coverage_samples else 1.0),
        "latency_p95": float(np.percentile(latency_samples, 95)) if latency_samples else 0.0,
        "env": env_name,
        "env_params": env_params,
        "checkpoint": str(checkpoint_path),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    import time
    import torch

    main()
