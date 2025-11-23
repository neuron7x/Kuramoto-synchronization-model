# Analytics Module

## Overview

The `analytics` module provides comprehensive tools for portfolio analysis, performance attribution, execution quality assessment, and risk analytics. It enables traders and portfolio managers to evaluate strategy performance, analyze market impact, and ensure environment parity across different deployment stages.

## Purpose

This module delivers professional-grade analytics capabilities:

- **Portfolio Attribution**: Break down returns by source (alpha, beta, specific returns)
- **Execution Quality**: Measure and analyze trade execution effectiveness
- **Transaction Cost Analysis (TCA)**: Evaluate slippage and implementation shortfall
- **Liquidity Impact**: Model and forecast market impact of large orders
- **Risk Analytics**: Portfolio risk decomposition and VaR calculations
- **Environment Parity**: Ensure consistency across development, staging, and production
- **Regime Analysis**: Track and analyze market regime transitions

## Key Features

- 📊 **Multi-Factor Attribution**: Decompose portfolio returns into contributing factors
- 💰 **Cost Analysis**: Comprehensive TCA with multiple benchmarks
- 📈 **Signal Tracking**: Monitor signal quality and decay over time
- 🎯 **Execution Forecasting**: Predict market impact before order placement
- ⚖️ **Risk Decomposition**: Break down portfolio risk by instrument and factor
- 🔍 **Performance Analytics**: Sharpe ratio, Sortino ratio, max drawdown, and more
- 🌡️ **Regime Detection**: Identify market phases (trending, mean-reverting, volatile)
- ✅ **Parity Checking**: Validate metric consistency across environments

## Module Structure

```
analytics/
├── __init__.py                    # Public API exports
├── _config_sanitizer.py          # Configuration validation
├── amm_metrics.py                # Automated Market Maker metrics
├── code_health/                  # Code quality analytics
├── demos/                        # Example analytics notebooks
├── environment_parity.py         # Environment consistency checker
├── execution_quality.py          # Execution performance metrics
├── fpma/                         # Fractal Project Method Analytics
├── liquidity_impact.py           # Market impact modeling
├── portfolio_attribution.py      # Portfolio return attribution
├── portfolio_risk.py             # Risk analytics and decomposition
├── regime/                       # Market regime detection
├── runner.py                     # Analytics job runner
├── signals/                      # Signal quality analytics
├── staging/                      # Staging environment tools
├── tca.py                        # Transaction Cost Analysis
├── tests/                        # Test suite
└── tracking.py                   # Performance tracking utilities
```

## Technology Stack

- **Python**: 3.11+ with full type annotations
- **NumPy**: Numerical computations
- **Pandas**: Time series analysis and data manipulation
- **SciPy**: Statistical analysis and optimization
- **Statsmodels**: Statistical modeling and hypothesis testing
- **Scikit-learn**: Machine learning for regime detection
- **Matplotlib/Plotly**: Visualization (optional, for demos)

## Installation

```bash
# Core installation includes analytics
pip install -e .

# With advanced analytics features
pip install -e ".[neuro_advanced]"

# Development mode with testing tools
pip install -e ".[dev]"
```

## Usage Examples

### Portfolio Attribution

```python
from analytics import PortfolioAttributionEngine, PortfolioAttributionConfig

# Configure attribution engine
config = PortfolioAttributionConfig(
    benchmark="SPY",
    attribution_method="brinson",
    factor_model="fama_french_3"
)

engine = PortfolioAttributionEngine(config)

# Run attribution analysis
report = engine.compute_attribution(
    portfolio_returns=portfolio_df,
    benchmark_returns=benchmark_df,
    factor_returns=factors_df
)

print(f"Alpha: {report.alpha:.4f}")
print(f"Beta: {report.beta:.4f}")
print(f"Tracking Error: {report.tracking_error:.4f}")
```

### Transaction Cost Analysis

```python
from analytics import TransactionCostAnalyzer, TCAConfig

# Setup TCA analyzer
tca = TransactionCostAnalyzer(
    config=TCAConfig(
        benchmark="arrival_price",
        slippage_tolerance_bps=10,
        impact_model="almgren_chriss"
    )
)

# Analyze executed orders
analysis = tca.analyze_execution(
    orders=executed_orders_df,
    market_data=market_df
)

print(f"Average Slippage: {analysis.avg_slippage_bps:.2f} bps")
print(f"Implementation Shortfall: {analysis.implementation_shortfall:.4f}")
print(f"Market Impact: {analysis.market_impact:.4f}")
```

### Liquidity Impact Modeling

```python
from analytics import LiquidityImpactModel, LiquidityImpactConfig

# Configure impact model
model = LiquidityImpactModel(
    config=LiquidityImpactConfig(
        impact_type="square_root",
        decay_factor=0.5,
        participation_rate=0.1
    )
)

# Forecast execution impact
forecast = model.forecast_impact(
    symbol="AAPL",
    order_size=10000,
    average_daily_volume=50000000,
    volatility=0.25,
    order_book=current_orderbook
)

print(f"Expected Impact: {forecast.expected_impact:.4f}")
print(f"Optimal VWAP Strategy: {forecast.optimal_strategy}")
```

### Environment Parity Checking

```python
from analytics import EnvironmentParityChecker, EnvironmentParityConfig

# Configure parity checker
checker = EnvironmentParityChecker(
    config=EnvironmentParityConfig(
        tolerance={"sharpe_ratio": 0.1, "max_drawdown": 0.05},
        metrics=["sharpe_ratio", "total_return", "max_drawdown"]
    )
)

# Compare environments
report = checker.check_parity(
    staging_metrics=staging_results,
    production_metrics=prod_results
)

if report.has_deviations:
    for deviation in report.deviations:
        print(f"⚠️ {deviation.metric}: {deviation.difference:.4f}")
else:
    print("✅ Environment parity maintained")
```

### Portfolio Risk Analytics

```python
from analytics import PortfolioRiskAnalyzer, RiskConfig

# Setup risk analyzer
analyzer = PortfolioRiskAnalyzer(
    config=RiskConfig(
        var_confidence=0.95,
        cvar_confidence=0.99,
        lookback_days=252
    )
)

# Compute risk metrics
risk_report = analyzer.analyze(
    positions=portfolio_positions,
    returns=historical_returns,
    covariance_matrix=cov_matrix
)

print(f"Portfolio VaR (95%): {risk_report.var_95:.4f}")
print(f"CVaR (99%): {risk_report.cvar_99:.4f}")
print(f"Beta to Market: {risk_report.beta:.4f}")
print(f"Diversification Ratio: {risk_report.diversification_ratio:.4f}")
```

## Running Tests

```bash
# Run all analytics tests
pytest analytics/tests/ -v

# Run with coverage report
pytest analytics/tests/ --cov=analytics --cov-report=html

# Run specific test suite
pytest analytics/tests/test_portfolio_attribution.py -v

# Run fast tests only (exclude slow computations)
pytest analytics/tests/ -m "not slow" -v
```

## Configuration

Configure analytics via YAML or environment variables:

```yaml
# config/analytics.yaml
analytics:
  attribution:
    method: brinson
    factor_model: fama_french_3
    benchmark: SPY
  
  tca:
    benchmark: arrival_price
    slippage_tolerance_bps: 10
    impact_model: almgren_chriss
  
  risk:
    var_confidence: 0.95
    cvar_confidence: 0.99
    lookback_days: 252
    monte_carlo_simulations: 10000
  
  environment_parity:
    enabled: true
    tolerance:
      sharpe_ratio: 0.1
      max_drawdown: 0.05
      total_return: 0.05
```

Environment variable overrides:
```bash
export ANALYTICS__TCA__SLIPPAGE_TOLERANCE_BPS=15
export ANALYTICS__RISK__VAR_CONFIDENCE=0.99
```

## Analytics Reports

The module generates professional reports in multiple formats:

### Attribution Report

```python
report = engine.compute_attribution(...)

# Export to JSON
report.to_json("attribution_report.json")

# Export to PDF (requires reportlab)
report.to_pdf("attribution_report.pdf")

# Export to Excel
report.to_excel("attribution_report.xlsx")
```

### Performance Dashboard

```python
from analytics import PerformanceDashboard

dashboard = PerformanceDashboard(portfolio_returns)
dashboard.generate(output="performance_dashboard.html")
```

## Performance Metrics

The analytics module computes a comprehensive set of metrics:

### Return Metrics
- Total Return, Annualized Return
- Geometric vs. Arithmetic Returns
- Rolling Returns (various windows)

### Risk Metrics
- Volatility (annualized standard deviation)
- Value at Risk (VaR) at multiple confidence levels
- Conditional Value at Risk (CVaR)
- Maximum Drawdown, Average Drawdown
- Downside Deviation
- Beta, Correlation to benchmark

### Risk-Adjusted Returns
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio
- Information Ratio
- Treynor Ratio
- Jensen's Alpha

### Attribution Metrics
- Alpha (excess return)
- Beta (systematic risk)
- Factor exposures
- Specific returns
- Selection effects
- Allocation effects

## Market Regime Detection

```python
from analytics.regime import RegimeDetector, RegimeConfig

detector = RegimeDetector(
    config=RegimeConfig(
        n_regimes=3,
        features=["volatility", "trend", "correlation"],
        detection_method="hmm"  # Hidden Markov Model
    )
)

# Detect current regime
regime = detector.detect_regime(market_data)
print(f"Current Regime: {regime.label}")  # e.g., "trending", "mean_reverting"
print(f"Confidence: {regime.confidence:.2f}")

# Get regime transition matrix
transitions = detector.get_transition_matrix()
```

## Best Practices

1. **Regular Monitoring**: Run attribution analysis at least daily in production
2. **Benchmark Selection**: Choose appropriate benchmarks for your strategy type
3. **Impact Modeling**: Use liquidity forecasts before placing large orders
4. **Environment Parity**: Always validate staging results match production
5. **Risk Budgeting**: Set VaR limits and monitor continuously
6. **TCA Analysis**: Review execution quality weekly to identify broker issues

## Architecture

The analytics module follows a service-oriented architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Analytics API Layer                      │
├─────────────────────────────────────────────────────────────┤
│  Attribution │ TCA │ Risk │ Liquidity │ Parity │ Tracking │
├─────────────────────────────────────────────────────────────┤
│                   Analytics Engine Layer                    │
│  ├─ Computation Engine  ├─ Report Generator                │
│  ├─ Data Aggregator     ├─ Metric Calculators              │
├─────────────────────────────────────────────────────────────┤
│                      Data Access Layer                      │
│  ├─ Time Series Store   ├─ Position Repository             │
│  ├─ Market Data Cache   ├─ Benchmark Provider              │
└─────────────────────────────────────────────────────────────┘
```

## Integration Points

### With Execution Module
- Receives order execution data for TCA
- Provides market impact forecasts for order sizing

### With Backtest Module
- Computes performance metrics for backtests
- Validates backtest results against live performance

### With Core Module
- Uses core indicators for regime detection
- Leverages event bus for real-time analytics updates

### With Observability Module
- Exports metrics to Prometheus
- Sends alerts on attribution anomalies

## Related Modules

- [`execution`](../execution/README.md): Order execution and management
- [`backtest`](../backtest/README.md): Backtesting framework
- [`core`](../core/README.md): Core indicators and infrastructure
- [`observability`](../observability/README.md): Metrics and monitoring
- [`strategies`](../strategies/README.md): Trading strategies

## Documentation

- [API Reference](https://docs.tradepulse.io/api/analytics)
- [Attribution Guide](https://docs.tradepulse.io/guides/attribution)
- [TCA Guide](https://docs.tradepulse.io/guides/tca)
- [Risk Analytics Guide](https://docs.tradepulse.io/guides/risk)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Code standards and formatting
- Test coverage requirements (>98%)
- Documentation guidelines
- Pull request workflow

## License

See [LICENSE](../LICENSE) for details. Part of the TradePulse proprietary codebase.

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [Documentation](https://docs.tradepulse.io)
- [Community Discussions](https://github.com/neuron7x/TradePulse/discussions)
