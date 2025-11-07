"""End-to-end smoke and property checks for the neural controller."""

from __future__ import annotations

import unittest

import numpy as np

from tradepulse.neural_controller.core.emh_engine import EMHSSM, Params, State
from tradepulse.neural_controller.estimation.ekf import EKFConfig, EMHEKF
from tradepulse.neural_controller.policy.controller import BasalGangliaController, PolicyConfig
from tradepulse.neural_controller.risk.cvar_gate import CVARGate
from tradepulse.neural_controller.integration.bridge import NeuralMarketController, NeuralTACLBridge
from tradepulse.neural_controller.validate.simulate import toy_stream


class DummyTACL:
    def optimize(self, allocs, temperature, generations=10):
        return {"allocs": dict(allocs), "optimized": True, "temperature": float(temperature)}


class DummyKuramoto:
    def get_order_parameter(self) -> float:
        return 0.25


class NeuralControllerTestCase(unittest.TestCase):
    def test_emh_bounds(self) -> None:
        model = EMHSSM(Params(), State())
        for _ in range(200):
            out = model.step(dict(dd=1, liq=1, reg=1, vol=1, reward=0.0, var_breach=True))
            self.assertTrue(0.0 <= out["H"] <= 1.0)
            self.assertTrue(0.0 <= out["M"] <= 1.0)
            self.assertTrue(0.0 <= out["E"] <= 1.0)
            self.assertTrue(0.0 <= out["S"] <= 1.0)

    def test_ekf_updates_without_drift(self) -> None:
        ekf = EMHEKF(Params(), EKFConfig())
        before = ekf.x.copy()
        est = ekf.step(dict(dd=0.2, liq=0.3, reg=0.4, vol=0.5, reward=0.0))
        self.assertEqual(set(est.keys()), {"H", "M", "E", "S"})
        self.assertTrue(np.all(ekf.x >= 0.0))
        self.assertTrue(np.all(ekf.x <= 1.0))
        self.assertFalse(np.allclose(before, ekf.x))

    def test_go_no_go_invariants(self) -> None:
        ctrl = BasalGangliaController(PolicyConfig(temp=1.0, tau_E_amber=0.3))
        action, _ = ctrl.decide({"H": 0.5, "M": 0.2, "E": 0.1, "S": 0.1}, "RED", 0.1)
        self.assertNotEqual(action, "increase_risk")
        action, probs = ctrl.decide({"H": 0.5, "M": 0.8, "E": 0.1, "S": 0.1}, "AMBER", -0.1)
        self.assertNotEqual(action, "increase_risk")
        self.assertEqual(probs["action_probs"]["increase_risk"], 0.0)

    def test_cvar_gate_scaling(self) -> None:
        gate = CVARGate(0.95, 0.03, 50)
        scales = [gate.update(float(np.random.normal(0, 0.01))) for _ in range(60)]
        self.assertTrue(all(0.0 <= s <= 1.0 for s in scales))

    def test_neural_bridge_flow(self) -> None:
        neural = NeuralMarketController.from_yaml("tradepulse/neural_controller/config/neural_params.yaml")
        bridge = NeuralTACLBridge(neural, DummyTACL(), DummyKuramoto(), sync_threshold=0.3)
        obs = dict(dd=0.2, liq=0.3, reg=0.4, vol=0.6, reward=0.01, var_breach=False, m_proxy=0.6)
        out = bridge.step(obs)
        self.assertIn(out["mode"], {"GREEN", "AMBER", "RED"})
        if out["mode"] == "RED":
            self.assertNotEqual(out["action"], "increase_risk")
        self.assertLessEqual(out["alloc_scale"], 1.0)
        self.assertGreater(out["temperature"], 0.0)

    def test_toy_stream_invariant(self) -> None:
        neural = NeuralMarketController.from_yaml("tradepulse/neural_controller/config/neural_params.yaml")
        bridge = NeuralTACLBridge(neural, DummyTACL(), DummyKuramoto(), sync_threshold=0.3)
        for obs in toy_stream(steps=16):
            obs["m_proxy"] = 0.5
            decision = bridge.step(obs)
            for key in ("H", "M", "E", "S"):
                self.assertTrue(0.0 <= decision[key] <= 1.0)
            if decision["mode"] == "RED":
                self.assertNotEqual(decision["action"], "increase_risk")


if __name__ == "__main__":
    unittest.main()
