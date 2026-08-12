# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Dict, cast

import numpy as np
import pytest
import yaml  # type: ignore[import-untyped]

from nak_controller.control.pi import rate_limit
from nak_controller.core.energetics import update_energy, update_load
from nak_controller.core.metrics import pnl_norm
from nak_controller.core.state import StrategyState, clip
from nak_controller.integration.hook import NaKHook
from nak_controller.runtime.controller import NaKController

CONFIG_PATH = Path("nak_controller/conf/nak.yaml")


def _default_inputs() -> tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    local = {
        "trades": 0.55,
        "pnl": 0.001,
        "pnl_scale": 0.01,
        "local_vol": 0.35,
        "local_dd": 0.2,
        "tech_errors": 0.05,
        "latency": 0.25,
        "slippage": 0.0005,
        "glial_support": 0.45,
    }
    global_obs = {
        "global_vol": 0.4,
        "portfolio_dd": 0.25,
        "exposure": 0.75,
        "unexpected_reward": 0.1,
    }
    bases = {"cooldown_ms_base": 2000.0}
    return local, global_obs, bases


def test_controller_seed_reproducibility() -> None:
    controller_a = NaKController(CONFIG_PATH, seed=1337)
    controller_b = NaKController(CONFIG_PATH, seed=1337)
    local, global_obs, bases = _default_inputs()

    out_a = controller_a.step("s", local, global_obs, bases)
    out_b = controller_b.step("s", local, global_obs, bases)

    for key in ("risk_per_trade_factor", "max_position_factor", "cooldown_ms", "EI"):
        assert pytest.approx(out_a[key], rel=1e-9, abs=1e-9) == out_b[key]


def test_controller_reset_with_seed_rewinds_rng() -> None:
    controller = NaKController(CONFIG_PATH, seed=7)
    local, global_obs, bases = _default_inputs()
    first = controller.step("s", local, global_obs, bases)

    second = controller.step("s", local, global_obs, bases)
    assert second["risk_per_trade_factor"] != first["risk_per_trade_factor"]

    controller.reset()
    assert controller.states == {}
    replay = controller.step("s", local, global_obs, bases)
    assert (
        pytest.approx(replay["risk_per_trade_factor"], rel=1e-9) == first["risk_per_trade_factor"]
    )

    controller.reset(seed=2024)
    after_reset = controller.step("s", local, global_obs, bases)
    fresh = NaKController(CONFIG_PATH, seed=2024).step("s", local, global_obs, bases)

    assert (
        pytest.approx(after_reset["risk_per_trade_factor"], rel=1e-9)
        == fresh["risk_per_trade_factor"]
    )


def test_hook_seed_property_tracks_resets() -> None:
    hook = NaKHook(CONFIG_PATH, seed=12)
    assert hook.seed == 12
    hook.reset(seed=21)
    assert hook.seed == 21


def test_update_load_uses_supplied_rng() -> None:
    controller = NaKController(CONFIG_PATH, seed=42)
    params = controller.params
    state = StrategyState()
    local = {
        "trades": 0.4,
        "local_vol": 0.5,
        "local_dd": 0.1,
        "tech_errors": 0.05,
        "latency": 0.1,
        "slippage": 0.0004,
    }
    rng = np.random.default_rng(91)
    bit_state = rng.bit_generator.state
    sigma = params.noise_sigma * max(1e-9, float(local["local_vol"]))
    expected_noise = rng.normal(0.0, sigma)
    rng.bit_generator.state = bit_state

    expected = clip(
        state.L
        + params.w_n * local["trades"]
        + params.w_v * local["local_vol"] * (1.0 - params.na_scale * 0.0)
        + params.w_d * local["local_dd"]
        + params.w_e * local["tech_errors"]
        + params.w_l * local["latency"]
        + params.w_s * local["slippage"]
        + expected_noise,
        params.L_min,
        params.L_max,
    )

    observed = update_load(state, params, dict(local), NA=0.0, rng=rng)
    assert observed == pytest.approx(expected)


def test_hysteresis_requires_recovery_to_exit_suspend() -> None:
    hook = NaKHook(CONFIG_PATH, seed=111)
    local, global_obs, bases = _default_inputs()

    # Force RED mode and suspension.
    red_obs = dict(local, local_vol=0.95, local_dd=0.9, trades=0.9, pnl=-0.01)
    red_global = dict(global_obs, global_vol=0.95, portfolio_dd=0.85)
    first = hook.compute_limits("strat", red_obs, red_global, 0.002, 1.0, 2000.0)
    assert first["mode"] == "RED"
    assert first["is_suspended"]

    # Gradual recovery keeps suspension because EI below hysteresis threshold.
    amber_obs = dict(
        local,
        pnl=-0.002,
        glial_support=0.0,
        local_vol=0.62,
        local_dd=0.58,
        trades=0.7,
        tech_errors=0.25,
        latency=0.4,
    )
    amber_global = dict(global_obs, global_vol=0.58, portfolio_dd=0.5)
    second = hook.compute_limits("strat", amber_obs, amber_global, 0.002, 1.0, 2000.0)
    assert second["mode"] in {"GREEN", "AMBER"}
    assert second["is_suspended"]

    # Strong recovery should exit suspension.
    green_obs = dict(local, pnl=0.004, local_vol=0.2, local_dd=0.05, trades=0.2)
    green_global = dict(global_obs, global_vol=0.2, portfolio_dd=0.05)
    third = hook.compute_limits("strat", green_obs, green_global, 0.002, 1.0, 2000.0)
    assert third["mode"] == "GREEN"
    assert not third["is_suspended"]


def test_rate_limit_caps_delta() -> None:
    assert rate_limit(None, 0.8, limit=0.1, lo=0.0, hi=1.0) == pytest.approx(0.8)
    assert rate_limit(0.5, 0.9, limit=0.1, lo=0.0, hi=1.0) == pytest.approx(0.6)
    assert rate_limit(0.5, 0.0, limit=0.1, lo=0.0, hi=1.0) == pytest.approx(0.4)


def test_update_energy_includes_unexpected_reward() -> None:
    controller = NaKController(CONFIG_PATH, seed=3)
    params = controller.params
    state = StrategyState()
    obs = {
        "pnl": 0.003,
        "pnl_scale": 0.01,
        "trades": 0.4,
        "local_vol": 0.5,
        "glial_support": 0.3,
    }
    NA = 0.2
    DA = 0.7
    da_unexp = 0.4

    energy_expected = clip(
        state.E
        + params.a_p * pnl_norm(obs["pnl"], scale=obs["pnl_scale"])
        - params.a_n * obs["trades"]
        - params.a_v * obs["local_vol"] * (1.0 - params.na_scale * NA)
        + params.a_g * obs["glial_support"]
        + params.a_da * da_unexp
        + 0.05 * (1.0 - min(1.0, state.debt)),
        0.0,
        params.E_max,
    )

    energy_observed = update_energy(state, params, dict(obs), NA=NA, DA=DA, da_unexp=da_unexp)
    assert energy_observed == pytest.approx(energy_expected)


def test_update_energy_tracks_debt_when_negative() -> None:
    controller = NaKController(CONFIG_PATH, seed=4)
    params = controller.params
    state = StrategyState(E=0.05)
    obs: Dict[str, float] = {
        "pnl": -0.01,
        "pnl_scale": 0.01,
        "trades": 1.0,
        "local_vol": 1.0,
        "glial_support": 0.0,
    }
    update_energy(state, params, obs, NA=0.0, DA=0.4, da_unexp=0.0)
    assert state.E == pytest.approx(0.0)
    assert state.debt > 0.0


def test_hook_scales_limit_outputs() -> None:
    hook = NaKHook(CONFIG_PATH, seed=21)
    local, global_obs, bases = _default_inputs()
    response = hook.compute_limits("scale", local, global_obs, 0.01, 5.0, 1500.0)
    risk_factor = cast(float, response["risk_per_trade_factor"])
    max_factor = cast(float, response["max_position_factor"])
    assert response["risk_per_trade"] == pytest.approx(risk_factor * 0.01)
    assert response["max_position"] == pytest.approx(max_factor * 5.0)


def test_logger_emits_info_when_enabled(caplog: pytest.LogCaptureFixture) -> None:
    controller = NaKController(CONFIG_PATH, seed=8)
    local, global_obs, bases = _default_inputs()
    with caplog.at_level(logging.INFO, logger="runtime.telemetry.nak"):
        controller.step("log", local, global_obs, bases)
    assert any(record.message == "nak.step" for record in caplog.records)


def test_controller_uses_seed_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAK_SEED", "2001")
    local, global_obs, bases = _default_inputs()
    env_controller = NaKController(CONFIG_PATH)
    env_result = env_controller.step("env", local, global_obs, bases)
    monkeypatch.delenv("NAK_SEED", raising=False)
    direct = NaKController(CONFIG_PATH, seed=2001).step("env", local, global_obs, bases)
    assert env_result["risk_per_trade_factor"] == pytest.approx(direct["risk_per_trade_factor"])


def test_controller_rejects_invalid_seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAK_SEED", "invalid-seed")
    with pytest.raises(ValueError):
        NaKController(CONFIG_PATH)


def test_hook_reads_seed_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAK_SEED", "2020")
    hook = NaKHook(CONFIG_PATH)
    assert hook.seed == 2020
    assert hook.config_path == CONFIG_PATH
    monkeypatch.delenv("NAK_SEED", raising=False)


def test_hook_rejects_invalid_seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAK_SEED", "bad-seed")
    with pytest.raises(ValueError):
        NaKHook(CONFIG_PATH)


def test_reset_without_seed_uses_random_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NAK_SEED", raising=False)
    controller = NaKController(CONFIG_PATH)
    local, global_obs, bases = _default_inputs()
    controller.reset()
    assert controller._seed is None
    assert controller.states == {}
    first_state = copy.deepcopy(controller._rng.bit_generator.state)
    controller.reset()
    second_state = controller._rng.bit_generator.state
    assert first_state != second_state


def test_step_raises_when_rate_limit_out_of_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = NaKController(CONFIG_PATH, seed=9)

    def fake_rate_limit(*args: object, **kwargs: object) -> float:
        return controller.params.r_max + 1.0

    monkeypatch.setattr("nak_controller.runtime.controller.rate_limit", fake_rate_limit)
    local, global_obs, bases = _default_inputs()
    with pytest.raises(RuntimeError, match="risk_factor"):
        controller.step("oops", local, global_obs, bases)


def test_step_raises_when_red_mode_not_suspended(tmp_path: Path) -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["nak"]["risk_mult"]["RED"] = 0.2
    path = tmp_path / "nak_red.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    controller = NaKController(path, seed=13)
    local, global_obs, bases = _default_inputs()
    bullish_local = dict(
        local,
        pnl=0.004,
        glial_support=0.6,
        local_vol=0.2,
        local_dd=0.05,
        trades=0.2,
    )
    stressed_global = dict(global_obs, global_vol=0.95, portfolio_dd=0.85)

    with pytest.raises(RuntimeError, match="RED mode must result in suspension"):
        controller.step("red", bullish_local, stressed_global, bases)
