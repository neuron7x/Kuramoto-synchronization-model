"""Evaluation entry-point for the MisanthropicAgent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from omegaconf import OmegaConf

from core.env.hawkes_env import HawkesConfig, HawkesEnv
from core.env.nhp_env import NHPConfig, NHPEnv
from runtime.bootstrap import set_determinism
from runtime.misanthropic_agent import MisanthropicAgent, load_agent_config


def _load_env(name: str, cfg_path: Path) -> object:
    cfg = OmegaConf.load(cfg_path)
    data = OmegaConf.to_container(cfg, resolve=True)
    if name == "hawkes":
        return HawkesEnv(HawkesConfig(**data))
    if name == "nhp":
        return NHPEnv(NHPConfig(**data))
    raise ValueError(f"Unknown environment {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/train.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--episodes", type=int, default=5)
    args = parser.parse_args()

    cfg = OmegaConf.load(args.config)
    cfg_dict = OmegaConf.to_container(cfg, resolve=True)
    seed = int(cfg_dict.get("seed", 42))
    set_determinism(seed)

    agent_cfg = load_agent_config(Path(cfg_dict["agent_config"]))
    env = _load_env(cfg_dict.get("env", "hawkes"), Path(cfg_dict.get("env_config", "configs/env/hawkes.yaml")))
    agent = MisanthropicAgent(agent_cfg, seed=seed, log_dir=Path(cfg_dict.get("log_dir", "logs")))
    state_dict = torch.load(args.checkpoint, map_location="cpu")
    agent.online.load_state_dict(state_dict)
    agent.target.load_state_dict(state_dict)
    agent.set_training(False)

    pnl_scores = []
    sharpe_samples = []
    coverage_samples = []
    ood_samples = []

    for _ in range(args.episodes):
        obs_dict = env.reset()
        obs = obs_dict["state"]
        reward = 0.0
        done = False
        pnl = 0.0
        rewards = []
        while not done:
            action = agent.step(obs, reward, done)
            next_obs, reward, done = env.step(action)
            pnl += reward
            rewards.append(reward)
            obs = next_obs["state"]
        agent.step(obs, reward, True)
        pnl_scores.append(pnl)
        if rewards:
            sharpe = np.mean(rewards) / (np.std(rewards) + 1e-6)
            sharpe_samples.append(sharpe)
        coverage_samples.extend(agent.coverage_history)
        ood_samples.append(float(np.mean(agent.coverage_history) if agent.coverage_history else 0.0))

    agent.close()
    dummy_input = torch.zeros(1, agent_cfg.arch.state_dim)
    onnx_path = Path(args.checkpoint).with_suffix(".onnx")
    try:
        torch.onnx.export(agent.online, dummy_input, onnx_path, opset_version=11)
    except Exception:
        onnx_path.write_text("onnx export skipped")

    cvar_est = float(np.percentile(pnl_scores, 5))
    result = {
        "avg_pnl": float(np.mean(pnl_scores)),
        "sharpe": float(np.mean(sharpe_samples) if sharpe_samples else 0.0),
        "cvar_95": cvar_est,
        "coverage": float(np.mean(coverage_samples) if coverage_samples else 1.0),
        "ood_score": float(np.mean(ood_samples) if ood_samples else 0.0),
        "onnx": str(onnx_path),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
