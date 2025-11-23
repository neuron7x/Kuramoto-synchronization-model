# Backtest Module

## Overview

The `backtest` module provides a comprehensive framework for testing trading strategies against historical data. It features event-driven backtesting, realistic order simulation, transaction cost modeling, and advanced performance analytics.

## Purpose

This module enables rigorous strategy validation through:

- **Event-Driven Backtesting**: Realistic simulation of live trading conditions
- **Order Execution Simulation**: High-fidelity modeling of order fills and slippage
- **Transaction Cost Analysis**: Accurate modeling of fees, slippage, and market impact
- **Monte Carlo Simulation**: Assess strategy robustness under various scenarios
- **Walk-Forward Analysis**: Out-of-sample testing with rolling windows
- **Synthetic Scenario Testing**: Test strategies under extreme market conditions
- **Performance Attribution**: Detailed breakdown of returns and risk metrics

## Key Features

- 🎯 **Event-Driven Engine**: Prevents look-ahead bias with realistic event ordering
- 📊 **Comprehensive Metrics**: 50+ performance metrics including Sharpe, Sortino, Calmar
- 💰 **Transaction Costs**: Configurable fees, slippage, and market impact models
- 🎲 **Monte Carlo**: Generate thousands of scenarios to assess robustness
- 📈 **Market Calendar**: Respect exchange holidays and trading hours
- 🔀 **Multiple Strategies**: Test and compare multiple strategies simultaneously
- 🧪 **Synthetic Data**: Generate controlled scenarios for stress testing
- ⚡ **Fast Execution**: Vectorized operations for rapid iteration

## Module Structure

```
backtest/
├── __init__.py                  # Public API exports
├── engine.py                    # Core backtesting engine
├── event_driven.py             # Event-driven backtesting implementation
├── events.py                   # Backtesting event types
├── execution_simulation.py     # Order execution simulator
├── market_calendar.py          # Trading calendar and hours
├── monte_carlo.py              # Monte Carlo simulation framework
├── performance.py              # Performance metrics calculation
├── resampling.py               # Bootstrap and resampling methods
├── strategies/                 # Example strategy implementations
├── synthetic.py                # Synthetic data and scenario generation
├── time_splits.py              # Train/test split utilities
└── transaction_costs.py        # Transaction cost models
```

## Technology Stack

- **Python**: 3.11+ with full type annotations
- **NumPy**: Vectorized numerical operations
- **Pandas**: Time series data handling
- **Exchange-Calendars**: Market trading schedules
- **SciPy**: Statistical analysis and optimization
- **Numba**: JIT compilation for performance-critical loops

## Installation

```bash
# Base installation
pip install -e .

# With development tools
pip install -e ".[dev]"
```

## Usage Examples

### Basic Backtesting

```python
from backtest import BacktestEngine, LatencyConfig, OrderBookConfig
from strategies import MomentumStrategy

# Configure backtest engine
engine = BacktestEngine(
    initial_capital=100000,
    latency_config=LatencyConfig(
        order_latency_ms=50,
        data_latency_ms=10
    ),
    orderbook_config=OrderBookConfig(
        depth_levels=10,
        use_realistic_liquidity=True
    )
)

# Add strategy
strategy = MomentumStrategy(lookback=20, threshold=0.02)
engine.add_strategy("momentum", strategy)

# Run backtest
results = engine.run(
    data=historical_data,
    start_date="2023-01-01",
    end_date="2023-12-31"
)

# Analyze results
print(f"Total Return: {results.total_return:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")
print(f"Win Rate: {results.win_rate:.2%}")
```

### Event-Driven Backtesting

```python
from backtest import EventDrivenBacktest, MarketDataEvent, OrderEvent

class MyStrategy:
    def on_market_data(self, event: MarketDataEvent):
        """React to market data updates"""
        if self.should_buy(event.data):
            return OrderEvent(
                symbol=event.symbol,
                side="buy",
                quantity=100,
                order_type="limit",
                limit_price=event.data.close * 0.99
            )
    
    def on_order_filled(self, event: OrderFilledEvent):
        """Handle order fill confirmations"""
        print(f"Order filled: {event.quantity} @ {event.fill_price}")

# Run event-driven backtest
backtest = EventDrivenBacktest(initial_capital=100000)
backtest.add_strategy(MyStrategy())
results = backtest.run(data=historical_data)
```

### Transaction Cost Modeling

```python
from backtest import TransactionCostModel

# Configure realistic transaction costs
cost_model = TransactionCostModel(
    commission_bps=5,        # 5 bps commission
    slippage_bps=2,          # 2 bps average slippage
    market_impact_model="square_root",  # Almgren-Chriss model
    bid_ask_spread_bps=1     # 1 bps spread
)

# Apply to backtest
engine = BacktestEngine(
    initial_capital=100000,
    transaction_cost_model=cost_model
)

results = engine.run(data=historical_data)

# Analyze cost impact
print(f"Total Commissions: ${results.total_commissions:.2f}")
print(f"Total Slippage: ${results.total_slippage:.2f}")
print(f"Total Market Impact: ${results.total_impact:.2f}")
```

### Monte Carlo Simulation

```python
from backtest import MonteCarloSimulator, MonteCarloConfig

# Configure Monte Carlo simulation
simulator = MonteCarloSimulator(
    config=MonteCarloConfig(
        num_simulations=10000,
        resample_method="bootstrap",  # or "parametric"
        confidence_levels=[0.05, 0.25, 0.5, 0.75, 0.95]
    )
)

# Run simulations
mc_results = simulator.run(
    strategy=my_strategy,
    data=historical_data,
    num_paths=10000
)

# Analyze distribution
print(f"Expected Return: {mc_results.mean_return:.2%}")
print(f"5th Percentile: {mc_results.percentile_5:.2%}")
print(f"95th Percentile: {mc_results.percentile_95:.2%}")
print(f"Probability of Profit: {mc_results.prob_profit:.2%}")

# Plot distribution
mc_results.plot_distribution(output="monte_carlo_results.png")
```

### Walk-Forward Analysis

```python
from backtest import WalkForwardAnalysis, WalkForwardConfig

# Configure walk-forward analysis
wfa = WalkForwardAnalysis(
    config=WalkForwardConfig(
        train_period_days=252,  # 1 year training
        test_period_days=63,    # 3 months testing
        step_size_days=21,      # Roll forward monthly
        optimization_metric="sharpe_ratio"
    )
)

# Run walk-forward test
wf_results = wfa.run(
    strategy_class=MomentumStrategy,
    param_grid={
        "lookback": [10, 20, 30, 50],
        "threshold": [0.01, 0.02, 0.03]
    },
    data=historical_data
)

# Analyze out-of-sample performance
print(f"In-Sample Sharpe: {wf_results.in_sample_sharpe:.2f}")
print(f"Out-of-Sample Sharpe: {wf_results.out_of_sample_sharpe:.2f}")
print(f"Degradation: {wf_results.degradation:.2%}")
```

### Synthetic Scenario Testing

```python
from backtest import SyntheticScenario, LiquidityShock, StructuralBreak

# Create synthetic stress scenarios
scenarios = [
    LiquidityShock(
        magnitude=0.5,      # 50% reduction in liquidity
        duration_days=5,
        start_date="2023-03-10"
    ),
    StructuralBreak(
        volatility_multiplier=2.5,  # 2.5x normal volatility
        correlation_change=-0.3,     # Correlations decrease
        duration_days=10
    )
]

# Test strategy under scenarios
for scenario in scenarios:
    synthetic_data = scenario.apply_to(historical_data)
    results = engine.run(data=synthetic_data)
    
    print(f"Scenario: {scenario.name}")
    print(f"Return: {results.total_return:.2%}")
    print(f"Max Drawdown: {results.max_drawdown:.2%}")
```

### Performance Report Generation

```python
from backtest import PerformanceReport, export_performance_report

# Generate comprehensive performance report
report = PerformanceReport.from_results(backtest_results)

# Export to multiple formats
export_performance_report(
    report,
    formats=["html", "pdf", "json"],
    output_dir="reports/backtest_results"
)

# Access individual metrics
print(f"CAGR: {report.cagr:.2%}")
print(f"Volatility: {report.volatility:.2%}")
print(f"Sharpe Ratio: {report.sharpe_ratio:.2f}")
print(f"Sortino Ratio: {report.sortino_ratio:.2f}")
print(f"Calmar Ratio: {report.calmar_ratio:.2f}")
print(f"Max Drawdown: {report.max_drawdown:.2%}")
print(f"Win Rate: {report.win_rate:.2%}")
print(f"Profit Factor: {report.profit_factor:.2f}")
```

### Multiple Strategy Comparison

```python
from backtest import StrategyComparison

# Compare multiple strategies
strategies = {
    "momentum": MomentumStrategy(lookback=20),
    "mean_reversion": MeanReversionStrategy(lookback=30),
    "breakout": BreakoutStrategy(atr_multiplier=2.0)
}

comparison = StrategyComparison(strategies)
results = comparison.run(data=historical_data)

# Compare metrics
comparison_df = results.to_dataframe()
print(comparison_df)

# Generate comparison chart
results.plot_equity_curves(output="strategy_comparison.png")
```

## Performance Metrics

The backtest module calculates an extensive set of metrics:

### Return Metrics
- Total Return, CAGR (Compound Annual Growth Rate)
- Daily/Monthly/Annual Returns
- Cumulative Returns
- Rolling Returns

### Risk Metrics
- Volatility (annualized)
- Maximum Drawdown, Average Drawdown
- Drawdown Duration
- Value at Risk (VaR), Conditional VaR
- Downside Deviation

### Risk-Adjusted Returns
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio
- Omega Ratio
- Information Ratio

### Trade Statistics
- Total Trades, Win Rate
- Average Win/Loss
- Profit Factor
- Expectancy
- Average Holding Period

### Advanced Metrics
- Tail Ratio
- Common Sense Ratio
- Outlier Win/Loss Ratio
- Recovery Factor
- Ulcer Index

## Running Tests

```bash
# Run all backtest tests
pytest tests/unit/backtest -v

# Run with coverage
pytest tests/unit/backtest --cov=backtest --cov-report=html

# Run performance tests
pytest tests/unit/backtest -m performance -v

# Run Monte Carlo tests (slow)
pytest tests/unit/backtest/test_monte_carlo.py -v
```

## Configuration

Configure backtest via YAML:

```yaml
# config/backtest.yaml
backtest:
  engine:
    initial_capital: 100000
    allow_fractional_shares: true
    
  latency:
    order_latency_ms: 50
    data_latency_ms: 10
    fill_latency_ms: 20
    
  orderbook:
    depth_levels: 10
    use_realistic_liquidity: true
    slippage_model: "volume_based"
    
  transaction_costs:
    commission_bps: 5
    slippage_bps: 2
    market_impact_model: "square_root"
    bid_ask_spread_bps: 1
    
  calendar:
    exchange: "NYSE"
    respect_holidays: true
    trading_start: "09:30"
    trading_end: "16:00"
```

## Best Practices

1. **Avoid Look-Ahead Bias**: Use event-driven backtesting
2. **Model Transaction Costs**: Always include realistic costs
3. **Use Walk-Forward**: Validate with out-of-sample testing
4. **Test Multiple Scenarios**: Use Monte Carlo and synthetic scenarios
5. **Respect Trading Calendar**: Account for holidays and hours
6. **Set Realistic Parameters**: Use achievable execution speeds
7. **Monitor Overfitting**: Compare in-sample vs. out-of-sample performance

## Common Pitfalls

### Look-Ahead Bias
```python
# ❌ WRONG: Using future data
signal = data["close"].rolling(20).mean().shift(-1)  # Looks ahead!

# ✅ CORRECT: Only use past data
signal = data["close"].rolling(20).mean()
```

### Survivorship Bias
```python
# ❌ WRONG: Only testing on survivors
data = load_current_sp500_stocks()

# ✅ CORRECT: Include delisted stocks
data = load_historical_sp500_stocks(include_delisted=True)
```

### Ignoring Transaction Costs
```python
# ❌ WRONG: No cost model
engine = BacktestEngine(initial_capital=100000)

# ✅ CORRECT: Include realistic costs
engine = BacktestEngine(
    initial_capital=100000,
    transaction_cost_model=TransactionCostModel(commission_bps=5)
)
```

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                   Backtest Engine                          │
├────────────────────────────────────────────────────────────┤
│  Event Loop  │  Strategy Manager  │  Performance Analyzer │
├────────────────────────────────────────────────────────────┤
│  Execution Simulator                                       │
│  ├─ Order Matching  ├─ Slippage Model  ├─ Cost Model     │
├────────────────────────────────────────────────────────────┤
│  Data Layer                                                │
│  ├─ Market Data  ├─ Order Book  ├─ Trading Calendar      │
└────────────────────────────────────────────────────────────┘
```

## Integration

### With Execution Module
- Shares order execution models
- Uses same transaction cost framework

### With Analytics Module  
- Exports metrics for portfolio attribution
- Provides performance data for TCA

### With Strategies Module
- Tests strategy implementations
- Validates strategy parameters

## Related Modules

- [`execution`](../execution/README.md): Order execution and simulation
- [`analytics`](../analytics/README.md): Performance analytics
- [`strategies`](../strategies/README.md): Trading strategies
- [`core`](../core/README.md): Core indicators and data

## Documentation

- [API Reference](https://docs.tradepulse.io/api/backtest)
- [Backtesting Guide](https://docs.tradepulse.io/guides/backtesting)
- [Performance Metrics](https://docs.tradepulse.io/guides/metrics)
- [Walk-Forward Analysis](https://docs.tradepulse.io/guides/walk-forward)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for licensing information.

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [Documentation](https://docs.tradepulse.io)
- [Community](https://github.com/neuron7x/TradePulse/discussions)
