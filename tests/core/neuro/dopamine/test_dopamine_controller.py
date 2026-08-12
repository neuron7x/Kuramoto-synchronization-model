# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

import pytest

from geosync.core.neuro.dopamine import DopamineController
from geosync.core.neuro.dopamine.ddm_adapter import DDMThresholds

CONFIG_PATH = Path("config/dopamine.yaml")


@pytest.fixture()
def controller(tmp_path: Path) -> DopamineController:
    cfg_target = tmp_path / "dopamine.yaml"
    cfg_target.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return DopamineController(str(cfg_target))


def _appetitive(ctrl: DopamineController) -> float:
    return ctrl.estimate_appetitive_state(0.4, 0.2, 0.1, 0.05)


def _policy_logits() -> Tuple[float, ...]:
    return (0.15, -0.05, 0.32)


def test_step_rpe_and_release_gate(controller: DopamineController) -> None:
    rpe, temperature, scaled_policy, extras = controller.step(
        reward=1.0,
        value=0.4,
        next_value=0.45,
        appetitive_state=_appetitive(controller),
        policy_logits=_policy_logits(),
        ddm_params=(0.9, 1.1, 0.2),
    )

    assert rpe > 0.0
    assert temperature == pytest.approx(extras["temperature"])
    assert len(scaled_policy) == len(_policy_logits())
    assert all(math.isfinite(x) for x in scaled_policy)
    assert isinstance(extras["release_gate_open"], bool)
    assert extras["dopamine_level"] <= 1.0
    assert isinstance(extras["ddm_thresholds"], DDMThresholds)


def test_step_extras_structure(controller: DopamineController) -> None:
    appetitive = _appetitive(controller)
    rpe, temperature, scaled_policy, extras = controller.step(
        reward=0.5,
        value=0.2,
        next_value=0.25,
        appetitive_state=appetitive,
        policy_logits=_policy_logits(),
    )

    # Updated field names as per v1.0 spec
    expected_keys = {
        "dopamine_level",
        "da_tonic",  # renamed from tonic_level
        "da_phasic",  # renamed from phasic_level
        "value_estimate",
        "rpe_var",  # renamed from rpe_variance
        "rpe",  # added in v1.0
        "release_gate_open",
        "go",
        "hold",
        "no_go",
        "go_threshold",
        "no_go_threshold",
        "hold_threshold",
        "adaptive_base_temperature",
        "temperature",
    }
    assert expected_keys.issubset(extras)
    assert extras["temperature"] == pytest.approx(temperature)
    assert scaled_policy == tuple(
        controller.modulate_action_value(v, dopamine_signal=extras["dopamine_level"])
        for v in _policy_logits()
    )


def test_temperature_stability(controller: DopamineController) -> None:
    appetitive = _appetitive(controller)
    last_temp = None
    for _ in range(32):
        min_temp, max_temp = controller.temperature_bounds()
        rpe, temperature, _, extras = controller.step(
            reward=0.0,
            value=0.0,
            next_value=0.0,
            appetitive_state=appetitive,
            policy_logits=_policy_logits(),
            ddm_params=(0.1, 1.0, 0.2),
        )
        assert -1e-6 < rpe < 1e-6
        assert min_temp <= temperature <= max_temp
        last_temp = temperature
        assert extras["release_gate_open"] is True

    assert last_temp is not None


@pytest.mark.parametrize("reward", [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0])
def test_td0_rpe_property(tmp_path: Path, reward: float) -> None:
    cfg_target = tmp_path / "dopamine.yaml"
    if not cfg_target.exists():
        cfg_target.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    ctrl = DopamineController(str(cfg_target))
    baseline = 0.8
    rpe = ctrl.compute_rpe(reward, baseline, baseline, discount_gamma=1.0)
    assert rpe == pytest.approx(reward)
    if reward != 0.0:
        assert math.copysign(1.0, rpe) == math.copysign(1.0, reward)


def test_release_gate_reacts_to_variance(controller: DopamineController) -> None:
    controller.reset_state()
    controller.config["rpe_ema_beta"] = 0.2
    controller.config["rpe_var_release_threshold"] = 0.55
    controller.config["rpe_var_release_hysteresis"] = 0.0
    appetitive = _appetitive(controller)

    rpe_high, _, _, extras_high = controller.step(
        reward=2.0,
        value=0.0,
        next_value=0.0,
        appetitive_state=appetitive,
        policy_logits=_policy_logits(),
    )
    assert rpe_high > 0.0
    assert extras_high["release_gate_open"] is False
    assert extras_high["hold"] is True

    rpe_low, _, _, extras_low = controller.step(
        reward=0.0,
        value=controller.value_estimate,
        next_value=controller.value_estimate,
        appetitive_state=appetitive,
        policy_logits=_policy_logits(),
    )
    assert abs(rpe_low) < 1e-2
    assert extras_low["release_gate_open"] is True


def test_meta_temperature_adaptation_increases_base(
    controller: DopamineController,
) -> None:
    controller.reset_state()
    controller.config["temp_adapt_lr"] = 0.2
    controller.config["temp_adapt_beta1"] = 0.5
    controller.config["temp_adapt_beta2"] = 0.5
    controller.config["temp_adapt_target_var"] = 0.0
    controller.config["temp_adapt_epsilon"] = 1e-6
    controller.config["temp_adapt_min_base"] = 0.1
    controller.config["temp_adapt_max_base"] = 5.0

    base_before = controller.config["base_temperature"]
    appetitive = _appetitive(controller)

    _, _, _, extras = controller.step(
        reward=1.5,
        value=0.0,
        next_value=0.0,
        appetitive_state=appetitive,
        policy_logits=_policy_logits(),
    )

    assert extras["adaptive_base_temperature"] > base_before
    assert controller.config["base_temperature"] == extras["adaptive_base_temperature"]
