from __future__ import annotations

import torch

from pathlib import Path

import numpy as np

from runtime.misanthropic_agent import MisanthropicAgent, load_agent_config
from core.risk.cvar import cvar_from_quantiles


class _ConstantNet(torch.nn.Module):
    def __init__(self, cfg) -> None:
        super().__init__()
        self.linear = torch.nn.Linear(cfg.arch.state_dim, cfg.arch.action_dim * cfg.arch.quantiles)
        torch.nn.init.constant_(self.linear.weight, -0.01)
        torch.nn.init.constant_(self.linear.bias, -0.2)
        self.action_dim = cfg.arch.action_dim
        self.quantiles = cfg.arch.quantiles

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        out = self.linear(x)
        return out.view(-1, self.action_dim, self.quantiles)


def test_lambda_updates_and_tail_loss(tmp_path) -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_agent_config(root / "configs" / "agent" / "misanthropic.yaml")
    cfg.batch_size = 2
    agent = MisanthropicAgent(cfg, seed=1, log_dir=tmp_path)
    obs = np.ones(cfg.arch.state_dim, dtype=np.float32)
    for _ in range(4):
        agent._update_replay(obs, 1, -1.0, obs, False)
    net = _ConstantNet(cfg)
    agent.online = net
    agent.target = _ConstantNet(cfg)
    agent.target.load_state_dict(agent.online.state_dict())
    agent.optimizer = torch.optim.Adam(agent.online.parameters(), lr=1e-3)
    agent.tacl.approve_change = lambda *args, **kwargs: True  # type: ignore[assignment]
    lambda_before = agent.lambda_cvar
    agent.repose()
    assert agent.lambda_cvar > lambda_before
    q = torch.linspace(-0.3, 0.1, steps=cfg.arch.quantiles).unsqueeze(0)
    cvar = cvar_from_quantiles(q, cfg.risk.alpha_cvar)
    loss_per_sample = torch.abs(q).mean(dim=1, keepdim=True)
    violation = torch.relu(torch.tensor(cfg.risk.c_cvar) - cvar).view(-1, 1)
    lagrangian_loss = (loss_per_sample + agent.lambda_cvar * violation).mean()
    hard_loss = (loss_per_sample + torch.where(violation > 0, torch.ones_like(violation), torch.zeros_like(violation))).mean()
    assert lagrangian_loss < hard_loss
