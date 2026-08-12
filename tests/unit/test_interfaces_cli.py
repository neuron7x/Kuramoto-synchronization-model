# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np

from core.indicators.entropy import delta_entropy, entropy
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci
from core.phase.detector import composite_transition
from interfaces.cli import signal_from_indicators


def _reference_signal(
    prices: np.ndarray, window: int = 32, ricci_delta: float = 0.005
) -> np.ndarray:
    sig = np.zeros(len(prices), dtype=int)
    for t in range(window, len(prices)):
        prefix = prices[: t + 1]
        phases = compute_phase(prefix)
        synchrony = kuramoto_order(phases[-window:])
        entropy_value = entropy(prefix[-window:])
        delta_value = delta_entropy(prefix, window=window)
        graph = build_price_graph(prefix[-window:], delta=ricci_delta)
        curvature = mean_ricci(graph)
        composite = composite_transition(synchrony, delta_value, curvature, entropy_value)
        if composite > 0.15 and delta_value < 0 and curvature < 0:
            sig[t] = 1
        elif composite < -0.15 and delta_value > 0:
            sig[t] = -1
        else:
            sig[t] = sig[t - 1]
    return sig


def test_signal_from_indicators_matches_reference() -> None:
    prices = np.linspace(100.0, 110.0, num=128)
    reference = _reference_signal(prices)

    threaded = signal_from_indicators(prices, window=32, max_workers=3)
    sequential = signal_from_indicators(prices, window=32, max_workers=0)

    assert np.array_equal(threaded, reference)
    assert np.array_equal(sequential, reference)


def test_signal_from_indicators_accepts_custom_ricci_delta() -> None:
    prices = np.linspace(100.0, 102.0, num=96)
    reference = _reference_signal(prices, window=24, ricci_delta=0.01)

    result = signal_from_indicators(prices, window=24, max_workers=2, ricci_delta=0.01)
    assert np.array_equal(result, reference)
