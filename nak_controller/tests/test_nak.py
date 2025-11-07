"""Integration-style tests covering the NaK control loop."""
from __future__ import annotations

import unittest
from typing import Any, Dict, cast

from nak_controller.conf import DEFAULT_CONFIG_PATH
from nak_controller.integration.hook import NaKHook

CONFIG_PATH = str(DEFAULT_CONFIG_PATH)


class NaKControllerTest(unittest.TestCase):
    """Exercise controller invariants under representative scenarios."""

    def setUp(self) -> None:
        self.hook = NaKHook(CONFIG_PATH)
        self.hook.reset()
        self.params = self.hook._controller.p

    def _step(self, **kwargs: float) -> Dict[str, Any]:
        local = dict(
            trades=kwargs.get("trades", 0.6),
            pnl=kwargs.get("pnl", 0.001),
            pnl_scale=0.01,
            local_vol=kwargs.get("local_vol", 0.3),
            local_dd=kwargs.get("local_dd", 0.1),
            tech_errors=kwargs.get("tech_errors", 0.0),
            latency=kwargs.get("latency", 0.3),
            slippage=kwargs.get("slippage", 0.0005),
            glial_support=kwargs.get("glial_support", 0.0),
        )
        global_obs = dict(
            global_vol=kwargs.get("global_vol", 0.3),
            portfolio_dd=kwargs.get("portfolio_dd", 0.1),
            exposure=kwargs.get("exposure", 1.0),
            unexpected_reward=kwargs.get("unexpected_reward", 0.0),
        )
        return self.hook.compute_limits(
            "s1",
            local,
            global_obs,
            base_risk_per_trade=0.002,
            base_max_position=1.0,
            base_cooldown_ms=2000,
        )

    def test_bounds_and_invariants(self) -> None:
        out = self._step()
        ei = cast(float, out["EI"])
        risk_factor = cast(float, out["risk_per_trade_factor"])
        maxpos_factor = cast(float, out["max_position_factor"])
        cooldown = cast(int, out["cooldown_ms"])
        self.assertGreaterEqual(ei, 0.0)
        self.assertLessEqual(ei, 1.0)
        self.assertGreaterEqual(risk_factor, self.params.r_min)
        self.assertLessEqual(risk_factor, self.params.r_max)
        self.assertEqual(maxpos_factor, risk_factor)
        self.assertGreaterEqual(cooldown, 1)

    def test_modes_and_hysteresis(self) -> None:
        out_red = self._step(
            global_vol=0.95,
            portfolio_dd=0.75,
            pnl=-0.002,
            trades=0.9,
            local_vol=0.95,
        )
        self.assertEqual(cast(str, out_red["mode"]), "RED")
        self.assertTrue(bool(out_red["is_suspended"]))

        unsuspend_threshold = self.params.EI_crit + self.params.EI_hysteresis
        recovered: Dict[str, Any] | None = None
        for _ in range(12):
            candidate = self._step(
                global_vol=0.2,
                portfolio_dd=0.02,
                pnl=0.003,
                trades=0.2,
                local_vol=0.1,
            )
            if not bool(candidate["is_suspended"]):
                recovered = candidate
                break
        self.assertIsNotNone(recovered, "Controller never exited suspension")
        assert recovered is not None
        self.assertGreaterEqual(cast(float, recovered["EI"]), unsuspend_threshold)

    def test_rate_limit(self) -> None:
        out1 = self._step(pnl=0.005)
        out2 = self._step(pnl=0.005, trades=0.0)
        r1 = cast(float, out1["risk_per_trade_factor"])
        r2 = cast(float, out2["risk_per_trade_factor"])
        self.assertLessEqual(abs(r2 - r1), self.params.delta_r_limit + 1e-6)

    def test_frequency_logic(self) -> None:
        o1 = self._step(global_vol=0.3, local_vol=0.2)
        o2 = self._step(global_vol=0.8, local_vol=0.8)
        self.assertNotEqual(cast(int, o1["cooldown_ms"]), cast(int, o2["cooldown_ms"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
