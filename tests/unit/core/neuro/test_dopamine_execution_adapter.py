# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for DopamineExecutionAdapter — RPE from execution outcomes.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import math

import pytest

from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.signal_bus import NeuroSignalBus


@pytest.fixture
def bus() -> NeuroSignalBus:
    return NeuroSignalBus()


@pytest.fixture
def adapter(bus: NeuroSignalBus) -> DopamineExecutionAdapter:
    return DopamineExecutionAdapter(bus)


# ── RPE computation ──────────────────────────────────────────────────


@pytest.mark.L3
class TestComputeRPE:
    """Schultz 1997 TD error: RPE = tanh(realized - predicted - slippage)."""

    def test_positive_pnl_positive_rpe(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=100.0, predicted_return=50.0)
        assert rpe > 0, "Better-than-expected → positive RPE"

    def test_negative_pnl_negative_rpe(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=-100.0, predicted_return=50.0)
        assert rpe < 0, "Worse-than-expected → negative RPE"

    def test_zero_pnl_matches_prediction(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=0.0, predicted_return=0.0)
        assert rpe == pytest.approx(0.0, abs=1e-9), "No surprise → zero RPE"

    def test_exact_match_zero_rpe(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=42.0, predicted_return=42.0)
        assert rpe == pytest.approx(0.0, abs=1e-9)


@pytest.mark.L3
class TestTanhNormalisation:
    """RPE must be bounded in [-1, 1] via tanh."""

    def test_large_positive_clamped(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=1e6, predicted_return=0.0)
        assert -1.0 <= rpe <= 1.0

    def test_large_negative_clamped(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=-1e6, predicted_return=0.0)
        assert -1.0 <= rpe <= 1.0

    def test_output_is_tanh(self, adapter: DopamineExecutionAdapter) -> None:
        rpe = adapter.compute_rpe(realized_pnl=1.0, predicted_return=0.0)
        assert rpe == pytest.approx(math.tanh(1.0), abs=1e-9)


@pytest.mark.L3
class TestSlippagePenalty:
    """Slippage reduces RPE (execution cost)."""

    def test_slippage_reduces_rpe(self, adapter: DopamineExecutionAdapter) -> None:
        rpe_no_slip = adapter.compute_rpe(realized_pnl=10.0, predicted_return=5.0)
        rpe_with_slip = adapter.compute_rpe(realized_pnl=10.0, predicted_return=5.0, slippage=2.0)
        assert rpe_with_slip < rpe_no_slip

    def test_negative_slippage_treated_as_abs(self, adapter: DopamineExecutionAdapter) -> None:
        rpe_pos = adapter.compute_rpe(realized_pnl=10.0, predicted_return=5.0, slippage=1.0)
        rpe_neg = adapter.compute_rpe(realized_pnl=10.0, predicted_return=5.0, slippage=-1.0)
        assert rpe_pos == pytest.approx(rpe_neg, abs=1e-9)


@pytest.mark.L3
class TestUpdateFromTrade:
    """update_from_trade extracts fields and publishes to bus."""

    def test_publishes_dopamine_to_bus(self, bus: NeuroSignalBus) -> None:
        adapter = DopamineExecutionAdapter(bus)
        trade = {"pnl": 5.0, "predicted_return": 2.0, "slippage": 0.0}
        rpe = adapter.update_from_trade(trade)

        # Bus should now hold the published RPE
        snapshot = bus.snapshot()
        assert snapshot.dopamine_rpe == pytest.approx(rpe, abs=1e-6)
        assert rpe > 0

    def test_defaults_for_missing_keys(self, bus: NeuroSignalBus) -> None:
        adapter = DopamineExecutionAdapter(bus)
        rpe = adapter.update_from_trade({"pnl": 0.0})
        assert rpe == pytest.approx(0.0, abs=1e-9)

    def test_negative_trade_publishes_negative_rpe(self, bus: NeuroSignalBus) -> None:
        adapter = DopamineExecutionAdapter(bus)
        rpe = adapter.update_from_trade({"pnl": -10.0, "predicted_return": 5.0})
        assert rpe < 0
        assert bus.snapshot().dopamine_rpe < 0


@pytest.mark.L3
class TestSharpeDelta:
    """Rolling Sharpe change as secondary reward signal."""

    def test_insufficient_data_returns_zero(self) -> None:
        assert DopamineExecutionAdapter.compute_sharpe_delta([0.01] * 10, window=20) == 0.0

    def test_improving_returns_positive_delta(self) -> None:
        # First 20 returns flat near zero, next 20 strongly positive
        returns = [0.001] * 20 + [0.05] * 20
        delta = DopamineExecutionAdapter.compute_sharpe_delta(returns, window=20)
        assert delta > 0

    def test_deteriorating_returns_negative_delta(self) -> None:
        returns = [0.05] * 20 + [0.001] * 20
        delta = DopamineExecutionAdapter.compute_sharpe_delta(returns, window=20)
        assert delta < 0
