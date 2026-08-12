# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from backtest.strategies.amm_combo import AMMComboStrategy, AMMStrategyConfig


def test_strategy_generates_actions_and_sizes():
    cfg = AMMStrategyConfig()
    strategy = AMMComboStrategy(cfg)
    actions = []
    sizes = []
    for i in range(800):
        x = 0.0004 if i < 600 else (0.03 if i % 2 == 0 else -0.03)
        R = 0.6
        kappa = 0.1
        o = strategy.on_step(x, R, kappa, None)
        actions.append(o["action"])
        sizes.append(abs(o["size"]))  # non-zero sometimes
    assert any(a in ("ENTER_LONG", "ENTER_SHORT") for a in actions)
    assert "EXIT_ALL" in actions
    assert max(sizes) > 0.0
