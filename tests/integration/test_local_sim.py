"""Integration smoke-tests for the offline simulation runner."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from domain import SignalAction
from scripts.run_local_sim import SimulationConfig, run_local_sim


def test_run_local_sim_offline_cycle(tmp_path):
    config = SimulationConfig(history_length=180, audit_path=tmp_path / "audit.jsonl")
    result = run_local_sim(config)

    assert isinstance(result.prices, pd.DataFrame)
    assert not result.prices.empty
    assert result.signal.action in SignalAction
    assert result.audit_log_path.parent.exists()

    if result.order is None:
        assert result.risk_check.status == "skipped"
        assert result.execution_report is None
    else:
        assert result.risk_check.status in {"passed", "rejected", "blocked"}
        assert result.execution_report is not None

    summary = result.summary()
    assert summary["signal_action"] == result.signal.action.value
    assert summary["risk"]["status"] == result.risk_check.status
    assert Path(summary["audit_log_path"]).parent.exists()
