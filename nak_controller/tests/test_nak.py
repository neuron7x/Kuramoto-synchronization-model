import unittest
from typing import Dict, cast

from nak_controller.integration.hook import NaKHook

CONFIG_PATH = "nak_controller/conf/nak.yaml"


class TestNaKController(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = NaKHook(CONFIG_PATH)

    def _step(
        self,
        *,
        gv: float = 0.3,
        pd: float = 0.1,
        pnl: float = 0.001,
        trades: float = 0.6,
        lvol: float = 0.3,
    ) -> Dict[str, object]:
        local = {
            "trades": trades,
            "pnl": pnl,
            "pnl_scale": 0.01,
            "local_vol": lvol,
            "local_dd": pd,
            "tech_errors": 0.0,
            "latency": 0.3,
            "slippage": 0.0005,
            "glial_support": 0.0,
        }
        global_obs = {
            "global_vol": gv,
            "portfolio_dd": pd,
            "exposure": 1.0,
            "unexpected_reward": 0.0,
        }
        return self.hook.compute_limits(
            "s1",
            local,
            global_obs,
            0.002,
            1.0,
            2000,
        )

    def test_bounds_and_invariants(self) -> None:
        out = self._step()
        self.assertTrue(0.0 <= cast(float, out["EI"]) <= 1.0)
        self.assertTrue(0.2 <= cast(float, out["risk_per_trade_factor"]) <= 1.8)
        self.assertAlmostEqual(
            cast(float, out["max_position_factor"]),
            cast(float, out["risk_per_trade_factor"]),
        )
        self.assertGreaterEqual(cast(int, out["cooldown_ms"]), 1)

    def test_modes_and_hysteresis(self) -> None:
        out_red = self._step(gv=0.95, pd=0.75, pnl=-0.002, trades=0.9, lvol=0.95)
        self.assertTrue(
            bool(out_red["is_suspended"]) or cast(str, out_red["mode"]) == "RED"
        )
        out_rec = None
        for _ in range(6):
            out_rec = self._step(gv=0.2, pd=0.02, pnl=0.003, trades=0.2, lvol=0.1)
        assert out_rec is not None
        self.assertGreaterEqual(cast(float, out_rec["EI"]), 0.15)

    def test_rate_limit(self) -> None:
        out1 = self._step(pnl=0.005)
        out2 = self._step(pnl=0.005, trades=0.0)
        self.assertLessEqual(
            abs(
                cast(float, out2["risk_per_trade_factor"])
                - cast(float, out1["risk_per_trade_factor"])
            ),
            0.20 + 1e-6,
        )

    def test_frequency_logic(self) -> None:
        o1 = self._step(gv=0.3, lvol=0.2)
        o2 = self._step(gv=0.8, lvol=0.8)
        self.assertNotEqual(o1["cooldown_ms"], o2["cooldown_ms"])

    def test_red_mode_forces_suspension(self) -> None:
        out = self._step(gv=1.0, pd=0.8, pnl=-0.01, trades=1.0, lvol=1.0)
        self.assertEqual(out["mode"], "RED")
        self.assertTrue(out["is_suspended"])
        self.assertAlmostEqual(cast(float, out["risk_per_trade_factor"]), 0.2, places=6)


if __name__ == "__main__":
    unittest.main()
