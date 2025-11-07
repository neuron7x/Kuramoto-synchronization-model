from __future__ import annotations

import unittest

from nak_controller.integration.hook import NaKHook
from nak_controller.runtime.controller import ControllerOutput

CFG = "nak_controller/conf/nak.yaml"


class TestNaK(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = NaKHook(CFG)

    def _step(
        self,
        gv: float = 0.3,
        pd: float = 0.1,
        pnl: float = 0.001,
        trades: float = 0.6,
        lvol: float = 0.3,
    ) -> ControllerOutput:
        local = dict(
            trades=trades,
            pnl=pnl,
            pnl_scale=0.01,
            local_vol=lvol,
            local_dd=pd,
            tech_errors=0.0,
            latency=0.3,
            slippage=0.0005,
            glial_support=0.0,
        )
        global_obs = dict(global_vol=gv, portfolio_dd=pd, exposure=1.0, unexpected_reward=0.0)
        out = self.hook.compute_limits("s1", local, global_obs, 0.002, 1.0, 2000)
        return out

    def test_bounds(self) -> None:
        out = self._step()
        self.assertTrue(0.0 <= out["EI"] <= 1.0)
        self.assertTrue(0.2 <= out["risk_per_trade_factor"] <= 1.8)
        self.assertTrue(out["cooldown_ms"] >= 1)

    def test_modes_and_hysteresis(self) -> None:
        # RED should suspend or zero risk
        out_red = self._step(gv=0.95, pd=0.75, pnl=-0.002, trades=0.9, lvol=0.95)
        mode = out_red["mode"]
        self.assertTrue(
            out_red["is_suspended"] or (isinstance(mode, str) and mode == "RED")
        )
        # after recovery, require hysteresis to unsuspend
        # simulate multiple steps to increase EI
        for _ in range(5):
            out_rec = self._step(gv=0.2, pd=0.05, pnl=0.003, trades=0.3, lvol=0.1)
        # cannot assert exact, but EI should move upward
        self.assertGreaterEqual(out_rec["EI"], 0.15)

    def test_rate_limit(self) -> None:
        out1 = self._step(pnl=0.005)
        out2 = self._step(pnl=0.005, trades=0.0)
        # risk cannot jump by more than delta per step
        self.assertLessEqual(
            abs(out2["risk_per_trade_factor"] - out1["risk_per_trade_factor"]),
            0.20 + 1e-6,
        )

    def test_frequency_logic(self) -> None:
        o1 = self._step(gv=0.3, lvol=0.2)
        o2 = self._step(gv=0.8, lvol=0.8)
        self.assertNotEqual(o1["cooldown_ms"], o2["cooldown_ms"])


if __name__ == "__main__":
    unittest.main()
