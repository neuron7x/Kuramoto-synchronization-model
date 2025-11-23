# Execution Module

## Overview

The `execution` module handles all aspects of order execution, order lifecycle management, position sizing, risk controls, and exchange connectivity. It provides production-ready components for live trading, paper trading, and order routing across multiple exchanges.

## Purpose

This module delivers enterprise-grade execution capabilities:

- **Order Management System (OMS)**: Complete order lifecycle from creation to settlement
- **Exchange Connectivity**: Unified interface to multiple exchanges via CCXT and custom connectors
- **Risk Management**: Pre-trade and post-trade risk controls, position limits, and compliance checks
- **Paper Trading**: High-fidelity simulation environment for testing strategies
- **Position Sizing**: Optimal capital allocation with risk constraints
- **Liquidation Management**: Automated liquidation of underwater positions
- **Smart Order Routing**: Intelligent order routing for best execution
- **Compliance Monitoring**: Regulatory compliance checks and audit trails

## Key Features

- 🔄 **Order Lifecycle Management**: Track orders from submission to completion
- 🌐 **Multi-Exchange Support**: Trade on Binance, Coinbase, Kraken, and more via CCXT
- 🛡️ **Risk Controls**: Pre-trade risk checks, position limits, and stop-loss automation
- 📊 **Real-Time Monitoring**: Live order book, position tracking, and P&L updates
- 🎯 **Execution Algorithms**: TWAP, VWAP, POV, and custom algorithms
- 📝 **Order Ledger**: Immutable audit trail of all order events
- 💰 **Capital Optimization**: Kelly criterion and modern portfolio theory allocation
- ⚡ **Low Latency**: Optimized for high-frequency trading scenarios
- 🧪 **Paper Trading Mode**: Zero-risk testing with realistic market simulation

## Module Structure

```
execution/
├── __init__.py                   # Public API exports
├── adapters/                     # Exchange adapter implementations
├── algorithms.py                 # Execution algorithms (TWAP, VWAP, etc.)
├── amm_runner.py                # Automated Market Maker execution
├── arbitrage/                    # Arbitrage opportunity detection
├── audit.py                      # Audit logging and compliance
├── canary.py                     # Canary deployment controller
├── capital_optimizer.py          # Capital allocation optimization
├── compliance.py                 # Compliance monitoring and checks
├── connectors.py                 # Base connector interface
├── hft/                         # High-frequency trading components
├── liquidation.py               # Position liquidation engine
├── live_loop.py                 # Live execution loop
├── metrics.py                   # Execution metrics collection
├── normalization.py             # Symbol and exchange normalization
├── oms.py                       # Order Management System
├── order.py                     # Order data structures
├── order_ledger.py              # Immutable order event ledger
├── order_lifecycle.py           # Order state machine
├── paper_trading.py             # Paper trading simulator
├── portfolio.py                 # Portfolio and position tracking
├── position_sizer.py            # Position sizing algorithms
├── resilience/                  # Resilience and retry logic
├── risk/                        # Risk management components
├── rollout.py                   # Progressive feature rollout
├── router.py                    # Smart order routing
├── session_snapshot.py          # Session state snapshots
├── shadow.py                    # Shadow trading mode
├── watchdog.py                  # Execution watchdog monitoring
└── workflows.py                 # Execution workflows
```

## Technology Stack

- **Python**: 3.11+ with type annotations
- **CCXT**: Multi-exchange cryptocurrency trading library
- **WebSockets**: Real-time market data and order updates
- **SQLAlchemy**: Order and position persistence
- **Redis**: High-performance caching and pub/sub
- **Tenacity**: Resilient retry logic with exponential backoff
- **AIOLimiter**: Rate limiting for API requests
- **Pydantic**: Request/response validation

## Installation

```bash
# Base installation
pip install -e .

# With exchange connectors
pip install -e ".[connectors]"

# Development mode
pip install -e ".[dev]"
```

## Usage Examples

### Order Management System

```python
from execution import OrderManagementSystem, OMSConfig

# Initialize OMS
oms = OrderManagementSystem(
    config=OMSConfig(
        mode="live",  # or "paper" for simulation
        exchange="binance",
        max_position_size=100000,
        enable_risk_checks=True
    )
)

# Submit a market order
order_id = await oms.submit_order(
    symbol="BTC/USDT",
    side="buy",
    order_type="market",
    quantity=0.5
)

# Track order status
status = await oms.get_order_status(order_id)
print(f"Order {order_id}: {status.state} at {status.fill_price}")
```

### Paper Trading

```python
from execution import PaperTradingSimulator, LatencyModel

# Configure paper trading with realistic latency
simulator = PaperTradingSimulator(
    initial_capital=100000,
    latency_model=LatencyModel(
        mean_latency_ms=50,
        std_latency_ms=15,
        distribution="normal"
    ),
    slippage_bps=5  # 5 basis points slippage
)

# Execute paper trade
result = await simulator.execute_order(
    symbol="AAPL",
    side="buy",
    quantity=100,
    order_type="market"
)

print(f"Paper trade executed at {result.fill_price}")
print(f"Total cost: ${result.total_cost:.2f}")
```

### Capital Optimization

```python
from execution import CapitalAllocationOptimizer, AllocationConstraints

# Setup optimizer with constraints
optimizer = CapitalAllocationOptimizer(
    constraints=AllocationConstraints(
        max_position_pct=0.2,  # Max 20% in any position
        max_leverage=2.0,
        min_position_size=100,
        sector_limits={"tech": 0.3, "finance": 0.25}
    )
)

# Optimize portfolio allocation
allocation = optimizer.optimize(
    signals=trading_signals,
    current_positions=portfolio.positions,
    available_capital=100000,
    risk_targets={"max_var": 0.02, "target_sharpe": 1.5}
)

print(f"Optimal allocation: {allocation.weights}")
print(f"Expected return: {allocation.expected_return:.4f}")
print(f"Expected volatility: {allocation.expected_volatility:.4f}")
```

### Risk Monitoring

```python
from execution import ComplianceMonitor, ComplianceReport

# Initialize compliance monitor
monitor = ComplianceMonitor(
    max_daily_loss=0.02,  # 2% max daily loss
    max_position_concentration=0.3,
    prohibited_symbols=["XYZ"],  # Blacklisted symbols
    trading_hours=("09:30", "16:00")
)

# Check compliance before order
violation = monitor.check_pre_trade(
    order=pending_order,
    portfolio=current_portfolio
)

if violation:
    print(f"⚠️ Compliance violation: {violation.reason}")
    # Cancel or modify order
else:
    # Proceed with execution
    await oms.submit_order(pending_order)
```

### Liquidation Management

```python
from execution import LiquidationEngine, LiquidationEngineConfig

# Configure liquidation engine
liquidator = LiquidationEngine(
    config=LiquidationEngineConfig(
        margin_call_threshold=0.3,  # 30% margin requirement
        liquidation_threshold=0.2,   # Liquidate at 20%
        max_slippage_tolerance=0.05  # 5% max slippage
    )
)

# Monitor margin account
margin_state = await liquidator.check_margin_account(account_id)

if margin_state.requires_liquidation:
    # Execute liquidation plan
    plan = liquidator.create_liquidation_plan(
        positions=margin_state.positions,
        urgency="high"
    )
    
    await liquidator.execute_plan(plan)
    print(f"Liquidated {len(plan.actions)} positions")
```

### Smart Order Routing

```python
from execution import SmartOrderRouter, RoutingConfig

# Configure router for best execution
router = SmartOrderRouter(
    config=RoutingConfig(
        exchanges=["binance", "coinbase", "kraken"],
        routing_strategy="best_price",  # or "lowest_fee", "highest_liquidity"
        min_liquidity=10000
    )
)

# Route order to best venue
routing_decision = await router.route_order(
    symbol="BTC/USDT",
    side="buy",
    quantity=1.5
)

print(f"Route to {routing_decision.exchange}")
print(f"Expected price: {routing_decision.expected_price}")
print(f"Total fees: {routing_decision.total_fees}")
```

### Execution Algorithms

```python
from execution import TwapAlgorithm, VwapAlgorithm

# Time-Weighted Average Price
twap = TwapAlgorithm(
    total_quantity=1000,
    duration_minutes=60,
    num_slices=12
)

# Execute TWAP strategy
async for slice_order in twap.execute(symbol="AAPL", side="buy"):
    result = await oms.submit_order(slice_order)
    print(f"TWAP slice filled at {result.avg_price}")

# Volume-Weighted Average Price
vwap = VwapAlgorithm(
    total_quantity=5000,
    target_participation=0.1  # 10% of volume
)

async for slice_order in vwap.execute(symbol="MSFT", side="sell"):
    result = await oms.submit_order(slice_order)
    print(f"VWAP slice filled at {result.avg_price}")
```

## Running Tests

```bash
# Run all execution tests
pytest tests/unit/execution -v

# Run with coverage
pytest tests/unit/execution --cov=execution --cov-report=html

# Run integration tests (requires exchange credentials)
pytest tests/integration/execution -v --exchange-env=staging

# Run paper trading tests
pytest tests/unit/execution/test_paper_trading.py -v
```

## Configuration

Configure execution via YAML or environment variables:

```yaml
# config/execution.yaml
execution:
  oms:
    mode: live  # or paper
    default_exchange: binance
    order_timeout_seconds: 30
    max_retries: 3
    
  risk:
    max_position_size: 100000
    max_daily_loss: 0.02
    max_leverage: 2.0
    position_limits:
      BTC: 10.0
      ETH: 100.0
    
  connectors:
    binance:
      api_key: ${BINANCE_API_KEY}
      api_secret: ${BINANCE_API_SECRET}
      testnet: false
      rate_limit: 1200  # requests per minute
    
  paper_trading:
    initial_capital: 100000
    slippage_bps: 5
    latency_mean_ms: 50
    latency_std_ms: 15
    
  capital_optimizer:
    method: kelly  # or "mean_variance", "risk_parity"
    max_position_pct: 0.2
    rebalance_threshold: 0.05
```

Environment overrides:
```bash
export EXECUTION__OMS__MODE=paper
export EXECUTION__RISK__MAX_LEVERAGE=1.5
export BINANCE_API_KEY=your_api_key
export BINANCE_API_SECRET=your_api_secret
```

## Order States

Orders progress through the following states:

```
PENDING → SUBMITTED → ACCEPTED → FILLED
                         ↓
                     REJECTED
                         ↓
                    CANCELLED
                         ↓
                      EXPIRED
```

Each state transition is recorded in the order ledger for audit purposes.

## Risk Controls

### Pre-Trade Checks
- Position size limits
- Capital availability
- Leverage constraints
- Blacklist verification
- Trading hours validation

### Post-Trade Monitoring
- Daily loss limits
- Position concentration
- Margin requirements
- Drawdown thresholds
- Exposure limits

### Circuit Breakers
- Automatic trading halt on excessive losses
- Position liquidation on margin calls
- Order cancellation on anomalous prices

## Performance Optimization

- **Connection Pooling**: Reuse WebSocket connections
- **Request Batching**: Batch multiple orders for efficiency
- **Caching**: Cache order book snapshots and positions
- **Async I/O**: Non-blocking I/O for all network operations
- **Rate Limiting**: Intelligent rate limiting to avoid bans

## Monitoring and Observability

### Metrics Exported
- `execution_order_latency_seconds`: Order submission latency
- `execution_fill_rate`: Percentage of orders filled
- `execution_slippage_bps`: Average slippage in basis points
- `execution_rejection_rate`: Order rejection rate
- `execution_position_count`: Number of open positions
- `execution_pnl_total`: Total P&L

### Alerts
- Order rejection rate > threshold
- Fill rate < threshold
- Excessive slippage detected
- Risk limit breached
- Exchange connectivity issues

## Best Practices

1. **Always Use Paper Trading First**: Test strategies in paper mode before live
2. **Set Conservative Risk Limits**: Start with tight limits and relax gradually
3. **Monitor Execution Quality**: Track slippage and rejection rates
4. **Use Smart Routing**: Let the router find best execution venues
5. **Implement Circuit Breakers**: Protect against runaway losses
6. **Audit Everything**: Review order ledger regularly
7. **Test Failover**: Ensure graceful degradation on exchange outages

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Execution API                           │
├──────────────────────────────────────────────────────────────┤
│  Order Management System (OMS)                               │
│  ├─ Order Lifecycle Manager                                  │
│  ├─ Risk Controller                                          │
│  └─ Compliance Monitor                                       │
├──────────────────────────────────────────────────────────────┤
│  Execution Layer                                             │
│  ├─ Smart Router  ├─ Algorithms  ├─ Position Sizer          │
├──────────────────────────────────────────────────────────────┤
│  Connector Layer                                             │
│  ├─ Binance  ├─ Coinbase  ├─ Kraken  ├─ Paper Trading      │
├──────────────────────────────────────────────────────────────┤
│  Data Layer                                                  │
│  ├─ Order Ledger  ├─ Position Store  ├─ Market Data Cache  │
└──────────────────────────────────────────────────────────────┘
```

## Related Modules

- [`core`](../core/README.md): Core trading infrastructure
- [`analytics`](../analytics/README.md): Execution quality analysis (TCA)
- [`backtest`](../backtest/README.md): Backtesting with execution simulation
- [`strategies`](../strategies/README.md): Trading strategies
- [`observability`](../observability/README.md): Metrics and monitoring

## Documentation

- [API Reference](https://docs.tradepulse.io/api/execution)
- [OMS Guide](https://docs.tradepulse.io/guides/oms)
- [Exchange Connector Guide](https://docs.tradepulse.io/guides/connectors)
- [Risk Management Guide](https://docs.tradepulse.io/guides/risk)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for licensing details.

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [Documentation](https://docs.tradepulse.io)
- [Community](https://github.com/neuron7x/TradePulse/discussions)
