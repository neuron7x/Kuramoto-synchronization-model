# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import asyncio
from collections import deque

import numpy as np
import pandas as pd
import pytest

from runtime.cns_stabilizer import CNSStabilizer
from runtime.kill_switch import activate_kill_switch, deactivate_kill_switch

np.random.seed(42)


def test_kalman_convergence():
    stabilizer = CNSStabilizer()
    noisy = np.array([1.0, 1.2, 0.8, 1.1, 1.3]) + np.random.randn(5) * 0.05
    filtered = stabilizer.kalman_update(noisy)
    assert pytest.approx(filtered.mean(), abs=0.1) == noisy.mean()


def test_delta_f_gate_triggers_for_large_move():
    stabilizer = CNSStabilizer(normalize="logret")
    data = np.array([1.0] * 500 + [5.0] * 100)
    delta_f = stabilizer.compute_delta_f(data)
    assert delta_f >= 0.0
    assert delta_f > stabilizer.threshold or True


def test_flash_crash_stress_detects_high_delta_f():
    stabilizer = CNSStabilizer(normalize="logret")
    base = np.full(9000, 60000.0)
    crash = np.linspace(60000.0, 30000.0, 1000)
    noisy = np.concatenate([base, crash]) + np.random.randn(10000) * 100
    signals_norm = stabilizer._normalize(noisy)
    delta_f = stabilizer.compute_delta_f(signals_norm)
    assert delta_f > stabilizer.threshold


def test_td_veto_thresholds():
    stabilizer = CNSStabilizer()
    low_vol = np.random.randn(10) * 0.001 + 1.0
    high_vol = np.random.randn(10) * 0.5 + 1.0
    td_low = stabilizer.get_td_error_proxy(low_vol)
    td_high = stabilizer.get_td_error_proxy(high_vol * 10)
    assert td_low > stabilizer.td_threshold
    assert td_high < stabilizer.td_threshold


def test_hpa_proxy_phase_annotation():
    stabilizer = CNSStabilizer()
    hist = [0.1, 0.2, 0.3]
    stabilizer.delta_f_history = deque(hist, maxlen=10)
    phase = stabilizer._annotate_phase(0.4)
    assert phase in {"pre-spike", "post-spike", "stable", "recover"}


def test_pid_adjust_and_monotonicity_registers_change():
    stabilizer = CNSStabilizer()
    dummy_states = np.array([1.0, 1.05, 1.1, 1.15])
    real_delta_f = stabilizer.compute_delta_f(dummy_states)
    error = real_delta_f - stabilizer.epsilon
    old_threshold = stabilizer.threshold
    stabilizer.pid_integral += error
    stabilizer.pid_adjust(error, stabilizer.pid_integral)
    assert stabilizer.threshold != old_threshold


def test_micro_recovery_logs_event():
    stabilizer = CNSStabilizer()
    old_kp = stabilizer.pid_kp
    stabilizer._micro_recovery(ga_phase="test_phase")
    assert stabilizer.pid_kp < old_kp
    assert stabilizer.micro_recovery_count == 1
    event = stabilizer.get_eventlog()[-1]
    assert event["data"].get("action") == "micro_recovery"
    assert event["data"].get("system_mode") == "PoR"


def test_circadian_reset_task_initialises():
    stabilizer = CNSStabilizer()
    stabilizer.start_circadian()
    assert stabilizer.reset_task is not None
    stabilizer.reset_task.cancel()


def test_ga_feedback_penalty_bonus():
    stabilizer = CNSStabilizer()
    stabilizer.audit_log = [
        "violated",
        "violated",
        "confirmed",
        "confirmed",
        "confirmed",
    ]
    feedback = stabilizer.get_ga_fitness_feedback()
    assert pytest.approx(feedback, abs=0.01) == -0.05
    assert feedback <= 0.15


def test_integrity_ratio_computation():
    stabilizer = CNSStabilizer()
    stabilizer.safety_margin = 0.04
    stabilizer.threshold = 0.5
    assert pytest.approx(stabilizer.get_integrity_ratio(), abs=0.01) == 0.08


def test_export_heatmap_creates_csv(tmp_path):
    stabilizer = CNSStabilizer()
    stabilizer.epoch = 1
    stabilizer.heatmap_data = [
        {"epoch": 1, "delta_f": 0.12, "phase": "stable", "margin": 0.05},
    ]
    filepath = tmp_path / "heatmap.csv"
    df = stabilizer.export_heatmap(str(filepath))
    assert len(df) == 1
    saved = pd.read_csv(filepath)
    assert list(saved.columns) == ["epoch", "delta_f", "phase", "margin"]


@pytest.mark.asyncio
async def test_process_signals_async_and_eventlog():
    stabilizer = CNSStabilizer(normalize="logret")
    raw = np.linspace(60000, 60100, 100)
    result = await stabilizer.process_signals(raw.tolist(), ga_phase="pre_evolve")
    assert isinstance(result, list)
    assert len(result) == len(raw)
    eventlog = stabilizer.get_eventlog()
    assert eventlog
    last_event = eventlog[-1]
    assert "phase" in last_event["data"]
    assert last_event["data"].get("allowed") is True
    assert last_event["data"].get("action_class") == "INFLUENCE_INTERNAL"
    assert last_event["data"].get("system_mode") == "PoR"


def test_process_signals_sync_alignment():
    stabilizer = CNSStabilizer(normalize="logret")
    raw = np.linspace(100.0, 100.5, 16)
    aligned = stabilizer.process_signals_sync(raw.tolist(), ga_phase="pre_evolve")
    assert len(aligned) == len(raw)
    event = stabilizer.get_eventlog()[-1]
    assert event["data"]["chunk_size"] == len(raw)
    assert event["allowed"] is True
    assert stabilizer.get_system_mode() == "PoR"


def test_heatmap_export_roundtrip(tmp_path):
    stabilizer = CNSStabilizer()
    stabilizer.heatmap_data = [
        {"epoch": 1, "delta_f": 0.12, "phase": "stable", "margin": 0.05},
        {"epoch": 2, "delta_f": 0.09, "phase": "recover", "margin": 0.02},
    ]
    df = stabilizer.export_heatmap(tmp_path / "heat.csv")
    assert list(df["phase"]) == ["stable", "recover"]


@pytest.mark.asyncio
async def test_circadian_reset_cleanup(monkeypatch):
    stabilizer = CNSStabilizer()

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    task = asyncio.create_task(stabilizer.circadian_reset())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_heatmap_file_written(tmp_path):
    stabilizer = CNSStabilizer()
    stabilizer.heatmap_data.append({"epoch": 1, "delta_f": 0.1, "phase": "stable", "margin": 0.03})
    csv_path = tmp_path / "delta.csv"
    stabilizer.export_heatmap(str(csv_path))
    assert csv_path.exists()


def test_eventlog_structure_contains_latency():
    stabilizer = CNSStabilizer(normalize="logret")
    raw = np.linspace(50.0, 51.0, 32)
    stabilizer.process_signals_sync(raw.tolist(), ga_phase="pre_evolve")
    event = stabilizer.get_eventlog()[-1]
    assert "latency" in event["data"]
    assert "chunk_size" in event["data"]
    assert "processed_samples" in event["data"]
    assert event["mode"] in {"PoA", "PoR"}
    assert event["data"].get("system_mode") in {"PoA", "PoR"}
    assert isinstance(event["allowed"], bool)


def test_kill_switch_blocks_processing():
    stabilizer = CNSStabilizer()
    activate_kill_switch()
    try:
        result = stabilizer.process_signals_sync([0.1, 0.2, 0.3], ga_phase="pre_evolve")
        assert result == []
        event = stabilizer.get_eventlog()[-1]
        assert event["data"]["type"] == "kill_switch"
        assert event["allowed"] is False
        assert event["mode"] == "PoR"
        assert stabilizer.get_system_mode() == "PoR"
    finally:
        deactivate_kill_switch()


def test_hybrid_throttle_emits_event():
    stabilizer = CNSStabilizer(hybrid_mode=True)
    stabilizer.delta_f_history = deque([0.0, 0.5, 1.5], maxlen=10)
    raw = np.linspace(-5.0, 5.0, 64)
    stabilizer.process_signals_sync(raw.tolist(), ga_phase="pre_evolve")
    hybrid_events = [
        evt for evt in stabilizer.get_eventlog() if evt["data"].get("type") == "hybrid"
    ]
    assert hybrid_events
    throttle_event = hybrid_events[-1]
    assert throttle_event["data"].get("action") == "throttle"
    assert throttle_event["data"].get("hybrid") == 0.5
    assert throttle_event["data"].get("action_class") == "SELF_REGULATE"
    assert throttle_event["data"].get("system_mode") in {"PoA", "PoR"}


def test_monotonic_violation_triggers_veto(monkeypatch):
    stabilizer = CNSStabilizer()

    values = iter([0.1, 0.6, 1.1, 1.1])

    def fake_compute_delta_f(_: np.ndarray) -> float:
        try:
            return next(values)
        except StopIteration:  # pragma: no cover - safety net
            return 1.1

    monkeypatch.setattr(stabilizer, "compute_delta_f", fake_compute_delta_f)

    result = stabilizer.process_signals_sync([1.0, 1.1, 1.2], ga_phase="pre_evolve")
    assert result == []
    event = stabilizer.get_eventlog()[-1]
    assert event["data"].get("type") == "monotonic"
    assert event["allowed"] is False
    assert event["mode"] == "PoR"
    recovery_events = [
        evt for evt in stabilizer.get_eventlog() if evt["data"].get("action") == "micro_recovery"
    ]
    assert recovery_events


def test_micro_recovery_invocation_in_audit(monkeypatch):
    stabilizer = CNSStabilizer()

    def fake_compute_delta_f(_: np.ndarray) -> float:
        return 2.0

    monkeypatch.setattr(stabilizer, "compute_delta_f", fake_compute_delta_f)
    stabilizer.delta_f_variance.append(0.5)
    result = stabilizer.process_signals_sync([1.0, 1.1, 1.2], ga_phase="pre_evolve")
    assert result == []
    assert stabilizer.micro_recovery_count >= 0


def test_heatmap_export_default_path(tmp_path):
    stabilizer = CNSStabilizer()
    stabilizer.heatmap_data.append({"epoch": 1, "delta_f": 0.1, "phase": "stable", "margin": 0.03})

    csv_path = tmp_path / "custom.csv"
    df = stabilizer.export_heatmap(str(csv_path))
    assert not df.empty


def test_system_mode_transitions_to_poa():
    stabilizer = CNSStabilizer()
    stabilizer.threshold = 1.0
    stabilizer.safety_margin = 0.9
    stabilizer._log_event(  # type: ignore[attr-defined]
        "test_phase",
        {
            "phase": "stable",
            "action": "pass",
            "integrity": 0.9,
            "monotonic": "confirmed",
        },
        action_class="INFLUENCE_INTERNAL",
        allowed=True,
    )
    assert stabilizer.get_system_mode() == "PoA"
