# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import time
from pathlib import Path

import numpy as np

from geosync.nlca_core import (
    NLCA,
    FiniteStateMachine,
    L2Collector,
    MarketRecorder,
    StateSimulator,
)


def _fake_tick(ts: float):
    return {
        "timestamp": ts,
        "p_a1": 100.0 + np.random.normal(0, 0.01),
        "p_b1": 99.99 + np.random.normal(0, 0.01),
        "q_a": np.abs(np.random.normal(1000, 50, size=10)).tolist(),
        "q_b": np.abs(np.random.normal(1000, 50, size=10)).tolist(),
        "events": [
            {"type": "add", "side": "ask", "volume": 50, "price_change": False},
            {"type": "trade", "side": "bid", "volume": 30, "price_change": True},
        ],
        "messages": [1] * np.random.randint(50, 80),
        "trades": [{"profit": 0.0, "slippage": 0.0}] * np.random.randint(1, 5),
        "delta_P": np.random.normal(0, 0.02),
        "Q": np.random.normal(0, 1000),
    }


def _build_nlca(delay_budget=0.1, exposure_limit=100000):
    context = {
        "S_median": 0.01,
        "D_median": 1000,
        "SVI_80th": 0.0001,
        "OTR_80th": 10,
        "BRHL_80th": 5,
    }
    recorder = MarketRecorder(enabled=False)
    return NLCA(
        context_profile=context,
        delay_budget=delay_budget,
        exposure_limit=exposure_limit,
        recorder=recorder,
    )


def test_step_core_contract_fields_exist():
    nlca = _build_nlca()
    base_ts = time.time()
    tick = _fake_tick(base_ts)

    out = nlca.step(tick)

    assert "state" in out
    assert "action" in out
    assert "metrics" in out
    assert "priority_paths" in out
    for key in ["S", "D", "OFI", "lambda", "SVI", "BRHL", "OTR"]:
        assert key in out["metrics"]


def test_latency_budget_enforced_and_sets_stop():
    nlca = _build_nlca(delay_budget=0.0)
    base_ts = time.time()
    tick = _fake_tick(base_ts)

    out = nlca.step(tick)

    assert out["action"] == "STOP_LATENCY"
    assert nlca.fsm.get_state() == "S⊘"


def test_exposure_firewall_blocks_and_forces_stop():
    nlca = _build_nlca(exposure_limit=500.0)

    ok_first = nlca.risk_firewall(400.0)
    ok_second = nlca.risk_firewall(200.0)

    assert ok_first is True
    assert ok_second is False
    assert nlca.fsm.get_state() == "S⊘"


def test_state_simulator_runs():
    nlca = _build_nlca()
    base_ts = time.time()
    ticks = [_fake_tick(base_ts + i * 0.01) for i in range(5)]

    sim = StateSimulator(nlca)
    summary = sim.simulate(ticks, num_steps=10)

    assert "transitions" in summary
    assert "results" in summary
    assert "final_state" in summary
    assert isinstance(summary["results"], list)
    assert len(summary["results"]) == 10


def test_market_recorder_flush_persists_dataset(tmp_path):
    dataset_dir = tmp_path / "market_ds"
    recorder = MarketRecorder(dataset_path=dataset_dir, enabled=True, flush_every=1)

    tick = {"timestamp": time.time()}
    decision = {"state": "S0", "action": "HOLD"}
    metrics = {
        "S": 0.1,
        "D": 1.0,
        "OFI": 0.0,
        "lambda": 0.0,
        "SVI": 0.0,
        "BRHL": 0.0,
        "OTR": 0.0,
    }

    recorder.record_tick(tick, decision, metrics)
    recorder.flush()

    assert recorder.buffer == []
    parquet_files = list(Path(dataset_dir).rglob("*.parquet"))
    assert parquet_files, "Expected at least one parquet file to be written"


def test_fsm_respects_refractory(monkeypatch):
    # Timestamps for time.time() calls (6 total):
    # 1. FSM init: sets last_transition_time (0.0)
    # 2. First transition: check passes (2.0 - 0.0 = 2.0 >= 1.0)
    # 3. First transition: logging call (2.0)
    # 4. Second transition: check fails (2.5 - 2.0 = 0.5 < 1.0 refractory)
    # 5. Forced transition: check passes (force=True)
    # 6. Forced transition: logging call (3.0)
    timestamps = [0.0, 2.0, 2.0, 2.5, 3.0, 3.0]

    def fake_time():
        if timestamps:
            return timestamps.pop(0)
        return 100.0  # Return a large value if we run out

    # Patch time.time in the nlca_core module's namespace
    monkeypatch.setattr("geosync.nlca_core.time.time", fake_time)

    fsm = FiniteStateMachine(refractory_period=1.0)

    first = fsm.transition("S1", "first")
    second = fsm.transition("S2", "too_soon")
    forced = fsm.transition("S3", "override", force=True)

    assert first is True
    assert second is False
    assert forced is True
    assert fsm.get_state() == "S3"
    assert len(fsm.get_logs()) == 2  # only successful transitions are logged


def test_l2collector_warns_on_desync(caplog, monkeypatch):
    collector = L2Collector(sync_tolerance=0.1)
    collector.last_ts = 0.0
    monkeypatch.setattr(time, "time", lambda: 1.0)

    with caplog.at_level("WARNING"):
        payload = collector.collect({"foo": "bar"})

    assert payload == {"foo": "bar"}
    assert any("Timestamp desync" in rec.message for rec in caplog.records)


def test_step_rejects_invalid_depth_vectors():
    nlca = _build_nlca()
    tick = _fake_tick(time.time())
    tick["q_a"] = ["bad", "data"]

    result = nlca.step(tick)

    assert result["action"] == "STOP_INVALID_DATA"
    assert result["state"] == "S⊘"
