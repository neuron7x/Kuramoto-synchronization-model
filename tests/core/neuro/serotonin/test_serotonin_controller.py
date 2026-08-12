# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml


def _load_serotonin_module() -> tuple[types.ModuleType, Any]:
    module_path = (
        Path(__file__).resolve().parents[4]
        / "core"
        / "neuro"
        / "serotonin"
        / "serotonin_controller.py"
    )
    spec = importlib.util.spec_from_file_location("serotonin_controller_test_module", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, module.SerotoninController


@pytest.fixture(scope="module")
def serotonin_module_and_cls() -> tuple[types.ModuleType, Any]:
    return _load_serotonin_module()


@pytest.fixture()
def serotonin_module(
    serotonin_module_and_cls: tuple[types.ModuleType, Any],
) -> types.ModuleType:
    module, _ = serotonin_module_and_cls
    return module


@pytest.fixture()
def serotonin_cls(serotonin_module_and_cls: tuple[types.ModuleType, Any]) -> Any:
    _, cls = serotonin_module_and_cls
    return cls


@pytest.fixture()
def serotonin_config_path(tmp_path: Path) -> Path:
    cfg_source = Path(__file__).resolve().parents[4] / "configs" / "serotonin.yaml"
    target = tmp_path / "serotonin.yaml"
    loaded = yaml.safe_load(cfg_source.read_text(encoding="utf-8")) or {}
    target.write_text(
        yaml.safe_dump(
            {
                "active_profile": "v24",
                "serotonin_v24": loaded.get("serotonin_v24", {}),
            }
        ),
        encoding="utf-8",
    )
    return target


@pytest.fixture()
def serotonin_controller(serotonin_cls: Any, serotonin_config_path: Path) -> Any:
    return serotonin_cls(str(serotonin_config_path))


def test_resolve_config_path_direct_file(serotonin_cls: Any, serotonin_config_path: Path) -> None:
    """NON_PHYSICS: config-path resolution plumbing, not a physics invariant."""
    resolved = serotonin_cls._resolve_config_path(str(serotonin_config_path))
    assert resolved == serotonin_config_path


def test_resolve_config_path_prefers_env_dir(
    monkeypatch: pytest.MonkeyPatch, serotonin_cls: Any, tmp_path: Path
) -> None:
    """NON_PHYSICS: env-dir config discovery plumbing, not a physics invariant."""
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    alt_cfg = env_dir / "serotonin.yaml"
    alt_cfg.write_text(
        (Path(__file__).resolve().parents[4] / "configs" / "serotonin.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEOSYNC_CONFIG_DIR", str(env_dir))

    resolved = serotonin_cls._resolve_config_path("nonexistent.yaml")

    assert resolved == alt_cfg


def test_resolve_config_path_missing(
    monkeypatch: pytest.MonkeyPatch, serotonin_cls: Any, tmp_path: Path
) -> None:
    """NON_PHYSICS: missing-config error plumbing, not a physics invariant."""
    monkeypatch.delenv("GEOSYNC_CONFIG_DIR", raising=False)
    with pytest.raises(FileNotFoundError):
        serotonin_cls._resolve_config_path(str(tmp_path / "missing.yaml"))


def test_config_profile_mismatch_rejected(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: config schema validation, not a physics invariant."""
    cfg = {
        "active_profile": "legacy",
        "serotonin_legacy": {"tonic_beta": 0.1},
        "serotonin_v24": {},
    }
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_config_unknown_root_rejected(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: config schema validation, not a physics invariant."""
    cfg: dict[str, Any] = {
        "active_profile": "v24",
        "serotonin_v24": {},
        "unexpected": 1,
    }
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_config_missing_profile_section(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: config schema validation, not a physics invariant."""
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump({"active_profile": "v24"}), encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_multi_document_config_rejected(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: config schema validation, not a physics invariant."""
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text("---\nactive_profile: v24\n---\n{}", encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_estimate_aversive_state_matches_formula(serotonin_controller: Any) -> None:
    """INV-5HT3: aversive state = 3*tanh(release/3) is monotone increasing in stress.

    Witnesses the qualitative monotonicity (INV-5HT3): the aversive-state map is a
    strictly increasing saturating function of the stress-release scalar, so sweeping
    market_vol upward must produce a non-decreasing serotonin response that also
    matches the closed-form 3*tanh(release/3) at each point.
    """
    ctrl = serotonin_controller
    cfg = ctrl.config
    free_energy = 0.5
    losses = 0.8
    rho = 0.1

    results: list[float] = []
    for market_vol in (1.0, 4.0, 9.0, 16.0):
        result = ctrl.estimate_aversive_state(market_vol, free_energy, losses, rho)
        expected_release = (
            cfg["alpha"] * math.sqrt(market_vol)
            + cfg["beta"] * free_energy
            + cfg["gamma"] * (losses + 0.5 * losses**2)
            + cfg["delta_rho"] * (1.0 - rho)
        )
        expected = 3.0 * math.tanh(expected_release / 3.0)
        assert math.isclose(result, expected, rel_tol=1e-6), (
            f"INV-5HT3: aversive-state formula mismatch at market_vol={market_vol}: "
            f"observed result={result}, expected 3*tanh(release/3)={expected} "
            f"(theory: closed-form saturating aversive map)"
        )
        results.append(result)

    deltas = np.diff(results)
    monotone_tol = -1e-12  # numerical floor for non-decreasing check (float round-off)
    assert np.all(deltas >= monotone_tol), (
        f"INV-5HT3: aversive state must be monotone non-decreasing in stress, "
        f"observed diffs={deltas.tolist()} with N=4 market_vol=[1,4,9,16] "
        f"(expected all >= monotone_tol per increasing aversive-wait signal)"
    )


def test_estimate_aversive_state_with_override_weights(
    serotonin_controller: Any,
) -> None:
    """INV-5HT3: amplifying the stress weight alpha monotonically amplifies serotonin.

    The aversive-state release scales linearly in alpha before the tanh saturation,
    so a monotone sweep of the alpha multiplier must give a monotone non-decreasing
    serotonin response — a directional (monotonicity_test) witness of INV-5HT3.
    """
    ctrl = serotonin_controller
    base_alpha = ctrl.config["alpha"]

    responses: list[float] = []
    for mult in (1.0, 1.5, 2.0, 3.0):
        overrides = {"alpha": base_alpha * mult}
        responses.append(ctrl.estimate_aversive_state(1.0, 0.5, 0.5, 0.0, overrides))

    deltas = np.diff(responses)
    monotone_tol = -1e-12  # numerical floor for non-decreasing check (float round-off)
    assert np.all(deltas >= monotone_tol), (
        f"INV-5HT3: serotonin response must be monotone non-decreasing as alpha grows, "
        f"observed diffs={deltas.tolist()} with N=4 alpha_mult=[1,1.5,2,3] "
        f"(expected all >= monotone_tol; stress weight only increases the aversive signal)"
    )


def test_estimate_aversive_state_rejects_negative_inputs(
    serotonin_controller: Any,
) -> None:
    """INV-5HT3: aversive-state inputs must be non-negative to preserve monotone mapping.

    The monotone aversive map is only defined on the non-negative stress domain
    (sqrt(market_vol) etc.); a negative coordinate would break monotonicity, so each
    such input must be rejected. Sweeping one negative coordinate at a time.
    """
    ctrl = serotonin_controller
    negative_cases = (
        (-0.1, 0.2, 0.3, 0.0),
        (0.1, -0.2, 0.3, 0.0),
        (0.1, 0.2, -0.3, 0.0),
    )
    for market_vol, free_energy, losses, rho in negative_cases:
        with pytest.raises(ValueError):
            ctrl.estimate_aversive_state(market_vol, free_energy, losses, rho)


def test_compute_serotonin_signal_updates_floor(serotonin_controller: Any) -> None:
    """INV-5HT2, INV-5HT5: signal in [0,1] and temperature_floor bounded."""
    ctrl = serotonin_controller
    cfg = ctrl.config

    low = ctrl.compute_serotonin_signal(0.1)
    floor_low = ctrl.temperature_floor

    high = ctrl.compute_serotonin_signal(2.5)
    floor_high = ctrl.temperature_floor

    floor_min = cfg["temperature_floor_min"]
    floor_max = cfg["temperature_floor_max"]
    assert 0.0 <= low <= 1.0, (
        f"INV-5HT2: serotonin signal must stay in [0,1], observed low={low} "
        f"at stress=0.1 (expected bounded output)"
    )
    assert 0.0 <= high <= 1.0, (
        f"INV-5HT2: serotonin signal must stay in [0,1], observed high={high} "
        f"at stress=2.5 (expected bounded output)"
    )
    assert floor_low >= floor_min, (
        f"INV-5HT5: temperature_floor must stay >= floor_min={floor_min}, "
        f"observed floor_low={floor_low} at stress=0.1 (expected bounded floor)"
    )
    assert floor_high <= floor_max, (
        f"INV-5HT5: temperature_floor must stay <= floor_max={floor_max}, "
        f"observed floor_high={floor_high} at stress=2.5 (expected bounded floor)"
    )
    assert floor_high >= floor_low, (
        f"INV-5HT5: floor must rise with stress, observed floor_high={floor_high} "
        f"< floor_low={floor_low} at stress=2.5 vs stress=0.1 (expected monotone floor)"
    )


def test_compute_serotonin_signal_rejects_negative(serotonin_controller: Any) -> None:
    """INV-5HT2: serotonin signal domain guard — every negative input is rejected.

    INV-5HT2 bounds s(t) in [0, s_max]; the domain that supports that bound excludes
    negative stress, so each negative input across the swept range must raise.
    """
    ctrl = serotonin_controller
    for bad_input in (-1e-6, -0.5, -10.0, -1e6):
        with pytest.raises(ValueError):
            ctrl.compute_serotonin_signal(bad_input)


def test_modulate_action_prob_applies_inhibition(serotonin_controller: Any) -> None:
    """INV-5HT2: modulated action probability stays in [0,1] across the input sweep.

    INV-5HT2 bounds the serotonin-modulated output in [0, 1]; here every input
    probability in a sweep must map to a value in [0,1] that also matches the
    closed-form inhibition*bias map clipped to [0,1].
    """
    ctrl = serotonin_controller
    ctrl.serotonin_level = 0.6
    cfg = ctrl.config
    inhibition_strength = ctrl.serotonin_level**2
    inhibition_factor = 1.0 - inhibition_strength * cfg["delta"]
    bias_factor = 1.0 + cfg["za_bias"] * (1.0 - math.exp(-2.0 * ctrl.serotonin_level))

    for prob in (0.0, 0.2, 0.5, 0.8, 1.0):
        result = ctrl.modulate_action_prob(prob)
        inhibited = prob * max(0.0, inhibition_factor)
        expected = float(np.clip(inhibited * bias_factor, 0.0, 1.0))
        assert math.isclose(result, expected, rel_tol=1e-6, abs_tol=1e-12), (
            f"INV-5HT2: modulated prob mismatch at prob={prob}: "
            f"observed result={result}, expected clip(inhibited*bias)={expected}"
        )
        assert 0.0 <= result <= 1.0, (
            f"INV-5HT2: modulated probability must stay in [0,1], observed "
            f"result={result} at prob={prob} (expected bounded output)"
        )


def test_modulate_action_prob_rejects_invalid_probability(
    serotonin_controller: Any,
) -> None:
    """INV-5HT2: probability input must lie in [0,1]; out-of-range inputs are rejected.

    INV-5HT2 is a closed-bound invariant; the modulation contract refuses inputs
    outside [0,1] so the bound is never silently violated. Each out-of-range input
    in the sweep must raise.
    """
    ctrl = serotonin_controller
    for bad_prob in (-0.5, -1e-6, 1.0 + 1e-6, 1.5, 10.0):
        with pytest.raises(ValueError):
            ctrl.modulate_action_prob(bad_prob)


def test_apply_internal_shift_tempering(serotonin_controller: Any) -> None:
    """INV-5HT1: stronger serotonin signal monotonically tempers the internal shift.

    INV-5HT1 is the Lyapunov non-increasing property: a larger serotonin (aversive)
    signal must drive the internal-shift magnitude monotonically down toward its
    non-negative floor, never amplify it. Witnessed by sweeping serotonin_signal
    upward and requiring a non-increasing tempered trajectory.
    """
    ctrl = serotonin_controller
    ctrl.serotonin_level = 0.7
    # Non-negativity floor is a physical bound (shift magnitude cannot go below 0),
    # not a tuned threshold.
    shift_floor = 0.0

    tempered_seq = [
        ctrl.apply_internal_shift(1.0, serotonin_signal=sig) for sig in (0.1, 0.3, 0.5, 0.7, 0.9)
    ]
    deltas = np.diff(tempered_seq)
    monotone_tol = 1e-12  # numerical floor for non-increasing check (float round-off)
    assert np.all(deltas <= monotone_tol), (
        f"INV-5HT1: tempered shift must be monotone non-increasing as serotonin rises, "
        f"observed diffs={deltas.tolist()} with N=5 signal=[0.1..0.9] "
        f"(expected all <= monotone_tol per Lyapunov tempering)"
    )
    assert min(tempered_seq) >= shift_floor, (
        f"INV-5HT1: tempered shift must respect the non-negativity floor={shift_floor}, "
        f"observed min={min(tempered_seq)} with N=5 signal=[0.1..0.9] (expected >= floor)"
    )


def test_apply_internal_shift_requires_non_negative_gradient(
    serotonin_controller: Any,
) -> None:
    """INV-5HT1: gradient input must be non-negative for Lyapunov stability.

    The Lyapunov tempering is only defined on a non-negative gradient; a negative
    gradient would invert the descent direction, so each negative input across the
    swept range must be rejected.
    """
    ctrl = serotonin_controller
    for bad_gradient in (-1e-6, -0.1, -1.0, -100.0):
        with pytest.raises(ValueError):
            ctrl.apply_internal_shift(bad_gradient)


def test_check_cooldown_hysteresis(serotonin_controller: Any) -> None:
    """NON_PHYSICS: cooldown hysteresis band logic (controller state machine, not the
    INV-5HT7 hard-veto physics invariant)."""
    ctrl = serotonin_controller
    margin = 0.05
    threshold = ctrl.config["cooldown_threshold"]
    ctrl.phasic_level = 0.0
    ctrl.gate_level = 0.0

    ctrl._hold_state = False
    assert not ctrl.check_cooldown(threshold * (1.0 + margin) - 1e-6)
    assert ctrl.check_cooldown(threshold * (1.0 + margin) + 1e-6)

    ctrl._hold_state = True
    assert ctrl.check_cooldown(threshold * (1.0 - margin) + 1e-6)
    assert not ctrl.check_cooldown(threshold * (1.0 - margin) - 1e-6)


def test_check_cooldown_guard_can_block(
    monkeypatch: pytest.MonkeyPatch, serotonin_controller: Any
) -> None:
    """NON_PHYSICS: TACL guard wiring can veto cooldown activation (callback plumbing,
    not the INV-5HT7 hard-veto physics invariant)."""
    ctrl = serotonin_controller
    ctrl._hold_state = False
    ctrl.phasic_level = ctrl.config["phasic_veto"] * 2
    block_calls: list[tuple[str, dict[str, Any]]] = []

    def guard(name: str, payload: dict[str, Any]) -> bool:
        block_calls.append((name, payload))
        return False

    ctrl.set_tacl_guard(guard)

    assert not ctrl.check_cooldown(ctrl.config["cooldown_threshold"] * 2)
    assert block_calls and block_calls[0][0] == "serotonin_cooldown"


def test_step_validates_inputs(serotonin_controller: Any, caplog: pytest.LogCaptureFixture) -> None:
    """NON_PHYSICS: step() input validation and drawdown-sign coercion logging
    (argument plumbing, not the INV-5HT3 monotonicity physics invariant)."""
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.step(stress=-0.1, drawdown=-0.01, novelty=0.2)
    with caplog.at_level("WARNING"):
        ctrl.step(stress=0.1, drawdown=0.01, novelty=0.2)
        assert any("coercing to negative" in record.message for record in caplog.records)
    with pytest.raises(ValueError):
        ctrl.step(stress=0.1, drawdown=-0.01, novelty=-0.2)


def test_step_returns_cooldown_tuple(
    monkeypatch: pytest.MonkeyPatch,
    serotonin_module: types.ModuleType,
    serotonin_controller: Any,
) -> None:
    """INV-5HT2: step() returns a serotonin level bounded in [0,1].

    The (hold, veto, cooldown, level) tuple's level field must obey the INV-5HT2
    bound s(t) in [0, s_max=1] on a nominal step; cooldown is a physical elapsed
    time and so is non-negative.
    """
    ctrl = serotonin_controller
    times = [1000.0, 1000.1, 1000.2, 1000.3]

    def fake_time() -> float:
        return times.pop(0)

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    hold, veto, cooldown, level = ctrl.step(stress=0.2, drawdown=-0.01, novelty=0.2)

    # cooldown is an elapsed-time quantity; its floor is the physical zero, not a tuned threshold.
    cooldown_time_floor = 0.0
    assert hold in {
        True,
        False,
    }, f"INV-5HT2: hold flag must be boolean, observed hold={hold!r} at stress=0.2"
    assert veto in {
        True,
        False,
    }, f"INV-5HT2: veto flag must be boolean, observed veto={veto!r} at stress=0.2"
    assert cooldown >= cooldown_time_floor, (
        f"INV-5HT2: cooldown elapsed-time must be >= {cooldown_time_floor}, "
        f"observed cooldown={cooldown} at stress=0.2 (expected non-negative time)"
    )
    assert 0.0 <= level <= 1.0, (
        f"INV-5HT2: serotonin level must stay in [0,1], observed level={level} "
        f"at stress=0.2 (expected bounded output)"
    )


def test_to_dict_reports_current_state(
    monkeypatch: pytest.MonkeyPatch,
    serotonin_module: types.ModuleType,
    serotonin_controller: Any,
    tmp_path: Path,
) -> None:
    """INV-5HT5: snapshot includes temperature_floor within configured bounds."""
    ctrl = serotonin_controller
    ctrl._hold_state = True
    ctrl._cooldown_start_time = 50.0

    times = [60.0]

    def fake_time() -> float:
        return times[0]

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    snapshot = ctrl.to_dict()

    # Elapsed cooldown is now (60.0) minus cooldown_start (50.0) = 10.0 s by construction.
    expected_elapsed_s = 60.0 - 50.0
    floor_min = ctrl.config["temperature_floor_min"]
    assert snapshot["hold_state"] is True, (
        f"INV-5HT5: snapshot must report held state, observed "
        f"hold_state={snapshot['hold_state']!r} at now=60.0 (expected True after "
        f"_hold_state set)"
    )
    assert snapshot["cooldown_s"] >= expected_elapsed_s, (
        f"INV-5HT5: snapshot cooldown_s must equal elapsed time >= "
        f"{expected_elapsed_s}s, observed cooldown_s={snapshot['cooldown_s']} "
        f"at now=60.0, start=50.0 (expected derived elapsed)"
    )
    assert snapshot["temperature_floor"] >= floor_min, (
        f"INV-5HT5: snapshot temperature_floor must stay >= floor_min={floor_min}, "
        f"observed temperature_floor={snapshot['temperature_floor']} at now=60.0 "
        f"(expected bounded floor)"
    )


def test_save_state_persists_json(
    monkeypatch: pytest.MonkeyPatch,
    serotonin_module: types.ModuleType,
    serotonin_controller: Any,
    tmp_path: Path,
) -> None:
    """NON_PHYSICS: JSON state serialization plumbing, not a physics invariant."""
    ctrl = serotonin_controller
    target = tmp_path / "state.json"

    times = [100.0, 100.0]

    def fake_time() -> float:
        return times[0]

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    ctrl.save_state(str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["_metadata"]["config_path"] == ctrl.config_path
    assert "serotonin_level" in data


def test_config_rejects_extra_fields(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: Pydantic config schema rejects unexpected fields."""
    config_with_extra = tmp_path / "config_extra.yaml"

    base_cfg: dict[str, Any] = {
        "alpha": 0.5,
        "beta": 0.3,
        "gamma": 0.4,
        "delta_rho": 0.2,
        "k": 1.5,
        "theta": 0.0,
        "delta": 0.5,
        "za_bias": 0.0,
        "decay_rate": 0.01,
        "cooldown_threshold": 0.7,
        "desens_threshold_ticks": 3,
        "desens_rate": 0.05,
        "target_dd": 0.15,
        "target_sharpe": 1.5,
        "beta_temper": 0.5,
        "phase_threshold": 0.7,
        "phase_kappa": 2.0,
        "burst_factor": 0.35,
        "mod_t_max": 10.0,
        "mod_t_half": 5.0,
        "mod_k": 0.5,
        "max_desens_counter": 10,
        "desens_gain": 0.8,
        # Extra field that should be rejected
        "tonic_beta": 0.35,
    }
    config_with_extra.write_text(
        yaml.safe_dump(
            {"active_profile": "v24", "serotonin_v24": base_cfg},
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        serotonin_cls(str(config_with_extra))


def test_config_validates_required_fields(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: Pydantic config schema requires all necessary fields."""
    incomplete_config = tmp_path / "incomplete.yaml"

    # Config missing required fields
    incomplete_content = """
alpha: 0.5
beta: 0.3
# Missing many required fields
"""
    incomplete_config.write_text(
        yaml.safe_dump(
            {
                "active_profile": "v24",
                "serotonin_v24": yaml.safe_load(incomplete_content),
            }
        ),
        encoding="utf-8",
    )

    # Should raise ValueError due to missing required fields
    with pytest.raises(ValueError, match="Invalid serotonin root configuration"):
        serotonin_cls(str(incomplete_config))


def test_dual_compatibility_config_loads_successfully(
    serotonin_cls: Any, serotonin_config_path: Path
) -> None:
    """INV-5HT6, INV-5HT4: tonic_level starts at 0 (finite, >=0); sensitivity starts at 1.0."""
    ctrl = serotonin_cls(str(serotonin_config_path))

    # Verify all required v2.4.0 fields are present and loaded.
    required_fields = ("alpha", "beta", "gamma", "delta_rho", "k", "theta", "delta", "za_bias")
    for field in required_fields:
        assert field in ctrl.config, (
            f"INV-5HT6: required config field must load before the controller can "
            f"compute finite tonic dynamics with field={field!r}; observed keys="
            f"{sorted(ctrl.config)} (expected {field!r} present)"
        )

    # Verify controller initial physics state.
    # INV-5HT4: sensitivity must initialise inside its [0.1, 1.0] bound (at the max).
    sensitivity_max = 1.0
    tonic_init = 0.0
    aversive_floor = 0.0
    assert ctrl.tonic_level == tonic_init, (
        f"INV-5HT6: tonic_level must initialise finite and non-negative "
        f"with tonic_init={tonic_init}, observed tonic_level={ctrl.tonic_level} (expected 0)"
    )
    assert ctrl.sensitivity == sensitivity_max, (
        f"INV-5HT4: sensitivity must initialise at its bound with sensitivity_max={sensitivity_max} "
        f"within [0.1,1.0], observed sensitivity={ctrl.sensitivity} (expected at max)"
    )

    # INV-5HT6: aversive state is finite and non-negative under finite inputs.
    result = ctrl.estimate_aversive_state(
        market_vol=2.0, free_energy=0.3, cum_losses=0.5, rho_loss=0.2
    )
    assert isinstance(result, float), (
        f"INV-5HT6: aversive state must be a finite float, observed type "
        f"{type(result).__name__} at market_vol=2.0 (expected float)"
    )
    assert result >= aversive_floor, (
        f"INV-5HT6: aversive state must be >= floor={aversive_floor}, observed "
        f"result={result} at market_vol=2.0 (expected non-negative finite output)"
    )


def test_config_field_types_are_validated(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: Pydantic config field-type validation."""
    invalid_config = tmp_path / "invalid_types.yaml"

    # Config with invalid type for numeric field
    invalid_body: dict[str, Any] = {
        "alpha": "not_a_number",
        "beta": 0.3,
        "gamma": 0.4,
        "delta_rho": 0.2,
        "k": 1.5,
        "theta": 0.0,
        "delta": 0.5,
        "za_bias": 0.0,
        "decay_rate": 0.01,
        "cooldown_threshold": 0.7,
        "desens_threshold_ticks": 3,
        "desens_rate": 0.05,
        "target_dd": 0.15,
        "target_sharpe": 1.5,
        "beta_temper": 0.5,
        "phase_threshold": 0.7,
        "phase_kappa": 2.0,
        "burst_factor": 0.35,
        "mod_t_max": 10.0,
        "mod_t_half": 5.0,
        "mod_k": 0.5,
        "max_desens_counter": 10,
        "desens_gain": 0.8,
    }
    invalid_config.write_text(
        yaml.safe_dump(
            {
                "active_profile": "v24",
                "serotonin_v24": invalid_body,
            }
        ),
        encoding="utf-8",
    )

    # Should raise ValueError due to type validation error
    with pytest.raises(ValueError, match="Invalid serotonin root configuration"):
        serotonin_cls(str(invalid_config))


def test_config_constraints_are_enforced(serotonin_cls: Any, tmp_path: Path) -> None:
    """NON_PHYSICS: Pydantic config constraint (ge, le, gt) enforcement."""
    invalid_config = tmp_path / "invalid_constraints.yaml"

    # Config with value outside allowed range (alpha should be >= 0.0)
    invalid_body: dict[str, Any] = {
        "alpha": -1.0,
        "beta": 0.3,
        "gamma": 0.4,
        "delta_rho": 0.2,
        "k": 1.5,
        "theta": 0.0,
        "delta": 0.5,
        "za_bias": 0.0,
        "decay_rate": 0.01,
        "cooldown_threshold": 0.7,
        "desens_threshold_ticks": 3,
        "desens_rate": 0.05,
        "target_dd": 0.15,
        "target_sharpe": 1.5,
        "beta_temper": 0.5,
        "phase_threshold": 0.7,
        "phase_kappa": 2.0,
        "burst_factor": 0.35,
        "mod_t_max": 10.0,
        "mod_t_half": 5.0,
        "mod_k": 0.5,
        "max_desens_counter": 10,
        "desens_gain": 0.8,
    }
    invalid_config.write_text(
        yaml.safe_dump(
            {"active_profile": "v24", "serotonin_v24": invalid_body},
        ),
        encoding="utf-8",
    )

    # Should raise ValueError due to constraint violation
    with pytest.raises(ValueError, match="Invalid serotonin root configuration"):
        serotonin_cls(str(invalid_config))


def test_risk_budget_monotone_in_stress(serotonin_controller: Any) -> None:
    """INV-5HT3: higher stress -> lower risk budget (monotone decreasing)."""
    budgets: list[float] = []
    for stress in (0.0, 0.5, 1.0, 2.0):
        budget, _ = serotonin_controller._derive_risk_budget(
            serotonin_controller.serotonin_level, stress
        )
        budgets.append(budget)
    assert budgets == sorted(budgets, reverse=True), (
        f"INV-5HT3: risk budget must be monotone decreasing in stress, observed "
        f"budgets={budgets} with N=4 stress=[0,0.5,1,2] "
        f"(expected non-increasing per aversive risk-off response)"
    )


def test_serotonin_signal_stays_bounded(serotonin_controller: Any) -> None:
    """INV-5HT2: s(t) stays in [0,1] and finite across extreme inputs.

    The closed bound s(t) in [0, s_max=1] must hold even as stress grows far past the
    saturation point; swept over several large inputs to witness the saturation.
    """
    for stress in (10.0, 1e3, 1e6, 1e9):
        val = serotonin_controller.compute_serotonin_signal(stress)
        assert 0.0 <= val <= 1.0, (
            f"INV-5HT2: serotonin signal must stay in [0,1], observed val={val} "
            f"at stress={stress} (expected saturating bounded output)"
        )
        assert math.isfinite(val), (
            f"INV-5HT2: serotonin signal must be finite, observed val={val} "
            f"at stress={stress} (expected no NaN/Inf under finite input)"
        )
