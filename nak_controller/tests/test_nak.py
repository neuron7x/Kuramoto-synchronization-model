"""Unit and property-based tests for the NaK controller.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from hypothesis import given, settings
from hypothesis import strategies as st

from nak_controller.cli.run_validate import main as validate_main
from nak_controller.conf.schema import load_nak_params
from nak_controller.control.global_mode import choose_mode
from nak_controller.control.neuromods import dopamine, noradrenaline, serotonin
from nak_controller.integration.hook import NaKHook

CFG = Path(__file__).resolve().parent.parent / "conf" / "nak.yaml"


def _local_obs(**overrides: float) -> dict[str, float]:
    payload = dict(
        trades=0.6,
        pnl=0.001,
        pnl_scale=0.01,
        local_vol=0.3,
        local_dd=0.1,
        tech_errors=0.0,
        latency=0.3,
        slippage=0.0005,
        glial_support=0.0,
    )
    payload.update(overrides)
    return payload


def _global_obs(**overrides: float) -> dict[str, float]:
    payload = dict(global_vol=0.3, portfolio_dd=0.1, exposure=1.0, unexpected_reward=0.0)
    payload.update(overrides)
    return payload


class TestNaKController(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = NaKHook(str(CFG), seed=1234)

    def test_bounds_and_invariants(self) -> None:
        out = self.hook.compute_limits("s1", _local_obs(), _global_obs(), 0.002, 1.0, 2000)
        self.assertTrue(0.0 <= out.EI <= 1.0)
        self.assertTrue(self.hook.ctrl.p.r_min - 1e-9 <= out.risk_per_trade_factor <= self.hook.ctrl.p.r_max + 1e-9)
        self.assertEqual(out.risk_per_trade_factor, out.max_position_factor)
        min_cd = math.floor(2000 / self.hook.ctrl.p.f_max)
        self.assertGreaterEqual(out.cooldown_ms, min_cd)

    def test_modes_and_hysteresis(self) -> None:
        red = self.hook.compute_limits(
            "s1",
            _local_obs(pnl=-0.002, trades=0.9, local_vol=0.95),
            _global_obs(global_vol=0.95, portfolio_dd=0.75),
            0.002,
            1.0,
            2000,
        )
        self.assertEqual(red.mode, "RED")
        self.assertTrue(red.is_suspended or math.isclose(self.hook.ctrl.p.risk_RED, 0.0))

        self.hook.ctrl.reset(seed=4321)
        recovered = None
        for _ in range(6):
            recovered = self.hook.compute_limits(
                "s1",
                _local_obs(pnl=0.003, trades=0.3, local_vol=0.1, local_dd=0.02),
                _global_obs(global_vol=0.2, portfolio_dd=0.05),
                0.002,
                1.0,
                2000,
            )
        assert recovered is not None
        self.assertGreaterEqual(recovered.EI, self.hook.ctrl.p.EI_crit)

    def test_rate_limit(self) -> None:
        self.hook.reset(seed=999)
        first = self.hook.compute_limits("s1", _local_obs(pnl=0.005), _global_obs(), 0.002, 1.0, 2000)
        second = self.hook.compute_limits("s1", _local_obs(pnl=0.005, trades=0.0), _global_obs(), 0.002, 1.0, 2000)
        delta = abs(second.risk_per_trade_factor - first.risk_per_trade_factor)
        self.assertLessEqual(delta, self.hook.ctrl.p.delta_r_limit + 1e-6)

    def test_frequency_logic(self) -> None:
        o1 = self.hook.compute_limits("s1", _local_obs(local_vol=0.2), _global_obs(global_vol=0.3), 0.002, 1.0, 2000)
        o2 = self.hook.compute_limits("s1", _local_obs(local_vol=0.8), _global_obs(global_vol=0.8), 0.002, 1.0, 2000)
        self.assertNotEqual(o1.cooldown_ms, o2.cooldown_ms)

    def test_neuromodulator_monotonicity(self) -> None:
        self.assertGreater(dopamine(0.2, beta_DA=0.8), dopamine(0.0, beta_DA=0.8))
        self.assertGreater(noradrenaline(0.9, na_vol_gain=1.0), noradrenaline(0.2, na_vol_gain=1.0))
        self.assertGreater(serotonin(0.7, ht_dd_gain=1.0), serotonin(0.2, ht_dd_gain=1.0))

    def test_reset_is_deterministic(self) -> None:
        self.hook.reset(seed=4242)
        first = self.hook.compute_limits("s1", _local_obs(), _global_obs(), 0.002, 1.0, 2000)
        self.hook.reset(seed=4242)
        second = self.hook.compute_limits("s1", _local_obs(), _global_obs(), 0.002, 1.0, 2000)
        self.assertEqual(first.as_dict(), second.as_dict())

    def test_cli_emits_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = validate_main(["--config", str(CFG), "--steps", "10", "--seeds", "1"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(buf.getvalue())
        self.assertIn("nak", payload)
        self.assertIn("baseline", payload)

    def test_config_validation_rejects_invalid_bounds(self) -> None:
        raw = yaml.safe_load(CFG.read_text(encoding="utf-8"))
        raw["nak"]["EI_low"] = 0.9
        raw["nak"]["EI_high"] = 0.2
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nak.yaml"
            path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_nak_params(path)


@settings(max_examples=60, deadline=None)
@given(
    trades=st.floats(min_value=0.0, max_value=1.0),
    pnl=st.floats(min_value=-0.01, max_value=0.01),
    local_vol=st.floats(min_value=0.0, max_value=1.0),
    local_dd=st.floats(min_value=0.0, max_value=1.0),
    global_vol=st.floats(min_value=0.0, max_value=1.0),
    portfolio_dd=st.floats(min_value=0.0, max_value=1.0),
)
def test_invariants_hold_under_random_inputs(
    trades: float,
    pnl: float,
    local_vol: float,
    local_dd: float,
    global_vol: float,
    portfolio_dd: float,
) -> None:
    hook = NaKHook(str(CFG), seed=777)
    out = hook.compute_limits(
        "hypo",
        _local_obs(trades=trades, pnl=pnl, local_vol=local_vol, local_dd=local_dd),
        _global_obs(global_vol=global_vol, portfolio_dd=portfolio_dd),
        0.002,
        1.0,
        2000,
    )
    p = hook.ctrl.p
    assert 0.0 <= out.EI <= 1.0
    assert p.r_min - 1e-9 <= out.risk_per_trade_factor <= p.r_max + 1e-9
    assert math.isclose(out.risk_per_trade_factor, out.max_position_factor, rel_tol=1e-9, abs_tol=1e-9)
    assert out.cooldown_ms >= math.floor(2000 / p.f_max)
    mode = choose_mode(global_vol, portfolio_dd, p.vol_amber, p.vol_red, p.dd_amber, p.dd_red)
    if mode == "RED":
        assert out.is_suspended or math.isclose(p.risk_RED, 0.0)

