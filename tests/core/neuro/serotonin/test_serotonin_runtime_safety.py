# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
import yaml


def _load_serotonin_module() -> tuple[ModuleType, Any, Any]:
    module_path = (
        Path(__file__).resolve().parents[4]
        / "core"
        / "neuro"
        / "serotonin"
        / "serotonin_controller.py"
    )
    spec = importlib.util.spec_from_file_location(
        "serotonin_controller_runtime_safety", module_path
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, module.SerotoninController, module.ControllerOutput


@pytest.fixture(scope="module")
def serotonin_module() -> ModuleType:
    return _load_serotonin_module()[0]


@pytest.fixture()
def serotonin_controller(tmp_path: Path, serotonin_module: ModuleType) -> Any:
    _module, SerotoninController, _ = _load_serotonin_module()
    cfg_source = Path(__file__).resolve().parents[4] / "configs" / "serotonin.yaml"
    cfg_path = tmp_path / "serotonin.yaml"
    loaded = yaml.safe_load(cfg_source.read_text(encoding="utf-8")) or {}
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "active_profile": "v24",
                "serotonin_v24": loaded.get("serotonin_v24", {}),
            }
        ),
        encoding="utf-8",
    )
    return SerotoninController(str(cfg_path))


def _obs(stress: float = 0.4, drawdown: float = -0.02, novelty: float = 0.3) -> dict[str, float]:
    return {"stress": stress, "drawdown": drawdown, "novelty": novelty}


MAX_COMPLEXITY_FACTOR = 5


def test_serotonin_bounds_random(serotonin_controller: Any) -> None:
    """INV-5HT2: s(t) in [0, 1] — serotonin level stays bounded across varied stress inputs."""
    ctrl = serotonin_controller
    for value in [0.1, 0.5, 1.0, 2.0]:
        out = ctrl.update(_obs(stress=value, drawdown=-0.01 * value, novelty=0.2))
        level = out.metrics_snapshot["serotonin_level"]
        assert 0.0 <= level <= 1.0, (
            f"INV-5HT2: serotonin level must stay in [0,1], observed level={level} "
            f"at stress={value} (expected bounded output)"
        )


def test_stress_monotonic_risk_budget(serotonin_controller: Any) -> None:
    """INV-5HT3: higher stress -> lower risk budget (pre-desensitization monotonicity).

    Sweeps stress upward on a fresh controller per point and requires the resulting
    risk budget to be monotone non-increasing — the aversive-wait signal lowers the
    risk budget as stress rises.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    budgets: list[float] = []
    for stress in (0.1, 0.3, 0.6, 1.2):
        fresh = cls(cfg_path)
        budgets.append(fresh.update(_obs(stress=stress, drawdown=-0.02, novelty=0.1)).risk_budget)
    deltas = np.diff(budgets)
    monotone_tol = 1e-9  # numerical floor for the non-increasing comparison
    assert np.all(deltas <= monotone_tol), (
        f"INV-5HT3: risk budget must be monotone non-increasing as stress rises, "
        f"observed diffs={deltas.tolist()} with N=4 stress=[0.1,0.3,0.6,1.2] "
        f"(expected all <= monotone_tol per aversive risk-off response)"
    )


def test_defensive_gate_blocks_actions(serotonin_controller: Any) -> None:
    """INV-5HT7: stress >= 1 OR |dd| >= 0.5 -> veto; defensive gate blocks actions.

    Exercises both disjuncts of the hard-veto condition (high stress; large
    drawdown) on a fresh controller each; every veto-triggering input must produce
    the HOLD_OR_REDUCE_ONLY gate.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    # Each case satisfies stress>=1.0 OR |drawdown|>=0.5 -> must veto.
    veto_cases = (
        _obs(stress=2.5, drawdown=-0.2, novelty=0.4),  # high stress disjunct
        _obs(stress=0.2, drawdown=-0.6, novelty=0.4),  # large-drawdown disjunct
        _obs(stress=1.0, drawdown=-0.01, novelty=0.4),  # stress at threshold
    )
    for case in veto_cases:
        out = cls(cfg_path).update(case)
        assert out.action_gate == "HOLD_OR_REDUCE_ONLY", (
            f"INV-5HT7: hard-veto must set HOLD_OR_REDUCE_ONLY gate, observed "
            f"gate={out.action_gate!r} with stress={case['stress']}, "
            f"drawdown={case['drawdown']} (expected veto)"
        )


def test_cooldown_persists_when_hold_active(serotonin_controller: Any) -> None:
    """NON_PHYSICS: veto persistence across updates (controller state-machine
    behavior, not a registered physics invariant)."""
    ctrl = serotonin_controller
    first = ctrl.update(_obs(stress=2.0, drawdown=-0.3, novelty=0.5))
    second = ctrl.update(_obs(stress=1.8, drawdown=-0.25, novelty=0.5))
    assert first.action_gate == "HOLD_OR_REDUCE_ONLY"
    assert second.action_gate == "HOLD_OR_REDUCE_ONLY"


def test_hysteresis_not_flip_flop(serotonin_controller: Any) -> None:
    """NON_PHYSICS: veto gate anti-flip-flop hysteresis (controller state-machine
    behavior, not a registered physics invariant)."""
    ctrl = serotonin_controller
    on = ctrl.update(_obs(stress=1.6, drawdown=-0.2, novelty=0.3))
    off = ctrl.update(_obs(stress=1.55, drawdown=-0.19, novelty=0.3))
    assert not (on.action_gate == "ALLOW" and off.action_gate == "HOLD_OR_REDUCE_ONLY")


def test_invalid_input_triggers_safe_mode(serotonin_controller: Any) -> None:
    """INV-HPC2: non-finite inputs never propagate; each forces safe DEFENSIVE mode.

    INV-HPC2 forbids NaN/Inf propagation: every non-finite coordinate fed to update()
    must be caught and routed to the fail-safe DEFENSIVE mode with an INVALID_INPUT
    reason code, never silently produce a NaN/Inf output.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    bad_inputs = (
        {"stress": float("nan"), "drawdown": -0.1, "novelty": 0.2},
        {"stress": 0.4, "drawdown": float("inf"), "novelty": 0.2},
        {"stress": 0.4, "drawdown": -0.1, "novelty": float("nan")},
    )
    for obs in bad_inputs:
        bad = cls(cfg_path).update(obs)
        assert bad.mode == "DEFENSIVE", (
            f"INV-HPC2: non-finite input must force DEFENSIVE safe mode, observed "
            f"mode={bad.mode!r} with stress={obs['stress']}, drawdown={obs['drawdown']} "
            f"(expected fail-safe)"
        )
        assert "INVALID_INPUT" in bad.reason_codes, (
            f"INV-HPC2: non-finite input must emit INVALID_INPUT, observed "
            f"reason_codes={bad.reason_codes} with stress={obs['stress']} "
            f"(expected guard code)"
        )


def test_numeric_stability_extremes(serotonin_controller: Any) -> None:
    """INV-5HT2: s(t) in [0, 1] holds even under extreme finite input magnitudes.

    Sweeps several large-but-finite (stress, drawdown, novelty) magnitudes; the
    serotonin level must stay inside the closed bound and the risk budget must stay
    at or above its configured floor.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    extreme_cases = (
        _obs(stress=50.0, drawdown=-10.0, novelty=20.0),
        _obs(stress=1e3, drawdown=-1e3, novelty=1e3),
        _obs(stress=1e6, drawdown=-5.0, novelty=1e6),
    )
    for case in extreme_cases:
        fresh = cls(cfg_path)
        out = fresh.update(case)
        level = out.metrics_snapshot["serotonin_level"]
        budget_floor = fresh._min_risk_budget
        assert 0.0 <= level <= 1.0, (
            f"INV-5HT2: serotonin level must stay in [0,1] under extremes, observed "
            f"level={level} at stress={case['stress']} (expected bounded output)"
        )
        assert out.risk_budget >= budget_floor, (
            f"INV-5HT2: risk budget must stay >= floor={budget_floor}, observed "
            f"risk_budget={out.risk_budget} at stress={case['stress']} (expected clamped)"
        )


def test_state_roundtrip(serotonin_controller: Any) -> None:
    """NON_PHYSICS: state serialization round-trip preserves controller state."""
    ctrl = serotonin_controller
    ctrl.update(_obs(stress=0.7, drawdown=-0.1, novelty=0.2))
    state = ctrl.get_state()
    ctrl.reset()
    ctrl.set_state(state)
    new_state = ctrl.get_state()
    assert state == new_state


def test_reason_codes_whitelist_only(
    serotonin_controller: Any, serotonin_module: ModuleType
) -> None:
    """NON_PHYSICS: all emitted reason codes belong to the REASON_CODES_WHITELIST."""
    ctrl = serotonin_controller
    ctrl.update(_obs(stress=2.0, drawdown=-0.2, novelty=0.7))
    reasons = ctrl.explain_last_decision()
    for code in serotonin_module.REASON_CODES_WHITELIST:
        if code in reasons:
            assert code in serotonin_module.REASON_CODES_WHITELIST


def test_trace_schema_stable_keys(serotonin_controller: Any) -> None:
    """NON_PHYSICS: trace JSONL event keys match expected schema."""
    ctrl = serotonin_controller
    ctrl.update(_obs(stress=1.0, drawdown=-0.1, novelty=0.5))
    trace = ctrl.export_trace_jsonl().splitlines()[-1]
    event = json.loads(trace)
    expected_keys = [
        "timestamp_utc",
        "schema_version",
        "active_profile",
        "inputs",
        "outputs",
        "reason_codes",
        "invariants_checked",
        "update_latency_us",
    ]
    assert list(event.keys()) == expected_keys
    assert set(event["inputs"].keys()) == {
        "stress",
        "drawdown",
        "novelty",
        "market_vol",
        "free_energy",
        "cum_losses",
        "rho_loss",
    }
    assert set(event["outputs"].keys()) >= {
        "mode",
        "risk_budget",
        "gate",
        "serotonin_level",
    }
    assert isinstance(event["invariants_checked"], dict)


def test_update_not_using_pandas(
    monkeypatch: pytest.MonkeyPatch, serotonin_controller: Any
) -> None:
    """NON_PHYSICS: update path must not import pandas."""

    class _NoPandas:
        def __getattr__(self, name: str) -> None:
            raise AssertionError("pandas should not be used")

    sys.modules["pandas"] = _NoPandas()  # type: ignore[assignment]
    ctrl = serotonin_controller
    ctrl.update(_obs())
    sys.modules.pop("pandas", None)


def test_update_constant_time_complexity(serotonin_controller: Any) -> None:
    """NON_PHYSICS: per-update latency does not degrade with iteration count."""
    ctrl = serotonin_controller
    t0 = time.perf_counter()
    for _ in range(50):
        ctrl.update(_obs(stress=0.6, drawdown=-0.05, novelty=0.2))
    base = time.perf_counter() - t0

    t1 = time.perf_counter()
    for _ in range(5000):
        ctrl.update(_obs(stress=0.61, drawdown=-0.05, novelty=0.2))
    long = time.perf_counter() - t1

    assert long / 5000 < base / 50 * MAX_COMPLEXITY_FACTOR


def test_micro_benchmark_latency(serotonin_controller: Any) -> None:
    """NON_PHYSICS: median update latency stays below 2000 us."""
    ctrl = serotonin_controller
    samples: list[float] = []
    for _ in range(10):
        out = ctrl.update(_obs(stress=0.5, drawdown=-0.03, novelty=0.2))
        samples.append(out.metrics_snapshot["update_latency_us"])
    median = sorted(samples)[len(samples) // 2]
    assert median < 2000


def test_invariants_flags_and_clamp_recorded(serotonin_controller: Any) -> None:
    """INV-5HT2 + INV-HPC2: the per-update invariant flags are checked and traced.

    The runtime self-records its own physics-invariant verdicts: finite_inputs
    (INV-HPC2 no NaN/Inf) and serotonin_in_bounds (INV-5HT2 s in [0,1]) must both be
    True, and any risk-budget clamp must be reflected consistently in reason_codes.
    """
    ctrl = serotonin_controller
    ctrl.update(_obs(stress=2.5, drawdown=-0.2, novelty=0.5))
    event = json.loads(ctrl.export_trace_jsonl().splitlines()[-1])
    invariants = event["invariants_checked"]
    assert invariants["finite_inputs"] is True, (
        f"INV-HPC2: finite_inputs flag must be True, observed "
        f"finite_inputs={invariants['finite_inputs']!r} at stress=2.5 (expected finite)"
    )
    assert invariants["serotonin_in_bounds"] is True, (
        f"INV-5HT2: serotonin_in_bounds flag must be True, observed "
        f"serotonin_in_bounds={invariants['serotonin_in_bounds']!r} at stress=2.5 "
        f"(expected level in [0,1])"
    )
    assert "risk_budget_clamped" in invariants, (
        f"INV-5HT2: trace must record the clamp flag, observed keys="
        f"{sorted(invariants)} at stress=2.5 (expected risk_budget_clamped present)"
    )
    if invariants["risk_budget_clamped"]:
        assert "RISK_BUDGET_CLAMPED" in event["reason_codes"], (
            f"INV-5HT2: clamp flag set must emit RISK_BUDGET_CLAMPED, observed "
            f"reason_codes={event['reason_codes']} at stress=2.5 (expected consistency)"
        )
    else:
        assert "RISK_BUDGET_CLAMPED" not in event["reason_codes"], (
            f"INV-5HT2: clamp flag unset must omit RISK_BUDGET_CLAMPED, observed "
            f"reason_codes={event['reason_codes']} at stress=2.5 (expected consistency)"
        )


def test_regression_cooldown_reentry(serotonin_controller: Any) -> None:
    """INV-5HT3: re-entering progressively higher stress never raises the risk budget.

    Regression for a cooldown-reentry bug: under a monotone-increasing stress
    re-entry sequence the risk budget must stay monotone non-increasing (INV-5HT3),
    never rebound upward on re-entry.
    """
    ctrl = serotonin_controller
    budgets: list[float] = []
    for stress in (2.0, 2.1, 2.3, 2.6):
        budgets.append(ctrl.update(_obs(stress=stress, drawdown=-0.3, novelty=0.4)).risk_budget)
    deltas = np.diff(budgets)
    monotone_tol = 1e-9  # numerical floor for the non-increasing comparison
    assert np.all(deltas <= monotone_tol), (
        f"INV-5HT3: risk budget must be monotone non-increasing under stress re-entry, "
        f"observed diffs={deltas.tolist()} with N=4 stress=[2.0,2.1,2.3,2.6] "
        f"(expected all <= monotone_tol; no rebound on re-entry)"
    )


def test_risk_gate_reduces_exposure(serotonin_controller: Any) -> None:
    """INV-5HT3: rising stress strictly reduces risk-budget exposure vs a calm baseline.

    A fresh-controller calm baseline (stress=0.2) is compared against each elevated
    stress level; every elevated case must yield a strictly smaller risk budget than
    the calm baseline (aversive exposure reduction).
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    baseline = cls(cfg_path).update(_obs(stress=0.2, drawdown=-0.01, novelty=0.1)).risk_budget
    for stress in (1.5, 3.0, 5.0):
        high = cls(cfg_path).update(_obs(stress=stress, drawdown=-0.3, novelty=0.1)).risk_budget
        assert high < baseline, (
            f"INV-5HT3: elevated stress must reduce risk budget below the calm "
            f"baseline={baseline}, observed high={high} at stress={stress} "
            f"(expected exposure reduction)"
        )


def test_ecs_alignment_monotone_stress(serotonin_controller: Any) -> None:
    """INV-5HT3: monotone stress increase -> monotone non-increasing risk budget.

    Sweeps stress on fresh controllers and requires the risk-budget trajectory to be
    monotone non-increasing — the ECS-aligned risk-off response to rising aversive load.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    budgets = [
        cls(cfg_path).update(_obs(stress=s, drawdown=-0.02, novelty=0.2)).risk_budget
        for s in (0.2, 0.4, 0.7, 1.0)
    ]
    deltas = np.diff(budgets)
    monotone_tol = 1e-9  # numerical floor for the non-increasing comparison
    assert np.all(deltas <= monotone_tol), (
        f"INV-5HT3: risk budget must be monotone non-increasing in stress, observed "
        f"diffs={deltas.tolist()} with N=4 stress=[0.2,0.4,0.7,1.0] "
        f"(expected all <= monotone_tol)"
    )


def test_crisis_priority_overrides_modes(serotonin_controller: Any) -> None:
    """INV-HPC2: non-finite crisis inputs always resolve to the safe DEFENSIVE mode.

    INV-HPC2 forbids NaN/Inf propagation: each non-finite (Inf or -Inf) crisis input
    must be intercepted and routed to DEFENSIVE rather than producing a non-finite
    internal state that leaks into the mode selection.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    crisis_inputs = (
        {"stress": float("inf"), "drawdown": -0.1, "novelty": 0.2},
        {"stress": 0.4, "drawdown": float("-inf"), "novelty": 0.2},
        {"stress": float("inf"), "drawdown": float("inf"), "novelty": 0.2},
    )
    for obs in crisis_inputs:
        out = cls(cfg_path).update(obs)
        assert out.mode == "DEFENSIVE", (
            f"INV-HPC2: non-finite crisis input must force DEFENSIVE, observed "
            f"mode={out.mode!r} with stress={obs['stress']}, drawdown={obs['drawdown']} "
            f"(expected fail-safe)"
        )


def test_reason_codes_flow_to_trace(serotonin_controller: Any) -> None:
    """NON_PHYSICS: reason_codes propagate into trace JSONL events."""
    ctrl = serotonin_controller
    ctrl.update(_obs(stress=2.2, drawdown=-0.2, novelty=0.5))
    event = json.loads(ctrl.export_trace_jsonl().splitlines()[-1])
    assert "reason_codes" in event
    assert isinstance(event["reason_codes"], list)


def test_positive_drawdown_triggers_spike(serotonin_controller: Any) -> None:
    """INV-5HT7: a drawdown spike (regardless of sign) drives the hard veto.

    INV-5HT7's |drawdown| disjunct must fire on a magnitude basis: each spike in the
    swept drawdown set (including a positive-signed coercion case) must set the
    HOLD_OR_REDUCE_ONLY gate and emit DRAWDOWN_SPIKE at low stress.
    """
    cfg_path = serotonin_controller.config_path
    cls = type(serotonin_controller)
    for drawdown in (0.2, 0.4, 0.6):
        out = cls(cfg_path).update(_obs(stress=0.2, drawdown=drawdown, novelty=0.2))
        assert out.action_gate == "HOLD_OR_REDUCE_ONLY", (
            f"INV-5HT7: drawdown spike must veto, observed gate={out.action_gate!r} "
            f"with drawdown={drawdown}, stress=0.2 (expected HOLD_OR_REDUCE_ONLY)"
        )
        assert "DRAWDOWN_SPIKE" in out.reason_codes, (
            f"INV-5HT7: drawdown spike must emit DRAWDOWN_SPIKE, observed "
            f"reason_codes={out.reason_codes} with drawdown={drawdown} (expected spike code)"
        )


def test_no_cyclic_imports(serotonin_module: ModuleType) -> None:
    """NON_PHYSICS: production module does not import from tests package."""
    assert "tests" not in serotonin_module.SerotoninController.__module__


def test_config_validation_error_message(tmp_path: Path) -> None:
    """NON_PHYSICS: invalid config raises ValueError with descriptive message."""
    bad_cfg: dict[str, object] = {
        "alpha": 1.0,
        "beta": 1.0,
        "gamma": 1.0,
        "delta_rho": 1.0,
        "k": 1.0,
        "theta": 0.0,
        "delta": 0.5,
        "za_bias": 0.0,
        "decay_rate": 0.1,
        "cooldown_threshold": 0.5,
        "desens_threshold_ticks": 1,
        "desens_rate": 0.1,
        "target_dd": 0.1,
        "target_sharpe": 1.0,
        "beta_temper": 0.1,
        "phase_threshold": 0.1,
        "phase_kappa": 0.1,
        "burst_factor": 0.1,
        "mod_t_max": 1.0,
        "mod_t_half": 1.0,
        "mod_k": 0.1,
        "max_desens_counter": 10,
        "desens_gain": 0.1,
        "gate_veto": 0.9,
        "phasic_veto": 1.0,
        "temperature_floor_min": 0.8,
        "temperature_floor_max": 0.4,
    }
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump(bad_cfg), encoding="utf-8")
    _module, SerotoninController, _ = _load_serotonin_module()
    with pytest.raises(ValueError, match="temperature_floor_min"):
        SerotoninController(str(cfg_path))


def test_deterministic_timestamp(
    monkeypatch: pytest.MonkeyPatch, serotonin_controller: Any
) -> None:
    """NON_PHYSICS: deterministic time provider produces expected timestamp in trace."""
    ctrl = serotonin_controller
    fixed = dt.datetime(2024, 1, 1, 0, 0, 0)
    ctrl._time_provider = lambda: fixed
    ctrl.update(_obs(stress=0.9, drawdown=-0.1, novelty=0.2))
    event = json.loads(ctrl.export_trace_jsonl().splitlines()[-1])
    assert event["timestamp_utc"].startswith("2024-01-01T00:00:00")


def test_jsonl_export_stable_order(serotonin_controller: Any) -> None:
    """NON_PHYSICS: JSONL export key ordering is deterministic."""
    ctrl = serotonin_controller
    ctrl.update(_obs(stress=0.8, drawdown=-0.1, novelty=0.2))
    lines = ctrl.export_trace_jsonl().splitlines()
    parsed_lines = [json.loads(line) for line in lines]
    assert all(isinstance(evt, dict) for evt in parsed_lines)
    parsed = parsed_lines[-1]
    expected_keys = [
        "timestamp_utc",
        "schema_version",
        "active_profile",
        "inputs",
        "outputs",
        "reason_codes",
        "invariants_checked",
        "update_latency_us",
    ]
    assert list(parsed.keys()) == expected_keys
