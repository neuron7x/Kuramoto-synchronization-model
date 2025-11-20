"""Unit tests for the Transaction Cost Analyzer."""

from __future__ import annotations

import math

import pytest

from analytics.tca import (
    BenchmarkPriceSample,
    BrokerVenueBreakdown,
    FillDetail,
    LiquiditySample,
    MarketVolumeSample,
    OrderLifecycle,
    PeriodicTCARecord,
    TransactionCostAnalyzer,
)


def _approx(value: float, expected: float, rel: float = 1e-6) -> bool:
    return math.isclose(value, expected, rel_tol=rel, abs_tol=1e-9)


def test_transaction_cost_analyzer_end_to_end() -> None:
    analyzer = TransactionCostAnalyzer(bucket_seconds=60.0)
    fills = [
        FillDetail(
            quantity=50.0,
            price=101.0,
            fees=1.0,
            timestamp=0.0,
            broker="BrokerA",
            venue="X",
        ),
        FillDetail(
            quantity=30.0,
            price=102.0,
            fees=0.6,
            timestamp=60.0,
            broker="BrokerB",
            venue="Y",
        ),
        FillDetail(
            quantity=20.0,
            price=103.0,
            fees=0.4,
            timestamp=120.0,
            broker="BrokerA",
            venue="X",
        ),
    ]
    orders = [
        OrderLifecycle(
            order_id="O1", submitted_ts=0.0, acknowledged_ts=0.2, completed_ts=30.0
        ),
        OrderLifecycle(
            order_id="O2", submitted_ts=40.0, acknowledged_ts=40.5, completed_ts=150.0
        ),
    ]
    market_volumes = [
        MarketVolumeSample(timestamp=0.0, volume=500.0),
        MarketVolumeSample(timestamp=60.0, volume=400.0),
        MarketVolumeSample(timestamp=120.0, volume=300.0),
    ]
    liquidity_samples = [
        LiquiditySample(timestamp=0.0, displayed_volume=200.0, spread_bps=5.0),
        LiquiditySample(timestamp=60.0, displayed_volume=180.0, spread_bps=6.0),
        LiquiditySample(timestamp=120.0, displayed_volume=160.0, spread_bps=5.5),
    ]
    benchmark_prices = [
        BenchmarkPriceSample(timestamp=0.0, price=100.5, vwap_window_volume=500.0),
        BenchmarkPriceSample(timestamp=60.0, price=100.8, vwap_window_volume=400.0),
        BenchmarkPriceSample(timestamp=120.0, price=101.2, vwap_window_volume=300.0),
    ]

    report = analyzer.generate_report(
        side="buy",
        arrival_price=100.0,
        target_quantity=120.0,
        fills=fills,
        orders=orders,
        market_volumes=market_volumes,
        liquidity_samples=liquidity_samples,
        benchmark_prices=benchmark_prices,
    )

    assert _approx(report.executed_quantity, 100.0)

    assert _approx(report.latency.submit_to_ack.mean, 0.35, rel=1e-3)
    assert report.latency.submit_to_ack.count == pytest.approx(2.0)
    assert report.latency.ack_to_fill.max == pytest.approx(109.5)

    assert _approx(report.slippage.implementation_shortfall, 172.0, rel=1e-6)
    assert _approx(report.slippage.per_share_shortfall, 1.72, rel=1e-6)

    assert _approx(report.liquidity.average_displayed_volume, 180.0, rel=1e-6)
    assert report.liquidity.book_pressure > 0.0
    assert _approx(report.liquidity.median_spread_bps, 5.5, rel=1e-6)

    assert _approx(report.benchmarks.trade_vwap, 101.7, rel=1e-6)
    assert _approx(report.benchmarks.market_vwap, 100.775, rel=1e-6)
    assert _approx(report.benchmarks.participation_rate, 100.0 / 1200.0, rel=1e-6)

    assert _approx(report.cost_breakdown.explicit_fees, 2.0, rel=1e-6)
    assert report.cost_breakdown.total_cost > report.cost_breakdown.explicit_fees

    assert any("Broker" in rec for rec in report.recommendations)

    brokers = {
        (
            breakdown.broker,
            breakdown.venue,
        ): breakdown
        for breakdown in report.broker_comparison
    }
    assert len(brokers) == 2
    broker_a = brokers[("BrokerA", "X")]
    assert isinstance(broker_a, BrokerVenueBreakdown)
    assert _approx(broker_a.quantity, 70.0, rel=1e-6)

    assert len(report.periodic) == 3
    assert all(isinstance(record, PeriodicTCARecord) for record in report.periodic)
    first_bucket = report.periodic[0]
    assert _approx(first_bucket.executed_quantity, 50.0, rel=1e-6)


def test_transaction_cost_analyzer_empty_inputs() -> None:
    analyzer = TransactionCostAnalyzer(bucket_seconds=60.0)
    report = analyzer.generate_report(
        side="sell",
        arrival_price=100.0,
        target_quantity=0.0,
        fills=[],
        orders=[],
        market_volumes=[],
        liquidity_samples=[],
        benchmark_prices=[],
    )

    assert report.executed_quantity == pytest.approx(0.0)
    assert report.latency.submit_to_ack.count == pytest.approx(0.0)
    assert report.slippage.implementation_shortfall == pytest.approx(0.0)
    assert report.liquidity.average_displayed_volume == pytest.approx(0.0)
    assert report.benchmarks.trade_vwap == pytest.approx(0.0)
    assert report.cost_breakdown.total_cost == pytest.approx(0.0)
    assert report.recommendations == ()
    assert report.broker_comparison == ()
    assert report.periodic == ()


def test_market_vwap_ignores_zero_volume_benchmarks() -> None:
    benchmarks = [
        BenchmarkPriceSample(timestamp=0.0, price=100.0, vwap_window_volume=0.0),
        BenchmarkPriceSample(timestamp=60.0, price=200.0, vwap_window_volume=100.0),
        BenchmarkPriceSample(timestamp=120.0, price=150.0, vwap_window_volume=None),
    ]

    result = TransactionCostAnalyzer._compute_market_vwap(benchmarks)

    expected = ((200.0 * 100.0) + (150.0 * 1.0)) / (100.0 + 1.0)
    assert _approx(result, expected, rel=1e-9)
