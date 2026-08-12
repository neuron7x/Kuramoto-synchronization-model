# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import walk_forward
from core.agent.strategy import PiAgent, Strategy
from core.indicators.entropy import delta_entropy, entropy
from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci
from core.phase.detector import composite_transition, phase_flags


def test_csv_to_backtest_pipeline(price_dataframe: pd.DataFrame) -> None:
    prices = price_dataframe["price"].to_numpy()
    phase = compute_phase(prices - prices.mean())
    R = kuramoto_order(phase)
    H = entropy(prices, bins=10)
    dH = delta_entropy(prices, window=10)
    hurst = hurst_exponent(prices)
    graph = build_price_graph(prices, delta=0.01)
    kappa_mean = mean_ricci(graph)

    state = {
        "R": R,
        "delta_H": dH,
        "kappa_mean": kappa_mean,
        "H": H,
        "phase_reversal": hurst < 0.4,
    }

    agent = PiAgent(strategy=Strategy(name="trend", params={"threshold": 0.5}))
    action = agent.evaluate_and_adapt(state)
    assert action in {"enter", "hold", "exit"}

    def signal_fn(_prices: np.ndarray) -> np.ndarray:
        signal = np.zeros_like(_prices)
        signal[1:] = 1
        return signal

    result = walk_forward(prices, signal_fn, fee=0.0005)
    expected_pnl = float(prices[-1] - prices[0] - 0.0005)
    assert result.pnl == pytest.approx(expected_pnl, rel=1e-9)
    assert result.trades == 1
    assert result.max_dd <= 0

    flag = phase_flags(R=R, dH=dH, kappa_mean=kappa_mean, H=H)
    score = composite_transition(R, dH, kappa_mean, H)
    assert flag in {"proto", "precognitive", "emergent", "post-emergent", "neutral"}
    assert -1.0 <= score <= 1.0
