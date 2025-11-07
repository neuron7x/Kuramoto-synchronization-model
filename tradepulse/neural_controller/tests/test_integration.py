
from __future__ import annotations

import sys
import types
from pathlib import Path

if 'tradepulse' not in sys.modules:
    pkg = types.ModuleType('tradepulse')
    pkg.__path__ = [str(Path(__file__).resolve().parents[2])]
    sys.modules['tradepulse'] = pkg

import unittest

import numpy as np

from ..core.emh_model import EMHSSM
from ..core.params import EKFConfig, HomeoConfig, Params, PolicyConfig, RiskConfig
from ..core.state import EMHState
from ..estimation.belief import VolBelief
from ..estimation.ekf import EMHEKF
from ..integration.bridge import KuramotoSync, NeuralMarketController, NeuralTACLBridge, TACLSystem
from ..policy.controller import BasalGangliaController
from ..risk.cvar import CVARGate, es_alpha
from ..validate.simulate import toy_stream


class DummyTACL(TACLSystem):
    def optimize(self, allocs, temperature, generations=10):
        return {"allocs": dict(allocs), "optimized": True}


class DummyKuramoto(KuramotoSync):
    def get_order_parameter(self) -> float:
        return 0.25


class TestNeuralController(unittest.TestCase):
    def test_state_bounds(self) -> None:
        m = EMHSSM(Params(), EMHState())
        for _ in range(200):
            out = m.step(dict(dd=1, liq=1, reg=1, vol=1, reward=0.0, var_breach=True))
            self.assertTrue(0.0 <= out["H"] <= 1.0)
            self.assertTrue(0.0 <= out["M"] <= 1.0)
            self.assertTrue(0.0 <= out["E"] <= 1.0)
            self.assertTrue(0.0 <= out["S"] <= 1.0)

    def test_ekf_bounds(self) -> None:
        ekf = EMHEKF(Params(), EKFConfig())
        est = ekf.step(dict(dd=0.2, liq=0.3, reg=0.4, reward=0.0))
        self.assertEqual(set(est.keys()), {"H", "M", "E", "S"})
        self.assertTrue(np.all(ekf.st.x >= 0) and np.all(ekf.st.x <= 1))

    def test_vol_belief(self) -> None:
        belief = VolBelief()
        hi = belief.step(0.9)
        lo = belief.step(0.1)
        self.assertNotEqual(hi, lo)

    def test_go_no_go(self) -> None:
        ctrl = BasalGangliaController(temp=1.0, tau_E_amber=0.3)
        action, _ = ctrl.decide({"H": 0.5, "M": 0.2, "E": 0.1, "S": 0.1}, "RED", 0.1)
        self.assertNotEqual(action, "increase_risk")
        action, _ = ctrl.decide({"H": 0.5, "M": 0.8, "E": 0.1, "S": 0.1}, "AMBER", -0.1)
        self.assertNotEqual(action, "increase_risk")

    def test_cvar_scale_bounds(self) -> None:
        gate = CVARGate(alpha=0.95, limit=0.03, lookback=50)
        for _ in range(60):
            scale = gate.update(float(np.random.normal(0, 0.01)))
            self.assertTrue(0.0 <= scale <= 1.0)

    def test_bridge_flow(self) -> None:
        nm = NeuralMarketController(Params(), EKFConfig(), PolicyConfig(), RiskConfig(), HomeoConfig())
        bridge = NeuralTACLBridge(nm, DummyTACL(), DummyKuramoto(), sync_threshold=0.3)
        obs = dict(dd=0.2, liq=0.3, reg=0.4, vol=0.6, reward=0.01, var_breach=False, m_proxy=0.6)
        out = bridge.step(obs)
        self.assertIn("action", out)
        self.assertIn("allocs", out)
        self.assertTrue(out["desync_throttle_applied"])
        self.assertGreaterEqual(out["temperature"], 0.3)

    def test_toy_stream(self) -> None:
        samples = list(toy_stream(steps=10))
        self.assertEqual(len(samples), 10)
        self.assertTrue(all(0.0 <= x["dd"] <= 1.0 for x in samples))

    def test_es_alpha(self) -> None:
        returns = np.array([-0.05, -0.03, 0.01, 0.02])
        es = es_alpha(returns, 0.95)
        self.assertGreaterEqual(es, 0.0)


if __name__ == "__main__":
    unittest.main()
