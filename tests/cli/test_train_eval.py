from __future__ import annotations

import json
import sys
from pathlib import Path

from cli import train_agent, eval_agent


def _write_config(path: Path, log_dir: Path) -> None:
    config = {
        "seed": 0,
        "episodes": 1,
        "log_dir": str(log_dir),
        "prometheus": {"enabled": False, "port": 9300},
        "env": "hawkes",
        "agent_config": str(Path(__file__).resolve().parents[2] / "configs" / "agent" / "misanthropic.yaml"),
        "env_config": str(Path(__file__).resolve().parents[2] / "configs" / "env" / "hawkes.yaml"),
    }
    with path.open("w") as fh:
        json.dump(config, fh)


def test_train_and_eval_cli(tmp_path, capsys) -> None:
    train_cfg = tmp_path / "train.json"
    _write_config(train_cfg, tmp_path)

    sys.argv = ["train_agent", "--config", str(train_cfg), "--log-dir", str(tmp_path)]
    train_agent.main()
    train_out = json.loads(capsys.readouterr().out.strip())
    checkpoint = Path(train_out["checkpoint"])
    assert checkpoint.exists()

    sys.argv = ["eval_agent", "--config", str(train_cfg), "--checkpoint", str(checkpoint), "--episodes", "1"]
    eval_agent.main()
    eval_out = json.loads(capsys.readouterr().out.strip())
    assert "avg_pnl" in eval_out
    assert Path(eval_out["onnx"]).exists()
