"""
Integrated Risk Management Example

Демонстрація роботи всіх нових модулів разом:
- Adaptive Risk Manager
- Market Regime Analyzer
- Dynamic Position Sizer
- Agent Coordinator
"""

import numpy as np

from modules.adaptive_risk_manager import AdaptiveRiskManager
from modules.agent_coordinator import AgentCoordinator, AgentType, Priority
from modules.dynamic_position_sizer import DynamicPositionSizer, SizingMethod
from modules.market_regime_analyzer import MarketRegimeAnalyzer
from core.utils.determinism import seed_numpy


def generate_market_data(n_bars=200, trend=0.0005, volatility=0.015):
    """Generate synthetic market data"""
    seed_numpy()

    # Price series
    returns = np.random.normal(trend, volatility, n_bars)
    prices = 100 * np.exp(np.cumsum(returns))

    return prices, returns


def main():
    print("=" * 80)
    print("TradePulse Integrated Risk Management System")
    print("=" * 80)
    print()

    # Initialize components
    print("🔧 Initializing components...")
    risk_manager = AdaptiveRiskManager(
        base_capital=100000.0, risk_tolerance=0.02, var_window=100
    )

    regime_analyzer = MarketRegimeAnalyzer(regime_window=50, transition_threshold=0.7)

    position_sizer = DynamicPositionSizer(
        base_capital=100000.0, default_method=SizingMethod.ADAPTIVE, kelly_fraction=0.25
    )

    coordinator = AgentCoordinator(max_concurrent_tasks=10)

    print("✅ Components initialized")
    print()

    # Register agents with coordinator
    print("📝 Registering agents...")
    coordinator.register_agent(
        agent_id="risk_mgr",
        agent_type=AgentType.RISK_MANAGER,
        name="Adaptive Risk Manager",
        description="Manages portfolio risk dynamically",
        handler=risk_manager,
        priority=Priority.HIGH,
    )

    coordinator.register_agent(
        agent_id="regime_analyzer",
        agent_type=AgentType.MARKET_ANALYZER,
        name="Market Regime Analyzer",
        description="Identifies market regimes",
        handler=regime_analyzer,
        priority=Priority.NORMAL,
    )

    coordinator.register_agent(
        agent_id="position_sizer",
        agent_type=AgentType.POSITION_SIZER,
        name="Dynamic Position Sizer",
        description="Calculates optimal position sizes",
        handler=position_sizer,
        priority=Priority.NORMAL,
    )

    print("✅ Agents registered")
    print()

    # Generate market data
    print("📊 Generating market data...")
    prices, returns = generate_market_data(n_bars=200)
    print(f"   Generated {len(prices)} price bars")
    print()

    # Analyze market regime
    print("🔍 Analyzing market regime...")
    regime_metrics = regime_analyzer.classify_regime(prices)

    print(f"   Regime Type: {regime_metrics.regime_type.value}")
    print(f"   Trend Strength: {regime_metrics.trend_strength.value}")
    print(f"   Hurst Exponent: {regime_metrics.hurst_exponent:.3f}")
    print(f"   Volatility: {regime_metrics.volatility:.4f}")
    print(f"   Confidence: {regime_metrics.regime_confidence:.2f}")
    print()

    # Get strategy recommendations based on regime
    recommendations = regime_analyzer.recommend_strategy_parameters(regime_metrics)
    print("📋 Strategy Recommendations:")
    print(
        f"   Position Size Multiplier: {recommendations['position_size_multiplier']:.2f}"
    )
    print(f"   Stop Loss Multiplier: {recommendations['stop_loss_multiplier']:.2f}")
    print(f"   Take Profit Multiplier: {recommendations['take_profit_multiplier']:.2f}")
    print(f"   Holding Period Target: {recommendations['holding_period_target']} bars")
    print()

    # Update risk manager with returns
    print("💹 Updating risk metrics...")
    risk_manager.update_from_returns(returns[:100])

    risk_metrics = risk_manager.calculate_risk_metrics(returns[:100])
    print(f"   VaR (95%): {risk_metrics.var_95:.4f}")
    print(f"   CVaR (95%): {risk_metrics.cvar_95:.4f}")
    print(f"   Sharpe Ratio: {risk_metrics.sharpe_ratio:.2f}")
    print(f"   Max Drawdown: {risk_metrics.max_drawdown:.2%}")
    print()

    # Update position limits
    print("🎯 Calculating position limits...")
    current_volatility = np.std(returns[-20:])
    position_limit = risk_manager.update_position_limits(
        symbol="BTCUSD", volatility=current_volatility
    )

    print(f"   Symbol: {position_limit.symbol}")
    print(f"   Max Position Size: ${position_limit.max_position_size:,.2f}")
    print(f"   Max Leverage: {position_limit.max_leverage:.2f}x")
    print(f"   Stop Loss: {position_limit.stop_loss_pct:.2%}")
    print(f"   Take Profit: {position_limit.take_profit_pct:.2%}")
    print()

    # Calculate position size
    print("📏 Calculating optimal position size...")
    current_price = prices[-1]
    signal_confidence = 0.75  # Example confidence level

    position_result = position_sizer.calculate_adaptive_size(
        symbol="BTCUSD",
        price=current_price,
        volatility=current_volatility,
        confidence=signal_confidence,
        win_rate=0.55,
        avg_win=0.025,
        avg_loss=0.015,
    )

    print(f"   Symbol: {position_result.symbol}")
    print(f"   Recommended Size: ${position_result.recommended_size:,.2f}")
    print(f"   Kelly Fraction: {position_result.kelly_fraction:.3f}")
    print(f"   Volatility Adjustment: {position_result.volatility_adjustment:.2f}x")
    print(f"   Confidence: {position_result.confidence:.2%}")
    print()

    # Simulate portfolio
    print("💼 Simulating portfolio...")
    positions = {
        "BTCUSD": position_result.recommended_size / current_price,
        "ETHUSD": 5.0,
        "SOLUSD": 100.0,
    }
    prices_dict = {"BTCUSD": current_price, "ETHUSD": 3000.0, "SOLUSD": 150.0}

    portfolio_risk = risk_manager.assess_portfolio_risk(positions, prices_dict)

    print(f"   Total Exposure: ${portfolio_risk.total_exposure:,.2f}")
    print(f"   Max Exposure: ${portfolio_risk.max_exposure:,.2f}")
    print(f"   Utilization: {portfolio_risk.utilization_pct:.1f}%")
    print(f"   Risk Level: {portfolio_risk.risk_level.value}")
    print(f"   Active Positions: {portfolio_risk.active_positions}")
    print()

    # Check if risk reduction needed
    should_reduce = risk_manager.should_reduce_risk(portfolio_risk)
    print(f"   ⚠️  Risk Reduction Needed: {'YES' if should_reduce else 'NO'}")
    print()

    # Coordinator summary
    print("🎛️  Coordinator Status:")
    system_health = coordinator.get_system_health()
    print(f"   System Health Score: {system_health['health_score']}")
    print(f"   Total Agents: {system_health['total_agents']}")
    print(f"   Active Agents: {system_health['active_agents']}")
    print()

    # Submit coordination tasks
    print("📤 Submitting coordination tasks...")
    task_ids = []

    task_ids.append(
        coordinator.submit_task(
            agent_id="risk_mgr",
            task_type="risk_check",
            payload={"portfolio": positions},
            priority=Priority.HIGH,
        )
    )

    task_ids.append(
        coordinator.submit_task(
            agent_id="regime_analyzer",
            task_type="regime_update",
            payload={"prices": prices[-50:]},
            priority=Priority.NORMAL,
        )
    )

    print(f"   Submitted {len(task_ids)} tasks")
    print()

    # Get final summaries
    print("📝 Final Summaries:")
    print()

    print("   Risk Manager Summary:")
    risk_summary = risk_manager.get_risk_summary()
    for key, value in risk_summary.items():
        print(f"      {key}: {value}")
    print()

    print("   Regime Analyzer Summary:")
    regime_summary = regime_analyzer.get_regime_summary()
    for key, value in regime_summary.items():
        print(f"      {key}: {value}")
    print()

    print("   Position Sizer Summary:")
    sizer_summary = position_sizer.get_summary()
    for key, value in sizer_summary.items():
        print(f"      {key}: {value}")
    print()

    print("   Coordinator Summary:")
    coord_summary = coordinator.get_coordination_summary()
    print(f"      Registered Agents: {coord_summary['registered_agents']}")
    print(f"      Queue Size: {coord_summary['queue_size']}")
    print(f"      Decisions Made: {coord_summary['decisions_made']}")
    print()

    print("=" * 80)
    print("✅ Integrated Risk Management System Demo Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
