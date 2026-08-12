# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

import numpy as np

from core.neuro.ecs_regulator import ECSInspiredRegulator, StressMode


def build_time_provider(start: datetime):
    counter = {"i": 0}

    def _provider():
        counter["i"] += 1
        return start + timedelta(seconds=counter["i"])

    return _provider


def prefill_calibration(regulator: ECSInspiredRegulator, scores: list[float]) -> None:
    for s in scores:
        regulator.update_with_realized(y_realized=s, y_pred=0.0)


def test_min_calibration_blocks_trading():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=5,
        calibration_window=8,
        conformal_gate_enabled=True,
    )

    action = regulator.decide_action(0.5)
    assert action == 0
    assert not regulator._last_conformal_ready


def test_conformal_quantile_monotonic_with_worse_residuals():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=1,
        calibration_window=20,
    )

    prefill_calibration(regulator, [0.01] * 10)
    low_q = regulator.get_conformal_threshold()
    prefill_calibration(regulator, [0.5] * 10)
    high_q = regulator.get_conformal_threshold()

    assert high_q >= low_q


def test_prediction_interval_and_gate_block_when_zero_inside():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=3,
        calibration_window=10,
    )
    prefill_calibration(regulator, [0.1, 0.1, 0.1, 0.1])

    interval = regulator.get_prediction_interval(0.05)
    assert interval[0] <= interval[1]
    assert regulator.get_conformal_threshold() >= 0

    action = regulator.decide_action(0.05)
    assert action == 0
    assert not regulator._last_confidence_gate_pass


def test_coverage_matches_target_within_tolerance():
    rng = np.random.default_rng(0)
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=20,
        calibration_window=256,
        alpha=0.1,
    )

    predictions = np.zeros(2000)
    noise = rng.normal(0, 1.0, size=2000)

    for y_real, y_pred in zip(noise, predictions):
        regulator.update_with_realized(y_realized=float(y_real), y_pred=float(y_pred))

    coverage = regulator._coverage_hits / max(regulator._coverage_events, 1)
    assert 0.85 <= coverage <= 0.95


def test_stress_tightening_is_monotonic():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=1,
        calibration_window=10,
        stress_q_multiplier=1.5,
        crisis_q_multiplier=2.0,
    )
    prefill_calibration(regulator, [0.05] * 20)

    regulator.stress_mode = StressMode.NORMAL
    action_normal = regulator.decide_action(0.2)

    regulator.stress_mode = StressMode.ELEVATED
    action_elevated = regulator.decide_action(0.2)

    regulator.stress_mode = StressMode.CRISIS
    action_crisis = regulator.decide_action(0.2)

    assert abs(action_crisis) <= abs(action_elevated) <= abs(action_normal)


def test_hash_chain_breaks_on_tamper():
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=1,
        calibration_window=5,
        time_provider=build_time_provider(base_time),
    )
    prefill_calibration(regulator, [0.1] * 5)
    regulator.decide_action(0.2)
    regulator.decide_action(0.25)

    trace = regulator.get_trace()
    assert len(trace) == 2

    first_event = trace.iloc[0].to_dict()
    tampered = {**first_event, "action": 99}
    canonical = json.dumps(
        {k: tampered[k] for k in tampered if k != "event_hash"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    recomputed_hash = regulator._canonical_json({k: tampered[k] for k in tampered})
    assert (
        tampered["event_hash"]
        != hashlib.sha256((tampered["prev_hash"] + canonical).encode("utf-8")).hexdigest()
    )
    assert recomputed_hash != canonical


def test_schema_stability_and_invariants():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=1,
        calibration_window=5,
    )
    prefill_calibration(regulator, [0.1] * 5)
    regulator.decide_action(0.2)
    regulator.decide_action(-0.25)

    trace = regulator.get_trace()
    keys = set(trace.columns)
    for _, row in trace.iterrows():
        assert set(row.index) == keys
        if not math.isnan(row["conformal_q"]):
            assert row["conformal_q"] >= 0
        if not row["confidence_gate_pass"]:
            assert row["action"] == 0


def test_determinism_with_fixed_time_provider():
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    time_provider = build_time_provider(base_time)
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.01,
        min_calibration=1,
        calibration_window=5,
        seed=42,
        time_provider=time_provider,
    )
    prefill_calibration(regulator, [0.1] * 5)

    actions = [regulator.decide_action(x) for x in [0.2, -0.3, 0.4]]
    trace = regulator.get_trace().to_dict(orient="records")

    regulator.reset()
    regulator._time_provider = build_time_provider(base_time)
    prefill_calibration(regulator, [0.1] * 5)
    actions_repeat = [regulator.decide_action(x) for x in [0.2, -0.3, 0.4]]
    trace_repeat = regulator.get_trace().to_dict(orient="records")

    assert actions == actions_repeat
    assert trace == trace_repeat
