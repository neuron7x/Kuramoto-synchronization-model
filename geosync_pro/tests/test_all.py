# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Test suite for GeoSync Pro."""

from __future__ import annotations

import unittest

from geosync_pro.estimation.belief import VolBelief
from geosync_pro.models.emh import EMHSSM, Params, State
from geosync_pro.policy.mpc import Controller
from geosync_pro.validate.validate import run_validation


class TestInvariants(unittest.TestCase):
    def test_bounds(self) -> None:
        p = Params()
        m = EMHSSM(p, State())
        for _ in range(100):
            obs = dict(dd=1.0, liq=1.0, reg=1.0, vol=1.0, reward=0.0, var_breach=True)
            s = m.step(obs)
            self.assertTrue(0.0 <= s["H"] <= 1.0)
            self.assertTrue(0.0 <= s["M"] <= 1.0)
            self.assertTrue(0.0 <= s["E"] <= 1.0)
            self.assertTrue(0.0 <= s["S"] <= 1.0)

    def test_red_blocks_increase(self) -> None:
        ctrl = Controller()
        state = dict(H=0.5, M=0.2, E=0.1, S=0.1)
        action, _ = ctrl.decide(state, "RED", 1.0)
        self.assertNotEqual(action, "increase_risk")

    def test_validation_metrics(self) -> None:
        _df, metrics = run_validation(steps=50)
        self.assertIn("mean_reward", metrics)
        self.assertIn("tail_ES95", metrics)
        self.assertEqual(metrics["prop_increase_risk_in_RED"], 0.0)

    def test_belief_hook(self) -> None:
        p = Params()
        m = EMHSSM(p, State())
        m.belief = VolBelief()
        out = m.step(dict(dd=0.2, liq=0.3, reg=0.4, vol=0.95, reward=0.0, var_breach=True))
        self.assertTrue(0.0 <= out["S"] <= 1.0)


if __name__ == "__main__":
    unittest.main()
