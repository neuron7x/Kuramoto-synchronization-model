from __future__ import annotations

import random

import pytest

from tradepulse.core.neuro.dopamine.dopamine_controller import DopamineController
from tradepulse.core.neuro.gaba.gaba_inhibition_gate import GABAInhibitionGate
from tradepulse.core.neuro.na_ach.neuromods import NAACHNeuromodulator
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController
from tradepulse.policy.basal_ganglia import (
    BasalGangliaDecisionStack,
    BasalGangliaPolicy,
    select_action,
)


@pytest.fixture(autouse=True)
def _seed() -> None:
    random.seed(7)


@pytest.fixture
def stack() -> BasalGangliaDecisionStack:
    return BasalGangliaDecisionStack()


def test_serotonin_hold_suppresses_go(stack: BasalGangliaDecisionStack) -> None:
    """High stress should force HOLD even with positive Q-values."""
    q_values = {"long": 1.0, "short": -0.2}
    constraints = {
        "reward": 0.05,
        "value": 0.8,
        "next_value": 0.85,
        "novelty": 0.1,
        "stress": 1.0,
        "drawdown": 0.6,
        "impulse": 0.1,
        "volatility": 0.4,
    }

    result = None
    for _ in range(3):
        result = stack.select_action(q_values, constraints)
    assert result is not None
    assert result.decision != "GO", "Serotonin HOLD veto should suppress GO decision"
    assert result.extras["serotonin"]["hold"] >= 0.5


def test_gaba_inhibition_prevents_impulsive_trades(
    stack: BasalGangliaDecisionStack,
) -> None:
    """Repeated impulses increase GABA inhibition reducing GO probability."""
    q_values = {"long": 0.9, "flat": 0.2}
    constraints = {
        "reward": 0.02,
        "value": 0.6,
        "next_value": 0.62,
        "novelty": 0.2,
        "stress": 0.2,
        "drawdown": 0.0,
        "volatility": 0.3,
    }

    # warm-up with moderate impulse
    constraints["impulse"] = 0.3
    stack.select_action(q_values, constraints)

    # apply strong impulse burst over several ticks
    constraints["impulse"] = 1.0
    result = None
    for _ in range(5):
        result = stack.select_action(q_values, constraints)
    assert result is not None
    inhibition = result.extras["gaba"]["inhibition"]
    assert inhibition > 0.1
    assert result.decision != "GO", "High inhibition should reduce GO probability"


def test_policy_temperature_remains_bounded_under_noise() -> None:
    ctrl = DopamineController("configs/dopamine.yaml")
    value = 0.5
    for _ in range(120):
        reward = random.uniform(-0.1, 0.1)
        next_value = random.uniform(0.4, 0.6)
        appetitive = ctrl.estimate_appetitive_state(
            abs(reward), 0.2, 0.1, abs(next_value - value)
        )
        ctrl.step(
            reward=reward,
            value=value,
            next_value=next_value,
            appetitive_state=appetitive,
            policy_logits=[0.3, 0.6],
        )
        temp = ctrl.compute_temperature()
        low, high = ctrl.temperature_bounds()
        assert low <= temp <= high
        value = next_value


def test_na_risk_budget_scales_with_volatility() -> None:
    neuromod = NAACHNeuromodulator("configs/na_ach.yaml")
    low = neuromod.update(volatility=0.3, novelty=0.1)
    high = neuromod.update(volatility=1.1, novelty=0.5)
    assert high["risk_multiplier"] > low["risk_multiplier"]
    assert high["temperature_scale"] < low["temperature_scale"]


def test_serotonin_hysteresis_and_release() -> None:
    ctrl = SerotoninController("configs/serotonin.yaml")
    state = {}
    for _ in range(4):
        state = ctrl.step(stress=1.0, drawdown=0.5, novelty=0.3)
    assert state["hold"] >= 0.5
    desens_before = state["desensitization"]
    # Need enough steps for the level to decay below release threshold AND
    # for the cooldown period (3 ticks) to expire
    for _ in range(10):
        state = ctrl.step(stress=0.0, drawdown=0.0, novelty=0.0)
    assert state["hold"] < 0.5
    assert ctrl.temperature_floor >= ctrl.config.floor_min
    assert ctrl.temperature_floor <= ctrl.config.floor_max
    assert state["desensitization"] <= desens_before


def test_select_action_module_level_api(stack: BasalGangliaDecisionStack) -> None:
    q_values = {"long": 0.9, "flat": 0.3}
    constraints = {
        "reward": 0.03,
        "value": 0.7,
        "next_value": 0.75,
        "novelty": 0.25,
        "stress": 0.3,
        "drawdown": 0.05,
        "impulse": 0.15,
        "volatility": 0.4,
    }
    direct = stack.select_action(q_values, constraints)
    via_api = select_action(q_values, constraints)
    assert isinstance(via_api, dict)
    assert via_api["decision"] == direct.decision
    assert pytest.approx(via_api["score"], rel=1e-6) == direct.score


def test_basal_ganglia_reset_and_gates(stack: BasalGangliaDecisionStack) -> None:
    stack.select_action(
        [0.1, 0.2], {"reward": 0.0, "value": 0.2, "next_value": 0.2, "volatility": 0.3}
    )
    stack.reset()
    assert stack.dopamine.last_rpe == 0.0
    result = stack.select_action(
        [0.4, 0.3],
        {"reward": 0.1, "value": 0.4, "next_value": 0.45, "volatility": 0.4},
        gates={"ddm_params": (0.2, 1.0, 0.1)},
    )
    assert "input_gates" in result.extras


def test_gaba_reset_and_validation(tmp_path) -> None:
    cfg_path = tmp_path / "bad.yaml"
    cfg_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        GABAInhibitionGate(str(cfg_path))

    gate = GABAInhibitionGate("configs/gaba.yaml")
    gate.update(0.5, dt=1.0, rpe=0.1, stress=0.2)
    gate.reset()
    state = gate.to_dict()
    assert state["inhibition"] == 0.0
    with pytest.raises(ValueError):
        gate.update(0.1, dt=0.0)


def test_serotonin_config_validation(tmp_path) -> None:
    cfg_path = tmp_path / "invalid.yaml"
    cfg_path.write_text("{tonic_beta: 1.1}", encoding="utf-8")
    with pytest.raises(ValueError):
        SerotoninController(str(cfg_path))


def test_legacy_policy_paths() -> None:
    policy = BasalGangliaPolicy()
    go = policy.decide({"R": 0.9}, "EMERGENT", "OK")
    hold = policy.decide({}, "CAUTION", "OK")
    no_go = policy.decide({}, "KILL", "OK")
    assert go[0] == "GO" and no_go[0] == "NO_GO" and hold[0] == "HOLD"
