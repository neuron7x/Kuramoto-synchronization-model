from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.request import urlopen

import numpy as np

from runtime.metrics import gauge_set, init_metrics_server
from runtime.misanthropic_agent import MisanthropicAgent, load_agent_config


def test_metrics_and_logging(tmp_path) -> None:
    init_metrics_server(9201)
    time.sleep(0.1)
    gauge_set("tradepulse_coverage", 0.9)
    resp = urlopen("http://localhost:9201/metrics")
    body = resp.read().decode("utf-8")
    assert "tradepulse_coverage" in body

    cfg = load_agent_config(Path(__file__).resolve().parents[2] / "configs" / "agent" / "misanthropic.yaml")
    cfg.batch_size = 2
    agent = MisanthropicAgent(cfg, seed=2, log_dir=tmp_path)
    obs = np.zeros(cfg.arch.state_dim, dtype=np.float32)
    agent._update_replay(obs, 1, 0.0, obs, False)
    agent._update_replay(obs, 1, 0.0, obs, False)
    agent.step(obs, reward=0.1, done=False)
    agent.close()
    log_file = next(tmp_path.glob("run_*.jsonl"))
    with log_file.open() as fh:
        data = json.loads(fh.readline())
    assert {"ts", "action", "coverage", "commit"}.issubset(data.keys())
