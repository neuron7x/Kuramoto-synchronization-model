from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

from tradepulse.core.neuro.dopamine import DopamineController, dopamine_step


@pytest.fixture
def config_dict() -> Dict[str, object]:
    return {
        "version": "2.2.0",
        "discount_gamma": 0.98,
        "learning_rate_v": 0.1,
        "decay_rate": 0.05,
        "burst_factor": 2.5,
        "k": 1.0,
        "theta": 0.5,
        "w_r": 0.60,
        "w_n": 0.20,
        "w_m": 0.15,
        "w_v": 0.20,
        "novelty_mode": "abs_rpe",
        "c_absrpe": 0.10,
        "baseline": 0.5,
        "delta_gain": 0.5,
        "base_temperature": 1.0,
        "min_temperature": 0.05,
        "temp_k": 1.2,
        "neg_rpe_temp_gain": 0.5,
        "max_temp_multiplier": 3.0,
        "invigoration_threshold": 0.75,
        "no_go_threshold": 0.25,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "meta_cooldown_ticks": 0,
        "metric_interval": 1,
        "meta_adapt_rules": {
            "good": {
                "learning_rate_v": 1.01,
                "delta_gain": 1.01,
                "base_temperature": 0.99,
            },
            "bad": {
                "learning_rate_v": 0.99,
                "delta_gain": 0.99,
                "base_temperature": 1.01,
            },
            "neutral": {
                "learning_rate_v": 1.0,
                "delta_gain": 1.0,
                "base_temperature": 1.0,
            },
        },
    }


@pytest.fixture
def controller(tmp_path: Path, config_dict: Dict[str, object]) -> DopamineController:
    cfg_path = tmp_path / "dopamine.yaml"
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_dict, f)

    metrics: Dict[str, List[float]] = {}

    def stub_logger(name: str, value: float) -> None:
        metrics.setdefault(name, []).append(value)

    ctrl = DopamineController(str(cfg_path), logger=stub_logger)
    ctrl._captured_metrics = metrics  # type: ignore[attr-defined]
    return ctrl


def test_dopamine_step_executes_full_pipeline(controller: DopamineController) -> None:
    cfg_before = dict(controller.config)
    result = dopamine_step(
        ctrl=controller,
        reward=0.2,
        value=0.1,
        next_value=0.3,
        reward_proxy=1.0,
        novelty=0.2,
        momentum=0.1,
        value_gap=0.05,
        original_q=2.0,
        performance_metrics={"drawdown": -0.04, "sharpe": 1.1},
    )

    expected_rpe = 0.2 + cfg_before["discount_gamma"] * 0.3 - 0.1
    assert result["rpe"] == pytest.approx(expected_rpe, rel=1e-6)

    expected_value_estimate = 0.0 + cfg_before["learning_rate_v"] * expected_rpe
    assert result["value_estimate"] == pytest.approx(expected_value_estimate, rel=1e-6)

    novelty_eff = 0.2 + cfg_before["c_absrpe"] * abs(expected_rpe)
    appetitive = (
        cfg_before["w_r"] * 1.0
        + cfg_before["w_n"] * novelty_eff
        + cfg_before["w_m"] * 0.1
        + cfg_before["w_v"] * 0.05
    )
    phasic = max(0.0, expected_rpe) * cfg_before["burst_factor"]
    tonic = (1 - cfg_before["decay_rate"]) * 0.0 + cfg_before["decay_rate"] * (
        appetitive + phasic
    )
    x = cfg_before["k"] * (tonic - cfg_before["theta"])
    expected_da = 1.0 / (1.0 + math.exp(-max(min(x, 60.0), -60.0)))
    assert result["dopamine"] == pytest.approx(expected_da, rel=1e-6)

    expected_q = 2.0 * (
        1.0 + cfg_before["delta_gain"] * (expected_da - cfg_before["baseline"])
    )
    assert result["q_modulated"] == pytest.approx(expected_q, rel=1e-6)

    expected_temp = cfg_before["base_temperature"] * math.exp(
        -cfg_before["temp_k"] * expected_da
    )
    assert result["temperature"] == pytest.approx(expected_temp, rel=1e-6)

    assert result["go"] is (expected_da > cfg_before["invigoration_threshold"])
    assert result["no_go"] is (expected_da < cfg_before["no_go_threshold"])
    assert result["hold"] is (not result["go"] and not result["no_go"])

    assert controller.config["learning_rate_v"] == pytest.approx(
        cfg_before["learning_rate_v"] * 1.01, rel=1e-6
    )
    assert controller.config["delta_gain"] == pytest.approx(
        cfg_before["delta_gain"] * 1.01, rel=1e-6
    )
    assert controller.config["base_temperature"] == pytest.approx(
        cfg_before["base_temperature"] * 0.99, rel=1e-6
    )

    metrics = controller._captured_metrics  # type: ignore[attr-defined]
    assert "dopamine_temperature" in metrics
    logged_temp = metrics["dopamine_temperature"][-1]
    expected_logged_temp = controller.config["base_temperature"] * math.exp(
        -controller.config["temp_k"] * controller.dopamine_level
    )
    assert logged_temp == pytest.approx(expected_logged_temp, rel=1e-6)


def test_dopamine_step_allows_gamma_override(controller: DopamineController) -> None:
    result = dopamine_step(
        ctrl=controller,
        reward=1.0,
        value=0.5,
        next_value=0.25,
        reward_proxy=0.2,
        novelty=0.0,
        momentum=0.0,
        value_gap=0.0,
        original_q=0.0,
        discount_gamma=0.5,
    )

    assert result["rpe"] == pytest.approx(1.0 + 0.5 * 0.25 - 0.5, rel=1e-6)


def test_meta_adapt_requires_expected_metrics(controller: DopamineController) -> None:
    with pytest.raises(
        ValueError, match="performance_metrics is missing required keys"
    ):
        dopamine_step(
            ctrl=controller,
            reward=0.0,
            value=0.0,
            next_value=0.0,
            reward_proxy=0.0,
            novelty=0.0,
            momentum=0.0,
            value_gap=0.0,
            original_q=0.0,
            performance_metrics={"drawdown": 0.0},
        )
