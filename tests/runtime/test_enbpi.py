from __future__ import annotations

import numpy as np

from pathlib import Path

from runtime.misanthropic_agent import MisanthropicAgent, load_agent_config


def test_enbpi_hold_trigger(tmp_path) -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_agent_config(root / "configs" / "agent" / "misanthropic.yaml")
    cfg.batch_size = 2
    agent = MisanthropicAgent(cfg, seed=7, log_dir=tmp_path)
    obs = np.ones(cfg.arch.state_dim, dtype=np.float32)
    for _ in range(4):
        agent._update_replay(obs, 1, 0.0, obs, False)
    agent._compute_coverage = lambda residual: (0.8, 0.1)  # type: ignore[assignment]
    action = None
    for _ in range(cfg.enbpi.breach_patience + 1):
        action = agent.step(obs, reward=5.0, done=False)
    assert action == 1
    assert agent.repose_calls >= 3
