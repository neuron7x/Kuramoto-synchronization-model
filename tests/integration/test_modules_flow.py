from __future__ import annotations

from datetime import datetime, time, timedelta

import numpy as np

from modules import AdaptiveRiskManager, DynamicPositionSizer, MarketRegimeAnalyzer
from modules.execution_analyzer import ExecutionAnalyzer, ExecutionRecord, ExecutionSide
from modules.order_validator import (
    Order,
    OrderSide,
    OrderType,
    OrderValidator,
    RiskLimits,
    TradingHours,
)
from modules.performance_tracker import PerformanceTracker
from modules.system_health_dashboard import (
    ComponentStatus,
    ComponentType,
    SystemHealthDashboard,
)


def _generate_sample_series(length: int = 180) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=42)
    price_changes = rng.normal(0, 1.5, size=length)
    prices = 100 + np.cumsum(price_changes)
    returns = np.diff(prices) / prices[:-1]
    return prices, returns


def test_modules_flow_integration() -> None:
    prices, returns = _generate_sample_series()
    volatility = float(returns.std(ddof=1))
    last_price = float(prices[-1])

    regime_analyzer = MarketRegimeAnalyzer()
    regime_metrics = regime_analyzer.classify_regime(prices, returns)

    assert regime_metrics is not None
    assert 0.0 <= regime_metrics.regime_confidence <= 1.0
    assert 0.0 <= regime_metrics.volatility
    assert 0.0 <= regime_metrics.hurst_exponent <= 1.0
    assert 0.0 <= regime_metrics.adf_pvalue <= 1.0

    risk_manager = AdaptiveRiskManager(base_capital=1_000_000, risk_tolerance=0.02)
    risk_metrics = risk_manager.calculate_risk_metrics(returns)
    position_limit = risk_manager.update_position_limits("BTC-USD", volatility)
    max_position = risk_manager.calculate_position_size(
        "BTC-USD", price=last_price, volatility=volatility, confidence=0.7
    )

    assert risk_metrics is not None
    assert risk_metrics.var_95 >= 0.0
    assert risk_metrics.var_99 >= 0.0
    assert 0.0 <= risk_metrics.max_drawdown <= 1.0
    assert position_limit.max_position_size > 0
    assert 0.0 < position_limit.max_leverage <= 10.0
    assert 0.0 < position_limit.stop_loss_pct < 1.0
    assert max_position > 0.0

    position_sizer = DynamicPositionSizer(base_capital=1_000_000)
    sizing_result = position_sizer.calculate_adaptive_size(
        symbol="BTC-USD",
        price=last_price,
        volatility=volatility,
        confidence=0.7,
        win_rate=0.55,
        avg_win=0.02,
        avg_loss=0.01,
    )

    assert sizing_result is not None
    assert sizing_result.min_size <= sizing_result.recommended_size <= sizing_result.max_size
    assert 0.0 <= sizing_result.confidence <= 1.0
    assert sizing_result.volatility_adjustment > 0.0

    risk_limits = RiskLimits(
        max_position_size=250_000.0,
        max_order_value=250_000.0,
        max_daily_trades=10,
        max_daily_volume=1_000_000.0,
        max_concentration=0.5,
        min_order_size=1.0,
        max_leverage=5.0,
    )
    trading_hours = TradingHours(
        start=time(0, 0),
        end=time(23, 59),
        trading_days=set(range(7)),
    )
    validator = OrderValidator(
        risk_limits=risk_limits,
        trading_hours=trading_hours,
        portfolio_value=1_000_000.0,
    )

    quantity = float(sizing_result.recommended_size / last_price)
    order = Order(
        order_id="order-001",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=last_price,
    )
    validation_result = validator.validate(order, current_price=last_price)

    assert validation_result is not None
    assert validation_result.is_valid
    assert 0.0 <= validation_result.risk_score <= 1.0
    assert validation_result.order.order_id == "order-001"

    execution_analyzer = ExecutionAnalyzer(slippage_threshold_bps=15.0, latency_threshold_ms=200.0)
    execution = ExecutionRecord(
        execution_id="exec-001",
        order_id=order.order_id,
        symbol=order.symbol,
        side=ExecutionSide.BUY,
        quantity=order.quantity,
        expected_price=order.price or last_price,
        executed_price=last_price * 1.0005,
        order_created_at=datetime.now() - timedelta(milliseconds=120),
        execution_time=datetime.now(),
        fees=1.25,
    )
    execution_analysis = execution_analyzer.record_execution(execution)

    assert execution_analysis is not None
    assert 0.0 <= execution_analysis.quality_score <= 100.0
    assert execution_analysis.slippage.slippage_bps is not None
    assert execution_analysis.latency.total_latency_ms >= 0.0

    performance_tracker = PerformanceTracker(initial_capital=1_000_000.0)
    performance_tracker.update_position(
        symbol="BTC-USD",
        quantity=order.quantity,
        average_price=last_price,
        current_price=last_price,
    )
    performance_tracker.record_trade(
        symbol="BTC-USD",
        side="buy",
        quantity=order.quantity,
        price=last_price,
        pnl=0.0,
    )
    performance_tracker.update_equity()
    performance_tracker.update_position(
        symbol="BTC-USD",
        quantity=order.quantity,
        average_price=last_price,
        current_price=last_price * 1.01,
    )
    performance_tracker.update_equity()
    performance_metrics = performance_tracker.get_metrics()

    assert performance_metrics is not None
    assert performance_metrics.total_return >= -1.0
    assert 0.0 <= performance_metrics.max_drawdown <= 1.0

    dashboard = SystemHealthDashboard(check_interval_seconds=5.0)
    components = [
        ("regime", "Market Regime Analyzer", ComponentType.STRATEGY),
        ("risk", "Adaptive Risk Manager", ComponentType.RISK_MANAGER),
        ("sizer", "Dynamic Position Sizer", ComponentType.STRATEGY),
        ("validator", "Order Validator", ComponentType.EXECUTION),
        ("execution", "Execution Analyzer", ComponentType.EXECUTION),
        ("performance", "Performance Tracker", ComponentType.MONITORING),
        ("health", "System Health Dashboard", ComponentType.MONITORING),
    ]
    for component_id, name, component_type in components:
        assert dashboard.register_component(component_id, name, component_type)
        assert dashboard.update_component_status(
            component_id, ComponentStatus.HEALTHY, message="OK"
        )

    summary = dashboard.get_summary()
    assert summary["total_components"] == len(components)
    assert summary["overall_status"] in {
        ComponentStatus.HEALTHY.value,
        ComponentStatus.DEGRADED.value,
        ComponentStatus.UNHEALTHY.value,
        ComponentStatus.UNKNOWN.value,
    }
