# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import math

import pytest

from analytics.execution_quality import (
    CancelReplaceSample,
    FillSample,
    cancel_replace_latency,
    fill_rate,
    implementation_shortfall,
    vwap,
    vwap_slippage,
)


def test_vwap_and_slippage_buy():
    fills = [
        FillSample(quantity=1.0, price=101.0),
        FillSample(quantity=2.0, price=99.5),
    ]
    assert math.isclose(vwap(fills), (1.0 * 101.0 + 2.0 * 99.5) / 3.0)
    slippage = vwap_slippage("buy", benchmark_price=100.0, fills=fills)
    assert slippage == pytest.approx(vwap(fills) - 100.0)


def test_vwap_slippage_sell_direction():
    fills = [FillSample(quantity=1.0, price=100.5)]
    slippage = vwap_slippage("sell", benchmark_price=101.0, fills=fills)
    assert slippage == pytest.approx(101.0 - 100.5)


def test_implementation_shortfall_buy():
    fills = [FillSample(quantity=1.5, price=101.0, fees=0.2)]
    shortfall = implementation_shortfall("buy", 100.0, fills)
    expected = (1.0 * (101.0 - 100.0) * 1.5) + 0.2
    assert shortfall == pytest.approx(expected)


def test_implementation_shortfall_sell():
    fills = [FillSample(quantity=2.0, price=99.0, fees=0.1)]
    shortfall = implementation_shortfall("sell", 100.0, fills)
    expected = (100.0 - 99.0) * 2.0 + 0.1
    assert shortfall == pytest.approx(expected)


def test_fill_rate_bounds():
    fills = [
        FillSample(quantity=0.6, price=100.0),
        FillSample(quantity=0.4, price=100.0),
    ]
    assert fill_rate(1.0, fills) == pytest.approx(1.0)
    assert fill_rate(2.0, fills) == pytest.approx(0.5)
    assert fill_rate(0.0, fills) == 0.0


def test_cancel_replace_latency_stats():
    samples = [
        CancelReplaceSample(cancel_ts=0.0, replace_ts=0.25),
        {"cancel_ts": 0.5, "replace_ts": 1.1},
        {"cancel": 2.0, "replace": 2.7},
    ]
    stats = cancel_replace_latency(samples)
    assert stats["count"] == pytest.approx(3.0)
    assert stats["max"] == pytest.approx(0.7)
    assert stats["p50"] == pytest.approx(0.6, abs=1e-9)
    assert stats["p95"] == pytest.approx(0.69, abs=1e-9)
    assert stats["mean"] == pytest.approx((0.25 + 0.6 + 0.7) / 3.0)
