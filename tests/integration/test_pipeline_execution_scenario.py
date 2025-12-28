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
from modules.system_health_dashboard import (
    ComponentStatus,
    ComponentType,
    HealthCheck,
    SystemHealthDashboard,
    SystemMetrics,
)


def _generate_market_series(length: int = 160) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=7)
    price_changes = rng.normal(0, 1.2, size=length)
    prices = 100 + np.cumsum(price_changes)
    returns = np.diff(prices) / prices[:-1]
    return prices, returns


def _run_integrated_pipeline() -> dict[str, object]:
    prices, returns = _generate_market_series()
    last_price = float(prices[-1])

    regime_analyzer = MarketRegimeAnalyzer()
    regime_metrics = regime_analyzer.classify_regime(prices, returns)

    risk_manager = AdaptiveRiskManager(base_capital=1_000_000, risk_tolerance=0.02)
    risk_metrics = risk_manager.calculate_risk_metrics(returns)
    volatility = max(float(regime_metrics.volatility), float(risk_metrics.volatility))
    position_limit = risk_manager.update_position_limits("BTC-USD", volatility)
    risk_position_size = risk_manager.calculate_position_size(
        "BTC-USD",
        price=last_price,
        volatility=volatility,
        confidence=regime_metrics.regime_confidence,
    )

    position_sizer = DynamicPositionSizer(base_capital=1_000_000)
    sizing_result = position_sizer.calculate_adaptive_size(
        symbol="BTC-USD",
        price=last_price,
        volatility=volatility,
        confidence=regime_metrics.regime_confidence,
        win_rate=0.56,
        avg_win=0.02,
        avg_loss=0.01,
    )
    recommended_notional = min(sizing_result.recommended_size, risk_position_size)

    risk_limits = RiskLimits(
        max_position_size=position_limit.max_position_size,
        max_order_value=position_limit.max_position_size * 1.1,
        max_daily_trades=10,
        max_daily_volume=1_000_000.0,
        max_concentration=0.5,
        min_order_size=1.0,
        max_leverage=position_limit.max_leverage,
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

    quantity = float(recommended_notional / last_price)
    order = Order(
        order_id="order-integrated-001",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=last_price,
    )
    validation_result = validator.validate(order, current_price=last_price)

    execution_analyzer = ExecutionAnalyzer(
        slippage_threshold_bps=15.0,
        latency_threshold_ms=200.0,
    )
    execution = ExecutionRecord(
        execution_id="exec-integrated-001",
        order_id=order.order_id,
        symbol=order.symbol,
        side=ExecutionSide.BUY,
        quantity=order.quantity,
        expected_price=order.price or last_price,
        executed_price=last_price * 1.0002,
        order_created_at=datetime.now() - timedelta(milliseconds=50),
        execution_time=datetime.now(),
        fees=1.5,
    )
    execution_analysis = execution_analyzer.record_execution(execution)

    return {
        "regime_metrics": regime_metrics,
        "risk_metrics": risk_metrics,
        "position_limit": position_limit,
        "risk_position_size": risk_position_size,
        "sizing_result": sizing_result,
        "order": order,
        "validation_result": validation_result,
        "execution": execution,
        "execution_analysis": execution_analysis,
        "volatility": volatility,
        "last_price": last_price,
    }


def test_integrated_pipeline_scenario() -> None:
    outputs = _run_integrated_pipeline()

    regime_metrics = outputs["regime_metrics"]
    risk_metrics = outputs["risk_metrics"]
    position_limit = outputs["position_limit"]
    risk_position_size = outputs["risk_position_size"]
    sizing_result = outputs["sizing_result"]
    validation_result = outputs["validation_result"]
    execution_analysis = outputs["execution_analysis"]

    assert 0.0 <= regime_metrics.regime_confidence <= 1.0
    assert 0.0 <= regime_metrics.volatility
    assert 0.0 <= regime_metrics.hurst_exponent <= 1.0
    assert 0.0 <= regime_metrics.adf_pvalue <= 1.0

    assert risk_metrics is not None
    assert risk_metrics.var_95 >= 0.0
    assert risk_metrics.var_99 >= 0.0
    assert 0.0 <= risk_metrics.max_drawdown <= 1.0
    assert position_limit.max_position_size > 0
    assert 0.0 < position_limit.max_leverage <= 10.0
    assert 0.0 < position_limit.stop_loss_pct < 1.0
    assert risk_position_size > 0.0

    assert sizing_result is not None
    assert sizing_result.min_size <= sizing_result.recommended_size <= sizing_result.max_size
    assert 0.0 <= sizing_result.confidence <= 1.0
    assert sizing_result.volatility_adjustment > 0.0

    assert validation_result is not None
    assert validation_result.is_valid
    assert 0.0 <= validation_result.risk_score <= 1.0
    assert validation_result.order.order_id == "order-integrated-001"

    assert execution_analysis is not None
    assert 0.0 <= execution_analysis.quality_score <= 100.0
    assert execution_analysis.slippage.slippage_bps is not None
    assert execution_analysis.latency.total_latency_ms >= 0.0


def test_system_health_dashboard_smoke() -> None:
    outputs = _run_integrated_pipeline()

    regime_metrics = outputs["regime_metrics"]
    risk_metrics = outputs["risk_metrics"]
    sizing_result = outputs["sizing_result"]
    validation_result = outputs["validation_result"]
    execution_analysis = outputs["execution_analysis"]

    dashboard = SystemHealthDashboard(check_interval_seconds=1.0)

    def regime_check() -> HealthCheck:
        status = (
            ComponentStatus.HEALTHY
            if 0.0 <= regime_metrics.regime_confidence <= 1.0
            else ComponentStatus.UNHEALTHY
        )
        return HealthCheck(
            check_name="regime_confidence",
            status=status,
            message=f"Confidence={regime_metrics.regime_confidence:.2f}",
        )

    def risk_check() -> HealthCheck:
        status = (
            ComponentStatus.HEALTHY
            if risk_metrics.var_95 >= 0.0 and risk_metrics.volatility >= 0.0
            else ComponentStatus.DEGRADED
        )
        return HealthCheck(
            check_name="risk_metrics",
            status=status,
            message=f"VaR95={risk_metrics.var_95:.4f}",
        )

    def sizing_check() -> HealthCheck:
        status = (
            ComponentStatus.HEALTHY
            if sizing_result.recommended_size > 0
            else ComponentStatus.DEGRADED
        )
        return HealthCheck(
            check_name="position_sizing",
            status=status,
            message=f"Size={sizing_result.recommended_size:.2f}",
        )

    def validation_check() -> HealthCheck:
        status = (
            ComponentStatus.HEALTHY
            if validation_result.is_valid
            else ComponentStatus.UNHEALTHY
        )
        return HealthCheck(
            check_name="order_validation",
            status=status,
            message=f"Valid={validation_result.is_valid}",
        )

    def execution_check() -> HealthCheck:
        status = (
            ComponentStatus.HEALTHY
            if execution_analysis.quality_score >= 70.0
            else ComponentStatus.DEGRADED
        )
        return HealthCheck(
            check_name="execution_quality",
            status=status,
            message=f"Score={execution_analysis.quality_score:.1f}",
        )

    dashboard.register_component(
        "regime",
        "Market Regime Analyzer",
        ComponentType.STRATEGY,
        regime_check,
    )
    dashboard.register_component(
        "risk",
        "Adaptive Risk Manager",
        ComponentType.RISK_MANAGER,
        risk_check,
    )
    dashboard.register_component(
        "sizer",
        "Dynamic Position Sizer",
        ComponentType.STRATEGY,
        sizing_check,
    )
    dashboard.register_component(
        "validator",
        "Order Validator",
        ComponentType.EXECUTION,
        validation_check,
    )
    dashboard.register_component(
        "execution",
        "Execution Analyzer",
        ComponentType.EXECUTION,
        execution_check,
    )

    results = dashboard.run_health_checks()

    assert results["regime"].status == ComponentStatus.HEALTHY
    assert results["risk"].status == ComponentStatus.HEALTHY
    assert results["sizer"].status == ComponentStatus.HEALTHY
    assert results["validator"].status == ComponentStatus.HEALTHY
    assert results["execution"].status == ComponentStatus.HEALTHY

    dashboard.update_system_metrics(
        SystemMetrics(
            cpu_usage_percent=min(100.0, regime_metrics.volatility * 1000),
            memory_usage_percent=min(100.0, risk_metrics.max_drawdown * 100),
            disk_usage_percent=50.0,
            network_latency_ms=execution_analysis.latency.total_latency_ms,
            active_connections=1,
            queue_depth=0,
            messages_per_second=1.0,
            orders_per_minute=1.0,
        )
    )

    summary = dashboard.get_system_summary()
    assert summary.overall_status == ComponentStatus.HEALTHY
    assert summary.healthy_components == 5
    assert summary.unhealthy_components == 0

    stored_metrics = dashboard.get_system_metrics()
    assert stored_metrics.network_latency_ms == execution_analysis.latency.total_latency_ms
