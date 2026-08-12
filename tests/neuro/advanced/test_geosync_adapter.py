# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the GeoSync neuro adapter."""

from __future__ import annotations

import numpy as np
import pytest

from core.neuro.adapters.geosync_adapter import GeoSyncNeuroAdapter, MarketPulse


@pytest.mark.asyncio
async def test_adapter_combines_amm_and_neuro() -> None:
    adapter = GeoSyncNeuroAdapter()
    rng = np.random.default_rng(1)
    prices = np.cumsum(rng.normal(0.0, 0.3, size=64)) + 25

    pulse = MarketPulse(signal=0.01, synchrony=0.6, curvature=0.05, entropy=0.02)
    market_data = {"series": {"ETH": prices.tolist()}}
    portfolio_state = {"strategies": ["fractal_momentum"]}

    response = await adapter.process_market_update(pulse, market_data, portfolio_state)
    assert "amm" in response
    assert "neuro" in response
    assert response["neuro"]["modulated_candidates"], "Candidates should not be empty"
