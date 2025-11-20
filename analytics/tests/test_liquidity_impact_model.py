from __future__ import annotations

import math

import pytest

from analytics.liquidity_impact import (
    ExecutionParameters,
    LiquidityImpactConfig,
    LiquidityImpactModel,
    LiquiditySnapshot,
    OrderBookLevel,
)


def build_snapshot(mid: float = 100.0) -> LiquiditySnapshot:
    return LiquiditySnapshot(
        mid_price=mid,
        bid_levels=(
            OrderBookLevel(price=mid - 0.1, quantity=5.0),
            OrderBookLevel(price=mid - 0.2, quantity=5.0),
        ),
        ask_levels=(
            OrderBookLevel(price=mid + 0.1, quantity=5.0),
            OrderBookLevel(price=mid + 0.2, quantity=5.0),
        ),
    )


def test_forecast_computes_slippage_and_cost() -> None:
    snapshot = build_snapshot()
    model = LiquidityImpactModel()

    forecast = model.forecast(
        side="buy",
        quantity=4.0,
        participation_rate=0.1,
        snapshot=snapshot,
        volatility=0.0,
    )

    assert forecast.base_market_impact == pytest.approx(0.1)
    assert forecast.expected_slippage > forecast.base_market_impact
    assert forecast.expected_cost == pytest.approx(forecast.expected_slippage * 4.0)
    assert forecast.expected_slippage_bps == pytest.approx(
        forecast.expected_slippage / 100.0 * 1e4
    )


def test_shortfall_penalty_and_liquidity_score() -> None:
    snapshot = build_snapshot()
    model = LiquidityImpactModel()

    forecast = model.forecast(
        side="buy",
        quantity=15.0,  # exceeds displayed depth (10)
        participation_rate=0.2,
        snapshot=snapshot,
        volatility=0.0,
    )

    assert forecast.shortfall_ratio == pytest.approx(5.0 / 15.0)
    assert forecast.liquidity_score == pytest.approx(10.0 / 15.0)
    assert forecast.expected_slippage > 0.0


def test_efficiency_metrics_include_shortfall() -> None:
    snapshot = build_snapshot()
    model = LiquidityImpactModel()
    forecast = model.forecast(
        side="sell",
        quantity=3.0,
        participation_rate=0.15,
        snapshot=snapshot,
        volatility=0.0,
    )

    metrics = model.efficiency_metrics(forecast, benchmark_price=99.8)

    assert metrics["expected_slippage_bps"] == pytest.approx(
        forecast.expected_slippage_bps
    )
    assert "expected_implementation_shortfall" in metrics
    assert metrics["expected_implementation_shortfall_bps"] == pytest.approx(
        metrics["expected_implementation_shortfall"] / 99.8 * 1e4
    )


def test_adjust_execution_reacts_to_high_slippage() -> None:
    snapshot = build_snapshot()
    model = LiquidityImpactModel()
    forecast = model.forecast(
        side="buy",
        quantity=6.0,
        participation_rate=0.25,
        snapshot=snapshot,
        volatility=0.0,
    )

    current = ExecutionParameters(
        participation_rate=0.2, slice_volume=2.0, limit_offset_bps=3.0
    )
    adjusted = model.adjust_execution_params(forecast, current)

    assert adjusted.participation_rate < current.participation_rate
    assert adjusted.slice_volume < current.slice_volume
    assert adjusted.limit_offset_bps > current.limit_offset_bps


def test_adjust_execution_reacts_to_low_slippage() -> None:
    snapshot = LiquiditySnapshot(
        mid_price=100.0,
        bid_levels=(OrderBookLevel(price=99.99, quantity=60.0),),
        ask_levels=(OrderBookLevel(price=100.01, quantity=60.0),),
    )
    config = LiquidityImpactConfig(impact_sensitivity=0.003, volatility_sensitivity=0.0)
    model = LiquidityImpactModel(config)

    forecast = model.forecast(
        side="buy",
        quantity=1.0,
        participation_rate=0.01,
        snapshot=snapshot,
        volatility=0.0,
    )

    current = ExecutionParameters(
        participation_rate=0.05, slice_volume=1.0, limit_offset_bps=3.0
    )
    adjusted = model.adjust_execution_params(forecast, current)

    assert adjusted.participation_rate > current.participation_rate
    assert adjusted.slice_volume > current.slice_volume
    assert adjusted.limit_offset_bps < current.limit_offset_bps


def test_batch_forecast_returns_forecasts() -> None:
    snapshot = build_snapshot()
    model = LiquidityImpactModel()
    quantities = [2.0, 4.0, 6.0]

    forecasts = model.batch_forecast(
        side="sell",
        quantities=quantities,
        participation_rate=0.2,
        snapshot=snapshot,
        volatility=0.0,
    )

    assert [f.quantity for f in forecasts] == quantities
    assert all(math.isfinite(f.expected_slippage) for f in forecasts)
