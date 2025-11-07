from __future__ import annotations

import numpy as np
import time
from pathlib import Path

from runtime.misanthropic_agent import MisanthropicAgent, load_agent_config


def test_step_latency_under_budget(tmp_path) -> None:
    cfg = load_agent_config(Path(__file__).resolve().parents[2] / "configs" / "agent" / "misanthropic.yaml")
    cfg.batch_size = 1
    agent = MisanthropicAgent(cfg, seed=3, log_dir=tmp_path)
    agent.repose = lambda: None  # type: ignore[assignment]
    obs = np.zeros(cfg.arch.state_dim, dtype=np.float32)
    reward = 0.0
    durations = []
    for _ in range(1000):
        start = time.perf_counter()
        agent.step(obs, reward, done=False)
        durations.append((time.perf_counter() - start) * 1000)
    p95 = np.percentile(durations, 95)
    assert p95 <= 10.0
