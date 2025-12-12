from __future__ import annotations

import numpy as np

from tradepulse.core.neuro.nak import NaKAdapter, NaKController


def test_nak_controller_update_returns_reward_and_log() -> None:
    ctrl = NaKController(1)
    reward, log = ctrl.update(p=0.01, v=0.02, drawdown=-0.01)
    assert isinstance(log, dict)
    assert "r_final" in log
    assert np.isfinite(reward)


def test_nak_adapter_combines_gate_and_controller() -> None:
    adapter = NaKAdapter(strategy_id=7)
    output = adapter.step(p=0.01, v=0.02, drawdown=-0.01)
    assert 0.0 <= output.gate <= 1.0
    assert 0.0 <= output.effective_size <= 1.0
    assert "shaped_reward" in output.controller_log
