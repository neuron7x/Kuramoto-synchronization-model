from __future__ import annotations

import math
from pathlib import Path
from typing import Tuple

import pytest

from tradepulse.core.neuro.dopamine import DopamineController
from tradepulse.core.neuro.dopamine.ddm_adapter import DDMThresholds


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
