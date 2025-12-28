from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml


def _load_serotonin_module() -> tuple[object, object]:
    module_path = (
        Path(__file__).resolve().parents[4]
        / "core"
        / "neuro"
        / "serotonin"
        / "serotonin_controller.py"
    )
    spec = importlib.util.spec_from_file_location(
        "serotonin_controller_test_module", module_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, module.SerotoninController


@pytest.fixture(scope="module")
def serotonin_module_and_cls():
    return _load_serotonin_module()


@pytest.fixture()
def serotonin_module(serotonin_module_and_cls):
    module, _ = serotonin_module_and_cls
    return module


@pytest.fixture()
def serotonin_cls(serotonin_module_and_cls):
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
def serotonin_controller(serotonin_cls, serotonin_config_path):
    return serotonin_cls(str(serotonin_config_path))


def test_resolve_config_path_direct_file(serotonin_cls, serotonin_config_path):
    resolved = serotonin_cls._resolve_config_path(str(serotonin_config_path))
    assert resolved == serotonin_config_path


def test_resolve_config_path_prefers_env_dir(
    monkeypatch, serotonin_cls, tmp_path: Path
):
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    alt_cfg = env_dir / "serotonin.yaml"
    alt_cfg.write_text(
        (Path(__file__).resolve().parents[4] / "configs" / "serotonin.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADEPULSE_CONFIG_DIR", str(env_dir))

    resolved = serotonin_cls._resolve_config_path("nonexistent.yaml")

    assert resolved == alt_cfg


def test_resolve_config_path_missing(monkeypatch, serotonin_cls, tmp_path: Path):
    monkeypatch.delenv("TRADEPULSE_CONFIG_DIR", raising=False)
    with pytest.raises(FileNotFoundError):
        serotonin_cls._resolve_config_path(str(tmp_path / "missing.yaml"))


def test_config_profile_mismatch_rejected(serotonin_cls, tmp_path: Path):
    cfg = {
        "active_profile": "legacy",
        "serotonin_legacy": {"tonic_beta": 0.1},
        "serotonin_v24": {},
    }
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_config_unknown_root_rejected(serotonin_cls, tmp_path: Path):
    cfg = {"active_profile": "v24", "serotonin_v24": {}, "unexpected": 1}
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_config_missing_profile_section(serotonin_cls, tmp_path: Path):
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text(yaml.safe_dump({"active_profile": "v24"}), encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_multi_document_config_rejected(serotonin_cls, tmp_path: Path):
    cfg_path = tmp_path / "serotonin.yaml"
    cfg_path.write_text("---\nactive_profile: v24\n---\n{}", encoding="utf-8")
    with pytest.raises(ValueError):
        serotonin_cls(str(cfg_path))


def test_estimate_aversive_state_matches_formula(serotonin_controller):
    ctrl = serotonin_controller
    cfg = ctrl.config
    market_vol = 4.0
    free_energy = 0.5
    losses = 0.8
    rho = 0.1

    result = ctrl.estimate_aversive_state(market_vol, free_energy, losses, rho)

    expected_release = (
        cfg["alpha"] * math.sqrt(market_vol)
        + cfg["beta"] * free_energy
        + cfg["gamma"] * (losses + 0.5 * losses**2)
        + cfg["delta_rho"] * (1.0 - rho)
    )
    expected = 3.0 * math.tanh(expected_release / 3.0)

    assert math.isclose(result, expected, rel_tol=1e-6)


def test_estimate_aversive_state_with_override_weights(serotonin_controller):
    ctrl = serotonin_controller
    overrides = {"alpha": ctrl.config["alpha"] * 2}

    baseline = ctrl.estimate_aversive_state(1.0, 0.5, 0.5, 0.0)
    overridden = ctrl.estimate_aversive_state(1.0, 0.5, 0.5, 0.0, overrides)

    assert overridden > baseline


def test_estimate_aversive_state_rejects_negative_inputs(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.estimate_aversive_state(-0.1, 0.2, 0.3, 0.0)
    with pytest.raises(ValueError):
        ctrl.estimate_aversive_state(0.1, -0.2, 0.3, 0.0)
    with pytest.raises(ValueError):
        ctrl.estimate_aversive_state(0.1, 0.2, -0.3, 0.0)


def test_compute_serotonin_signal_updates_floor(serotonin_controller):
    ctrl = serotonin_controller
    cfg = ctrl.config

    low = ctrl.compute_serotonin_signal(0.1)
    floor_low = ctrl.temperature_floor

    high = ctrl.compute_serotonin_signal(2.5)
    floor_high = ctrl.temperature_floor

    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert floor_low >= cfg["temperature_floor_min"]
    assert floor_high <= cfg["temperature_floor_max"]
    assert floor_high >= floor_low


def test_compute_serotonin_signal_rejects_negative(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.compute_serotonin_signal(-0.5)


def test_modulate_action_prob_applies_inhibition(serotonin_controller):
    ctrl = serotonin_controller
    ctrl.serotonin_level = 0.6
    result = ctrl.modulate_action_prob(0.8)

    cfg = ctrl.config
    inhibition_strength = ctrl.serotonin_level**2
    inhibition_factor = 1.0 - inhibition_strength * cfg["delta"]
    inhibited = 0.8 * max(0.0, inhibition_factor)
    bias_factor = 1.0 + cfg["za_bias"] * (1.0 - math.exp(-2.0 * ctrl.serotonin_level))
    expected = float(np.clip(inhibited * bias_factor, 0.0, 1.0))

    assert math.isclose(result, expected, rel_tol=1e-6)


def test_modulate_action_prob_rejects_invalid_probability(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.modulate_action_prob(1.5)


def test_apply_internal_shift_tempering(serotonin_controller):
    ctrl = serotonin_controller
    ctrl.serotonin_level = 0.7
    baseline = ctrl.apply_internal_shift(1.0, serotonin_signal=0.2)
    tempered = ctrl.apply_internal_shift(1.0, serotonin_signal=0.7)

    assert tempered < baseline
    assert tempered >= 0.0


def test_apply_internal_shift_requires_non_negative_gradient(serotonin_controller):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.apply_internal_shift(-0.1)


def test_check_cooldown_hysteresis(serotonin_controller):
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


def test_check_cooldown_guard_can_block(monkeypatch, serotonin_controller):
    ctrl = serotonin_controller
    ctrl._hold_state = False
    ctrl.phasic_level = ctrl.config["phasic_veto"] * 2
    block_calls = []

    def guard(name: str, payload: dict) -> bool:
        block_calls.append((name, payload))
        return False

    ctrl.set_tacl_guard(guard)

    assert not ctrl.check_cooldown(ctrl.config["cooldown_threshold"] * 2)
    assert block_calls and block_calls[0][0] == "serotonin_cooldown"


def test_step_validates_inputs(serotonin_controller, caplog):
    ctrl = serotonin_controller
    with pytest.raises(ValueError):
        ctrl.step(stress=-0.1, drawdown=-0.01, novelty=0.2)
    with caplog.at_level("WARNING"):
        ctrl.step(stress=0.1, drawdown=0.01, novelty=0.2)
        assert any("coercing to negative" in record.message for record in caplog.records)
    with pytest.raises(ValueError):
        ctrl.step(stress=0.1, drawdown=-0.01, novelty=-0.2)


def test_step_returns_cooldown_tuple(
    monkeypatch, serotonin_module, serotonin_controller
):
    ctrl = serotonin_controller
    times = [1000.0, 1000.1, 1000.2, 1000.3]

    def fake_time():
        return times.pop(0)

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    hold, veto, cooldown, level = ctrl.step(stress=0.2, drawdown=-0.01, novelty=0.2)

    assert hold in {True, False}
    assert veto in {True, False}
    assert cooldown >= 0.0
    assert 0.0 <= level <= 1.0


def test_to_dict_reports_current_state(
    monkeypatch, serotonin_module, serotonin_controller, tmp_path: Path
):
    ctrl = serotonin_controller
    ctrl._hold_state = True
    ctrl._cooldown_start_time = 50.0

    times = [60.0]

    def fake_time():
        return times[0]

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    snapshot = ctrl.to_dict()

    assert snapshot["hold_state"] is True
    assert snapshot["cooldown_s"] >= 10.0
    assert snapshot["temperature_floor"] >= ctrl.config["temperature_floor_min"]


def test_save_state_persists_json(
    monkeypatch, serotonin_module, serotonin_controller, tmp_path: Path
):
    ctrl = serotonin_controller
    target = tmp_path / "state.json"

    times = [100.0, 100.0]

    def fake_time():
        return times[0]

    monkeypatch.setattr(serotonin_module, "time", fake_time)

    ctrl.save_state(str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["_metadata"]["config_path"] == ctrl.config_path
    assert "serotonin_level" in data


def test_config_rejects_extra_fields(serotonin_cls, tmp_path: Path):
    """Test that SerotoninConfig rejects unexpected fields."""
    config_with_extra = tmp_path / "config_extra.yaml"

    base_cfg = {
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


def test_config_validates_required_fields(serotonin_cls, tmp_path: Path):
    """Test that SerotoninConfig still requires all necessary fields."""
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
    serotonin_cls, serotonin_config_path
):
    """Test that the strict v2.4.0 config loads correctly."""
    ctrl = serotonin_cls(str(serotonin_config_path))

    # Verify all required v2.4.0 fields are present and loaded
    assert "alpha" in ctrl.config
    assert "beta" in ctrl.config
    assert "gamma" in ctrl.config
    assert "delta_rho" in ctrl.config
    assert "k" in ctrl.config
    assert "theta" in ctrl.config
    assert "delta" in ctrl.config
    assert "za_bias" in ctrl.config

    # Verify controller is functional
    assert ctrl.tonic_level == 0.0
    assert ctrl.sensitivity == 1.0

    # Test basic functionality
    result = ctrl.estimate_aversive_state(
        market_vol=2.0, free_energy=0.3, cum_losses=0.5, rho_loss=0.2
    )
    assert isinstance(result, float)
    assert result >= 0.0


def test_config_field_types_are_validated(serotonin_cls, tmp_path: Path):
    """Test that config field types are properly validated by Pydantic."""
    invalid_config = tmp_path / "invalid_types.yaml"

    # Config with invalid type for numeric field
    invalid_body = {
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


def test_config_constraints_are_enforced(serotonin_cls, tmp_path: Path):
    """Test that config field constraints (ge, le, gt) are enforced."""
    invalid_config = tmp_path / "invalid_constraints.yaml"

    # Config with value outside allowed range (alpha should be >= 0.0)
    invalid_body = {
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


def test_risk_budget_monotone_in_stress(serotonin_controller):
    budgets: list[float] = []
    for stress in (0.0, 0.5, 1.0, 2.0):
        budget, _ = serotonin_controller._derive_risk_budget(
            serotonin_controller.serotonin_level, stress
        )
        budgets.append(budget)
    assert budgets == sorted(budgets, reverse=True)


def test_serotonin_signal_stays_bounded(serotonin_controller):
    val = serotonin_controller.compute_serotonin_signal(1e6)
    assert 0.0 <= val <= 1.0
    assert math.isfinite(val)
